import os
from glob import glob

from setuptools import find_packages, setup

package_name = "vatp_ros"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
        (os.path.join("share", package_name, "config"), glob("config/*")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="sinchk",
    maintainer_email="sinchugk@gmail.com",
    description="ROS 2 nodes for the Verifiable Agentic Task Planner.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "planner_node = vatp_ros.planner_node:main",
            "skill_server = vatp_ros.skill_server:main",
            "benchmark = vatp_ros.benchmark:main",
        ],
    },
)
