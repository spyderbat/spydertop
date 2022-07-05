#
# setup.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc.  All rights reserved.
#

"""
    Spydertop Historical TOP Tool

    Provides a way to view the state of a system
    in the past, utilizing the spyderbat apis.
"""


from setuptools import setup

NAME = "spydertop"
VERSION = "0.1.0"
# To install the library, run the following
#
# python setup.py install
#
# prerequisite: setuptools
# http://pypi.python.org/pypi/setuptools

REQUIRES = ["asciimatics", "click", "sbapi", "pyyaml", "typing", "textwrap"]

setup(
    name=NAME,
    version=VERSION,
    description="Historical TOP Tool",
    author="Griffith Thomas",
    author_email="kiranwells1008@gmail.com",
    url="",
    keywords=["spydertop", "Spyderbat API UI & Public APIs"],
    python_requires=">=3.6",
    install_requires=REQUIRES,
    packages=["spydertop", "spydertop.screens"],
    py_modules="spydertop",
    include_package_data=True,
    long_description="""\
    Provides a way to view the state of a system
    in the past, utilizing the spyderbat apis.
    """,
    entry_points="""
    [console_scripts]
    spydertop=spydertop:cli
    """,
)
