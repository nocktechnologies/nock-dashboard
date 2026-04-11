from setuptools import find_packages, setup

setup(
    name="nockcc-agent",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "websockets>=12.0",
    ],
    entry_points={
        "console_scripts": [
            "nockcc-agent=nockcc_agent.daemon:main",
        ],
    },
    python_requires=">=3.12",
)
