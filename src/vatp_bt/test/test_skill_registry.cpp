// The executor must be able to instantiate EXACTLY the skills the validator/LLM know about.
#include <gtest/gtest.h>

#include <set>

#include "ament_index_cpp/get_package_share_directory.hpp"
#include "behaviortree_cpp/bt_factory.h"
#include "vatp_bt/skill_registry.hpp"

TEST(SkillRegistry, LoadsSharedSkillLibrary)
{
  const auto path =
    ament_index_cpp::get_package_share_directory("vatp_core") + "/spec/skills.yaml";
  const auto specs = vatp_bt::load_skill_specs(path);
  std::set<std::string> names;
  for (const auto & s : specs) {names.insert(s.name);}
  for (const char * expect : {"NavigateTo", "PickObject", "PlaceObject", "CheckZoneClear",
      "CheckHolding", "CheckObjectAt", "ReportStatus", "RequestHumanHelp", "Wait"})
  {
    EXPECT_TRUE(names.count(expect)) << expect;
  }
}

TEST(SkillRegistry, ActionNameIsSnakeCase)
{
  EXPECT_EQ(vatp_bt::skill_action_name("NavigateTo"), "/vatp/skills/navigate_to");
  EXPECT_EQ(vatp_bt::skill_action_name("CheckZoneClear"), "/vatp/skills/check_zone_clear");
  EXPECT_EQ(vatp_bt::skill_action_name("Wait"), "/vatp/skills/wait");
}

TEST(SkillRegistry, RegistersAllAndBuildsPlanXml)
{
  const auto path =
    ament_index_cpp::get_package_share_directory("vatp_core") + "/spec/skills.yaml";
  const auto specs = vatp_bt::load_skill_specs(path);
  BT::BehaviorTreeFactory f;
  auto ctx = std::make_shared<vatp_bt::SkillContext>();
  EXPECT_EQ(vatp_bt::register_skills(f, specs, ctx), specs.size());
  const std::string xml = R"(
<root BTCPP_format="4" main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <Sequence name="n1">
      <Fallback name="n2">
        <CheckZoneClear name="n3" zone="loading_bay"/>
        <RequestHumanHelp name="n4" reason="blocked"/>
      </Fallback>
      <RetryUntilSuccessful name="n5" num_attempts="3">
        <NavigateTo name="n6" zone="zone_b"/>
      </RetryUntilSuccessful>
    </Sequence>
  </BehaviorTree>
</root>)";
  EXPECT_NO_THROW(f.createTreeFromText(xml));
}

TEST(SkillRegistry, RejectsUnknownSkillAndMissingPort)
{
  const auto path =
    ament_index_cpp::get_package_share_directory("vatp_core") + "/spec/skills.yaml";
  BT::BehaviorTreeFactory f;
  auto ctx = std::make_shared<vatp_bt::SkillContext>();
  vatp_bt::register_skills(f, vatp_bt::load_skill_specs(path), ctx);
  const std::string bad =
    R"(<root BTCPP_format="4" main_tree_to_execute="M"><BehaviorTree ID="M"><GraspObject name="x"/></BehaviorTree></root>)";
  EXPECT_THROW(f.createTreeFromText(bad), std::exception);
}

int main(int argc, char ** argv)
{
  testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
