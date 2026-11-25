// Lifecycle BehaviorTree.CPP executor with a closed-loop recovery supervisor.
//
//   RunMission(instruction)
//     1. GetWorld                    current perceived scene
//     2. PlanMission (LLM+validator) -> validated BT.CPP XML      (nothing moves before this)
//     3. tick the tree; every skill is an ExecuteSkill action call
//     4. tree FAILURE  -> FALLBACK_TRIGGERED -> GetWorld (re-perceive) -> Replan(failure, world)
//                      -> validated patch for the REMAINING mission -> TREE_SWAPPED -> goto 3
//
// Lifecycle: configure = load skill library, create clients/servers; activate = accept
// missions; deactivate = halt the running tree and reject goals.

#include <atomic>
#include <chrono>
#include <future>
#include <memory>
#include <string>
#include <thread>

#include "ament_index_cpp/get_package_share_directory.hpp"
#include "behaviortree_cpp/bt_factory.h"
#include "behaviortree_cpp/contrib/json.hpp"
#include "behaviortree_cpp/loggers/abstract_logger.h"
#include "behaviortree_cpp/loggers/groot2_publisher.h"
#include "lifecycle_msgs/msg/state.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"
#include "vatp_bt/skill_registry.hpp"
#include "vatp_interfaces/action/run_mission.hpp"
#include "vatp_interfaces/msg/mission_event.hpp"
#include "vatp_interfaces/srv/get_world.hpp"
#include "vatp_interfaces/srv/plan_mission.hpp"
#include "vatp_interfaces/srv/replan.hpp"

using namespace std::chrono_literals;
using json = nlohmann::json;
using CallbackReturn = rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn;
using RunMission = vatp_interfaces::action::RunMission;
using GoalHandle = rclcpp_action::ServerGoalHandle<RunMission>;
using MissionEvent = vatp_interfaces::msg::MissionEvent;

namespace
{

// Publishes NODE_STATUS events for every status transition (feeds dashboards / metrics).
class EventLogger : public BT::StatusChangeLogger
{
public:
  EventLogger(
    BT::TreeNode * root,
    std::function<void(const std::string &, const std::string &, const std::string &)> emit)
  : BT::StatusChangeLogger(root), emit_(std::move(emit)) {}

  void callback(
    BT::Duration, const BT::TreeNode & node, BT::NodeStatus, BT::NodeStatus status) override
  {
    if (status == BT::NodeStatus::IDLE) {return;}
    emit_("NODE_STATUS", node.name(), json{{"status", BT::toStr(status)}}.dump());
  }
  void flush() override {}

private:
  std::function<void(const std::string &, const std::string &, const std::string &)> emit_;
};

}  // namespace

class BtExecutor : public rclcpp_lifecycle::LifecycleNode
{
public:
  BtExecutor()
  : rclcpp_lifecycle::LifecycleNode("vatp_bt_executor")
  {
    declare_parameter("skills_yaml", "");
    declare_parameter("groot_port", 1667);
    declare_parameter("tick_hz", 30.0);
    declare_parameter("service_timeout_s", 120.0);
    declare_parameter("autostart", true);
  }

  void autostart_if_requested()
  {
    if (!get_parameter("autostart").as_bool()) {return;}
    boot_ = create_wall_timer(
      500ms, [this]() {
        boot_->cancel();
        if (configure().id() == lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE) {activate();}
      });
  }

  CallbackReturn on_configure(const rclcpp_lifecycle::State &) override
  {
    try {
      std::string path = get_parameter("skills_yaml").as_string();
      if (path.empty()) {
        path = ament_index_cpp::get_package_share_directory("vatp_core") + "/spec/skills.yaml";
      }
      specs_ = vatp_bt::load_skill_specs(path);
      RCLCPP_INFO(get_logger(), "skill library: %zu skills from %s", specs_.size(), path.c_str());
    } catch (const std::exception & e) {
      RCLCPP_ERROR(get_logger(), "cannot load skill library: %s", e.what());
      return CallbackReturn::FAILURE;
    }
    cb_ = create_callback_group(rclcpp::CallbackGroupType::Reentrant);
    ctx_ = std::make_shared<vatp_bt::SkillContext>();
    ctx_->emit = [this](const std::string & t, const std::string & n, const std::string & d) {
        emit(t, n, d);
      };
    auto self = std::static_pointer_cast<rclcpp_lifecycle::LifecycleNode>(shared_from_this());
    vatp_bt::create_clients(self, specs_, cb_, *ctx_);
    factory_ = std::make_unique<BT::BehaviorTreeFactory>();
    vatp_bt::register_skills(*factory_, specs_, ctx_);

    events_ = create_publisher<MissionEvent>("/vatp/events", 100);
    plan_cli_ = create_client<vatp_interfaces::srv::PlanMission>(
      "/vatp/plan_mission", rclcpp::ServicesQoS(), cb_);
    replan_cli_ = create_client<vatp_interfaces::srv::Replan>(
      "/vatp/replan", rclcpp::ServicesQoS(), cb_);
    world_cli_ = create_client<vatp_interfaces::srv::GetWorld>(
      "/vatp/get_world", rclcpp::ServicesQoS(), cb_);

    server_ = rclcpp_action::create_server<RunMission>(
      this, "/vatp/run_mission",
      [this](const rclcpp_action::GoalUUID &, std::shared_ptr<const RunMission::Goal>) {
        return active_ && !busy_.exchange(true) ?
        rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE : rclcpp_action::GoalResponse::REJECT;
      },
      [](std::shared_ptr<GoalHandle>) {return rclcpp_action::CancelResponse::ACCEPT;},
      [this](std::shared_ptr<GoalHandle> gh) {
        if (worker_.joinable()) {worker_.join();}
        worker_ = std::thread([this, gh]() {execute(gh); busy_ = false;});
      },
      rcl_action_server_get_default_options(), cb_);
    return CallbackReturn::SUCCESS;
  }

  CallbackReturn on_activate(const rclcpp_lifecycle::State & s) override
  {
    LifecycleNode::on_activate(s);
    active_ = true;
    RCLCPP_INFO(get_logger(), "ACTIVE: accepting missions");
    return CallbackReturn::SUCCESS;
  }

  CallbackReturn on_deactivate(const rclcpp_lifecycle::State & s) override
  {
    active_ = false;
    halt_requested_ = true;
    if (worker_.joinable()) {worker_.join();}
    halt_requested_ = false;
    LifecycleNode::on_deactivate(s);
    return CallbackReturn::SUCCESS;
  }

  CallbackReturn on_cleanup(const rclcpp_lifecycle::State &) override
  {
    server_.reset(); plan_cli_.reset(); replan_cli_.reset(); world_cli_.reset();
    return CallbackReturn::SUCCESS;
  }

  ~BtExecutor() override
  {
    halt_requested_ = true;
    if (worker_.joinable()) {worker_.join();}
  }

private:
  void emit(const std::string & type, const std::string & node, const std::string & detail)
  {
    if (!events_ || !events_->is_activated()) {return;}
    MissionEvent m;
    m.stamp = now();
    m.type = type; m.node = node; m.detail = detail;
    events_->publish(m);
  }

  template<typename Srv>
  typename Srv::Response::SharedPtr call(
    typename rclcpp::Client<Srv>::SharedPtr cli, typename Srv::Request::SharedPtr req)
  {
    const auto timeout = std::chrono::duration<double>(get_parameter("service_timeout_s").as_double());
    if (!cli->wait_for_service(10s)) {return nullptr;}
    auto fut = cli->async_send_request(req);
    if (fut.wait_for(timeout) != std::future_status::ready) {return nullptr;}
    return fut.get();
  }

  static int metric_int(const std::string & js, const char * key)
  {
    auto j = json::parse(js, nullptr, false);
    return j.is_object() && j.contains(key) && j[key].is_number() ? j[key].get<int>() : 0;
  }

  static double secs(std::chrono::steady_clock::time_point a)
  {
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - a).count();
  }

  void finish(
    const std::shared_ptr<GoalHandle> & gh, std::shared_ptr<RunMission::Result> r, bool ok,
    const std::string & msg)
  {
    r->success = ok;
    r->message = msg;
    emit(
      "MISSION_END", "", json{{"success", ok}, {"message", msg}, {"replans", r->replans}}.dump());
    if (ok) {gh->succeed(r);} else {gh->abort(r);}
  }

  void execute(const std::shared_ptr<GoalHandle> gh)
  {
    const auto goal = gh->get_goal();
    auto result = std::make_shared<RunMission::Result>();
    auto fb = std::make_shared<RunMission::Feedback>();
    const int max_replans = goal->max_replans ? goal->max_replans : 3;
    ctx_->clear_failures();

    // 1) perceive ---------------------------------------------------------------------
    auto wreq = std::make_shared<vatp_interfaces::srv::GetWorld::Request>();
    auto wresp = call<vatp_interfaces::srv::GetWorld>(world_cli_, wreq);
    if (!wresp || wresp->world_yaml.empty()) {
      return finish(gh, result, false, "no world available from /vatp/get_world");
    }

    // 2) plan (LLM + deterministic validator) -----------------------------------------
    emit("PLAN_REQUEST", "", json{{"instruction", goal->instruction}}.dump());
    auto preq = std::make_shared<vatp_interfaces::srv::PlanMission::Request>();
    preq->instruction = goal->instruction;
    preq->world_yaml = wresp->world_yaml;
    preq->required_goals_json = goal->required_goals_json;
    const auto t_plan = std::chrono::steady_clock::now();
    auto presp = call<vatp_interfaces::srv::PlanMission>(plan_cli_, preq);
    result->first_plan_latency_s = secs(t_plan);
    if (!presp) {return finish(gh, result, false, "planner service timeout");}
    emit("PLAN_READY", "", json{{"ok", presp->ok}, {"latency_s", result->first_plan_latency_s},
        {"metrics", json::parse(presp->metrics_json, nullptr, false)}}.dump());
    if (!presp->ok) {
      return finish(gh, result, false, "plan REJECTED by validator: " + presp->issues_json);
    }
    std::string xml = presp->bt_xml;
    result->initial_nodes = metric_int(presp->metrics_json, "nodes");

    // 3/4) execute with closed-loop recovery ------------------------------------------
    const double hz = get_parameter("tick_hz").as_double();
    while (true) {
      factory_->clearRegisteredBehaviorTrees();
      BT::Tree tree;
      try {
        tree = factory_->createTreeFromText(xml);
      } catch (const std::exception & e) {
        result->final_bt_xml = xml;
        return finish(gh, result, false, std::string("executor could not build tree: ") + e.what());
      }
      result->final_bt_xml = xml;
      std::unique_ptr<BT::Groot2Publisher> groot;
      try {
        groot = std::make_unique<BT::Groot2Publisher>(
          tree, static_cast<unsigned>(get_parameter("groot_port").as_int()));
      } catch (const std::exception & e) {
        RCLCPP_WARN(get_logger(), "Groot2 publisher unavailable: %s", e.what());
      }
      EventLogger logger(
        tree.rootNode(), [this](const std::string & t, const std::string & n, const std::string & d) {emit(t, n, d);});
      emit("TREE_STARTED", "", json{{"replans", result->replans}}.dump());
      ctx_->clear_failures();

      BT::NodeStatus st = BT::NodeStatus::RUNNING;
      while (st == BT::NodeStatus::RUNNING) {
        if (halt_requested_ || !rclcpp::ok()) {
          tree.haltTree();
          return finish(gh, result, false, "halted by lifecycle deactivation");
        }
        if (gh->is_canceling()) {
          tree.haltTree();
          r_canceled(gh, result);
          return;
        }
        st = tree.tickOnce();
        if (st == BT::NodeStatus::RUNNING) {
          std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>(1000.0 / hz)));
        }
      }
      tree.haltTree();

      if (st == BT::NodeStatus::SUCCESS) {
        return finish(gh, result, true, "mission tree completed");
      }

      // ---- FAILURE: recovery supervisor ------------------------------------------------
      const auto f = ctx_->best_failure();
      emit(
        "FALLBACK_TRIGGERED", f.node,
        json{{"skill", f.skill}, {"code", f.code}, {"message", f.message}}.dump());
      if (static_cast<int>(result->replans) >= max_replans) {
        return finish(gh, result, false, "tree failed and replan budget exhausted: " + f.code);
      }
      fb->status = "replanning after " + f.code;
      fb->replans = result->replans;
      gh->publish_feedback(fb);

      auto w2 = call<vatp_interfaces::srv::GetWorld>(world_cli_, std::make_shared<vatp_interfaces::srv::GetWorld::Request>());
      if (!w2) {return finish(gh, result, false, "world service timeout during recovery");}
      auto rreq = std::make_shared<vatp_interfaces::srv::Replan::Request>();
      rreq->instruction = goal->instruction;
      rreq->world_yaml = w2->world_yaml;
      rreq->failed_node = f.node;
      rreq->failed_skill = f.skill;
      rreq->failure_code = f.code;
      rreq->failure_message = f.message;
      rreq->required_goals_json = goal->required_goals_json;
      emit("REPLAN_REQUEST", f.node, json{{"code", f.code}}.dump());
      const auto t_re = std::chrono::steady_clock::now();
      auto rresp = call<vatp_interfaces::srv::Replan>(replan_cli_, rreq);
      const double dt = secs(t_re);
      result->total_replan_latency_s += dt;
      if (!rresp) {return finish(gh, result, false, "replan service timeout");}
      emit(
        "REPLAN_READY", f.node,
        json{{"ok", rresp->ok}, {"latency_s", dt},
          {"metrics", json::parse(rresp->metrics_json, nullptr, false)}}.dump());
      if (!rresp->ok) {
        return finish(gh, result, false, "replan REJECTED by validator: " + rresp->issues_json);
      }
      xml = rresp->bt_xml;
      ++result->replans;
      emit("TREE_SWAPPED", f.node, json{{"replans", result->replans}}.dump());
    }
  }

  void r_canceled(const std::shared_ptr<GoalHandle> & gh, std::shared_ptr<RunMission::Result> r)
  {
    r->success = false;
    r->message = "canceled";
    gh->canceled(r);
  }

  std::vector<vatp_bt::SkillSpec> specs_;
  std::shared_ptr<vatp_bt::SkillContext> ctx_;
  std::unique_ptr<BT::BehaviorTreeFactory> factory_;
  rclcpp::CallbackGroup::SharedPtr cb_;
  rclcpp_lifecycle::LifecyclePublisher<MissionEvent>::SharedPtr events_;
  rclcpp::Client<vatp_interfaces::srv::PlanMission>::SharedPtr plan_cli_;
  rclcpp::Client<vatp_interfaces::srv::Replan>::SharedPtr replan_cli_;
  rclcpp::Client<vatp_interfaces::srv::GetWorld>::SharedPtr world_cli_;
  rclcpp_action::Server<RunMission>::SharedPtr server_;
  rclcpp::TimerBase::SharedPtr boot_;
  std::thread worker_;
  std::atomic<bool> active_{false}, busy_{false}, halt_requested_{false};
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<BtExecutor>();
  node->autostart_if_requested();
  rclcpp::executors::MultiThreadedExecutor exec(rclcpp::ExecutorOptions(), 6);
  exec.add_node(node->get_node_base_interface());
  exec.spin();
  rclcpp::shutdown();
  return 0;
}
