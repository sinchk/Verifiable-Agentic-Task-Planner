cmake_minimum_required(VERSION 3.8)
project(vatp_bt)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()
set(CMAKE_CXX_STANDARD 17)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)
find_package(behaviortree_cpp REQUIRED)
find_package(vatp_interfaces REQUIRED)
find_package(ament_index_cpp REQUIRED)
find_package(yaml-cpp REQUIRED)

add_library(vatp_bt_lib src/skill_registry.cpp)
target_include_directories(vatp_bt_lib PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
ament_target_dependencies(vatp_bt_lib rclcpp rclcpp_action rclcpp_lifecycle
  behaviortree_cpp vatp_interfaces ament_index_cpp)
target_link_libraries(vatp_bt_lib yaml-cpp)

add_executable(bt_executor src/bt_executor.cpp)
target_link_libraries(bt_executor vatp_bt_lib)
ament_target_dependencies(bt_executor rclcpp rclcpp_action rclcpp_lifecycle
  behaviortree_cpp vatp_interfaces ament_index_cpp)

install(TARGETS vatp_bt_lib bt_executor
  ARCHIVE DESTINATION lib LIBRARY DESTINATION lib RUNTIME DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY include/ DESTINATION include)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_skill_registry test/test_skill_registry.cpp)
  target_link_libraries(test_skill_registry vatp_bt_lib)
  ament_target_dependencies(test_skill_registry rclcpp rclcpp_action rclcpp_lifecycle
    behaviortree_cpp vatp_interfaces ament_index_cpp)
endif()

ament_package()
