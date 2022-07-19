#
# setup.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
    Spydertop Historical TOP Tool

    Provides a way to view the state of a system
    in the past, utilizing the spyderbat apis.
"""


from setuptools import setup

NAME = "spydertop"
VERSION = "0.2.1"

REQUIRES = ["asciimatics", "click", "spyderbat-api", "pyyaml"]

setup(
    name=NAME,
    version=VERSION,
    description="Historical TOP Tool",
    author="Griffith Thomas",
    author_email="dev@spyderbat.com",
    url="https://github.com/spyderbat/spydertop",
    keywords=["spydertop", "Spyderbat API UI & Public APIs"],
    python_requires=">=3.6",
    install_requires=REQUIRES,
    packages=["spydertop", "spydertop.screens"],
    py_modules=["spydertop", "spydertop.screens"],
    include_package_data=True,
    long_description="""\
    Provides a way to view the state of a system
    in the past, utilizing the Spyderbat apis.
    """,
    entry_points="""
    [console_scripts]
    spydertop=spydertop:cli
    """,
)
