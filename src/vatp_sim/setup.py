import os
from glob import glob

from setuptools import find_packages, setup

package_name = "vatp_sim"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
        (os.path.join("share", package_name, "config"), glob("config/*")),
        (os.path.join("share", package_name, "urdf"), glob("urdf/*")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="sinchk",
    maintainer_email="sinchugk@gmail.com",
    description="Gazebo Harmonic warehouse and mobile manipulator for the VATP project.",
    license="Apache-2.0",
    entry_points={"console_scripts": ["ground_truth_localizer = vatp_sim.ground_truth_localizer:main"]},
)
