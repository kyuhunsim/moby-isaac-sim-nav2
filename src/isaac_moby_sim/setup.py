from glob import glob
import os

from setuptools import find_packages, setup


package_name = "isaac_moby_sim"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "config"), glob("config/*")),
        (
            os.path.join("share", package_name, "assets", "scenes"),
            glob("assets/scenes/*.usd"),
        ),
        (
            os.path.join("share", package_name, "assets", "arm"),
            glob("assets/arm/*.usd"),
        ),
    ],
    scripts=["scripts/run_moby_stage.py"],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="RISE Lab",
    maintainer_email="jinkanglee@g.skku.edu",
    description="Isaac Sim stage assets and runner for Moby.",
    license="MIT",
)
