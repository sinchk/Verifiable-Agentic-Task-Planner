#pragma once
// Registers every skill of the shared skill library (skills.yaml) as a BehaviorTree.CPP node.
// The library file is the single source of truth: adding a skill there makes it
// available to the validator, the LLM prompt AND this executor without C++ changes
// (as long as a skill server implements the action).

#include <atomic>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "behaviortree_cpp/bt_factory.h"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"
#include "vatp_interfaces/action/execute_skill.hpp"

namespace vatp_bt
{

using ExecuteSkill = vatp_interfaces::action::ExecuteSkill;
using SkillClient = rclcpp_action::Client<ExecuteSkill>;

struct SkillSpec
{
  std::string name;
  std::string kind;  // "action" | "condition"
  std::vector<std::string> ports;
};

/// Parses the `skills:` section of skills.yaml.
std::vector<SkillSpec> load_skill_specs(const std::string & yaml_path);

/// CamelCase -> /vatp/skills/snake_case
std::string skill_action_name(const std::string & skill);

struct FailureInfo
{
  std::string node, skill, code, message;
  bool valid{false};
};

/// State shared by all skill nodes of one executor.
struct SkillContext
{
  std::map<std::string, SkillClient::SharedPtr> clients;
  std::mutex mu;
  FailureInfo last_action_failure;     // last failed *action* (what recovery cares about)
  FailureInfo last_condition_failure;  // fallback if the tree failed on a condition
  std::function<void(const std::string &, const std::string &, const std::string &)> emit;
  uint64_t skill_calls{0};

  void clear_failures()
  {
    std::lock_guard<std::mutex> l(mu);
    last_action_failure = {};
    last_condition_failure = {};
  }
  FailureInfo best_failure()
  {
    std::lock_guard<std::mutex> l(mu);
    return last_action_failure.valid ? last_action_failure : last_condition_failure;
  }
};

/// Create one action client per skill on `node`.
void create_clients(
  const rclcpp_lifecycle::LifecycleNode::SharedPtr & node, const std::vector<SkillSpec> & specs,
  const rclcpp::CallbackGroup::SharedPtr & group, SkillContext & ctx);

/// Register all skills on the factory; returns the number of registered nodes.
size_t register_skills(
  BT::BehaviorTreeFactory & factory, const std::vector<SkillSpec> & specs,
  const std::shared_ptr<SkillContext> & ctx);

}  // namespace vatp_bt
