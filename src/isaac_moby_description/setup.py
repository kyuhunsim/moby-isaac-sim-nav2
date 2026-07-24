from pathlib import Path

from setuptools import find_packages, setup


package_name = "isaac_moby_description"
package_root = Path(__file__).parent


def package_files(directory: str):
    root = package_root / directory
    files = []
    for path in root.rglob("*"):
        if path.is_file():
            relative_directory = path.parent.relative_to(package_root)
            destination = Path("share") / package_name / relative_directory
            files.append((str(destination), [str(path)]))
    return files


data_files = [
    ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
    ("share/" + package_name, ["package.xml"]),
]
data_files.extend(package_files("urdf"))
data_files.extend(package_files("model"))

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=data_files,
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="RISE Lab",
    maintainer_email="jinkanglee@g.skku.edu",
    description="URDF and mesh description for the Moby mobile manipulator.",
    license="MIT",
)
