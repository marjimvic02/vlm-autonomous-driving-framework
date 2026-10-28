from setuptools import find_packages, setup

package_name = "perception_module"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="marjimvic",
    maintainer_email="marjimvic02@users.noreply.github.com",
    description="Scene context fusion from CARLA sensor topics.",
    license="LicenseRef-Proprietary",
    entry_points={
        "console_scripts": ["scene_context_node = perception_module.scene_context_node:main"],
    },
)
