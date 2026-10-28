import os
from glob import glob

from setuptools import find_packages, setup

package_name = "low_control_module"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (
            os.path.join("share", package_name, "launch"),
            glob("launch/*.launch.py") + glob("launch/*.json"),
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="marjimvic",
    maintainer_email="marjimvic02@users.noreply.github.com",
    description="Semantic action dispatch and speed control through CARLA Traffic Manager.",
    license="LicenseRef-Proprietary",
    entry_points={
        "console_scripts": ["action_dispatcher = low_control_module.action_dispatcher:main"],
    },
)
