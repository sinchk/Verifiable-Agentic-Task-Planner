from setuptools import find_packages, setup

package_name = "vatp_core"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["tests"]),
    package_data={package_name: ["spec/*.yaml", "knowledge/*.md"]},
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/spec", ["vatp_core/spec/skills.yaml"]),
    ],
    install_requires=["setuptools", "pyyaml"],
    zip_safe=True,
    maintainer="sinchk",
    maintainer_email="sinchugk@gmail.com",
    description="Skill library, world model, BT validator, RAG and LLM planner (ROS-independent).",
    license="Apache-2.0",
    tests_require=["pytest"],
)
