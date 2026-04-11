from setuptools import find_packages, setup

setup(
    name="nockcc-cli",
    version="0.1.0",
    packages=find_packages(where=".."),
    package_dir={"": ".."},
    install_requires=["click>=8.0", "httpx>=0.24", "rich>=13.0"],
    entry_points={
        "console_scripts": [
            "nockcc=cli.nockcc:cli",
        ],
    },
)
