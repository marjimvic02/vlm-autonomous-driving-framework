from glob import glob

from setuptools import find_packages, setup

package_name = "decision_making_module"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml", "LICENSE"]),
        # Install the behavior prompt so it is found on a non-symlink build too
        ("share/" + package_name + "/prompt", glob("prompt/*.md")),
    ],
    install_requires=["setuptools", "python-dotenv", "openai", "requests"],
    zip_safe=True,
    maintainer="marjimvic",
    maintainer_email="marjimvic02@users.noreply.github.com",
    description="Multimodal high-level driving decisions using local or cloud VLMs.",
    license="MIT",
    entry_points={
        "console_scripts": ["prompt_manager = decision_making_module.prompt_manager:main"],
    },
)
