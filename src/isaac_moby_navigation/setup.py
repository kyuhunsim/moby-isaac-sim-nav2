from glob import glob
import os

from setuptools import find_packages, setup


package_name = "isaac_moby_navigation"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
        (os.path.join("share", package_name, "map"), glob("map/*")),
        (os.path.join("share", package_name, "param"), glob("param/*.yaml")),
        (os.path.join("share", package_name, "rviz"), glob("rviz/*.rviz")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="RISE Lab",
    maintainer_email="jinkanglee@g.skku.edu",
    description="Minimal Nav2 configuration for Moby.",
    license="MIT",
)
