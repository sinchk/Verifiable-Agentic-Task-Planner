#include "vatp_bt/skill_registry.hpp"

#include <cctype>
#include <stdexcept>

#include "behaviortree_cpp/contrib/json.hpp"
#include "yaml-cpp/yaml.h"

namespace vatp_bt
{

std::vector<SkillSpec> load_skill_specs(const std::string & yaml_path)
{
  YAML::Node root = YAML::LoadFile(yaml_path);
  std::vector<SkillSpec> specs;
  for (const auto & kv : root["skills"]) {
    SkillSpec s;
    s.name = kv.first.as<std::string>();
    s.kind = kv.second["kind"].as<std::string>();
    if (kv.second["ports"]) {
      for (const auto & p : kv.second["ports"]) {
        s.ports.push_back(p.first.as<std::string>());
      }
    }
    specs.push_back(std::move(s));
  }
  return specs;
}

std::string skill_action_name(const std::string & skill)
{
  std::string out = "/vatp/skills/";
  for (size_t i = 0; i < skill.size(); ++i) {
    const char c = skill[i];
    if (std::isupper(static_cast<unsigned char>(c))) {
      if (i > 0) {out += '_';}
      out += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    } else {
      out += c;
    }
  }
  return out;
}

void create_clients(
  const rclcpp_lifecycle::LifecycleNode::SharedPtr & node, const std::vector<SkillSpec> & specs,
  const rclcpp::CallbackGroup::SharedPtr & group, SkillContext & ctx)
{
  for (const auto & s : specs) {
    ctx.clients[s.name] =
      rclcpp_action::create_client<ExecuteSkill>(node, skill_action_name(s.name), group);
  }
}

namespace
{

enum class Phase {Pending, Running, Succeeded, Failed, Rejected};

// Shared with action callbacks; outlives the BT node if the tree is swapped mid-flight.
struct CallState
{
  std::atomic<Phase> phase{Phase::Pending};
  std::mutex mu;
  rclcpp_action::ClientGoalHandle<ExecuteSkill>::SharedPtr handle;
  std::string code, message;
};

class SkillNode : public BT::StatefulActionNode
{
public:
  SkillNode(
    const std::string & name, const BT::NodeConfig & cfg, std::shared_ptr<SkillContext> ctx,
    SkillSpec spec)
  : BT::StatefulActionNode(name, cfg), ctx_(std::move(ctx)), spec_(std::move(spec)) {}

  static BT::PortsList providedPorts() {return {};}  // real ports come from the manifest

  BT::NodeStatus onStart() override
  {
    auto client = ctx_->clients.at(spec_.name);
    ExecuteSkill::Goal goal;
    goal.skill = spec_.name;
    std::string args_json = "{";
    for (const auto & p : spec_.ports) {
      auto v = getInput<std::string>(p);
      if (!v) {
        return fail("PLAN_INVALID", "missing port '" + p + "': " + v.error());
      }
      goal.arg_names.push_back(p);
      goal.arg_values.push_back(v.value());
      args_json += "\"" + p + "\":\"" + v.value() + "\",";
    }
    if (args_json.back() == ',') {args_json.pop_back();}
    args_json += "}";

    if (!client->action_server_is_ready()) {
      return fail("SKILL_UNAVAILABLE", "action server for " + spec_.name + " is not available");
    }
    state_ = std::make_shared<CallState>();
    auto st = state_;
    SkillClient::SendGoalOptions opt;
    opt.goal_response_callback = [st](SkillClient::GoalHandle::SharedPtr h) {
        if (!h) {
          st->code = "SKILL_REJECTED";
          st->message = "goal rejected by skill server";
          st->phase = Phase::Rejected;
        } else {
          std::lock_guard<std::mutex> l(st->mu);
          st->handle = h;
          st->phase = Phase::Running;
        }
      };
    opt.result_callback = [st](const SkillClient::GoalHandle::WrappedResult & r) {
        st->code = r.result ? r.result->code : "NO_RESULT";
        st->message = r.result ? r.result->message : "";
        const bool ok = r.code == rclcpp_action::ResultCode::SUCCEEDED && r.result && r.result->success;
        if (!ok && st->code.empty()) {
          st->code = r.code == rclcpp_action::ResultCode::CANCELED ? "CANCELED" : "SKILL_ABORTED";
        }
        st->phase = ok ? Phase::Succeeded : Phase::Failed;
      };
    {
      std::lock_guard<std::mutex> l(ctx_->mu);
      ++ctx_->skill_calls;
    }
    if (ctx_->emit) {ctx_->emit("SKILL_START", name(), "{\"skill\":\"" + spec_.name + "\",\"args\":" + args_json + "}");}
    client->async_send_goal(goal, opt);
    return BT::NodeStatus::RUNNING;
  }

  BT::NodeStatus onRunning() override
  {
    switch (state_->phase.load()) {
      case Phase::Pending:
      case Phase::Running:
        return BT::NodeStatus::RUNNING;
      case Phase::Succeeded:
        return BT::NodeStatus::SUCCESS;
      case Phase::Rejected:
      case Phase::Failed:
        return fail(state_->code, state_->message);
    }
    return BT::NodeStatus::FAILURE;
  }

  void onHalted() override
  {
    if (!state_) {return;}
    std::lock_guard<std::mutex> l(state_->mu);
    if (state_->handle && state_->phase == Phase::Running) {
      ctx_->clients.at(spec_.name)->async_cancel_goal(state_->handle);
    }
  }

private:
  BT::NodeStatus fail(const std::string & code, const std::string & msg)
  {
    FailureInfo fi{name(), spec_.name, code, msg, true};
    {
      std::lock_guard<std::mutex> l(ctx_->mu);
      (spec_.kind == "action" ? ctx_->last_action_failure : ctx_->last_condition_failure) = fi;
    }
    if (ctx_->emit && spec_.kind == "action") {
      nlohmann::json j = {{"skill", spec_.name}, {"code", code}, {"message", msg}};
      ctx_->emit("SKILL_FAILED", name(), j.dump());
    }
    return BT::NodeStatus::FAILURE;
  }

  std::shared_ptr<SkillContext> ctx_;
  SkillSpec spec_;
  std::shared_ptr<CallState> state_;
};

}  // namespace

size_t register_skills(
  BT::BehaviorTreeFactory & factory, const std::vector<SkillSpec> & specs,
  const std::shared_ptr<SkillContext> & ctx)
{
  for (const auto & spec : specs) {
    BT::TreeNodeManifest manifest;
    manifest.type = spec.kind == "condition" ? BT::NodeType::CONDITION : BT::NodeType::ACTION;
    manifest.registration_ID = spec.name;
    for (const auto & p : spec.ports) {
      manifest.ports.insert(BT::InputPort<std::string>(p));
    }
    factory.registerBuilder(
      manifest, [ctx, spec](const std::string & name, const BT::NodeConfig & cfg) {
        return std::make_unique<SkillNode>(name, cfg, ctx, spec);
      });
  }
  return specs.size();
}

}  // namespace vatp_bt
