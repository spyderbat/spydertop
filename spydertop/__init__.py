#
# __init__.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
Spydertop Historical TOP Tool

Provides a way to view the state of a system
in the past, utilizing the spyderbat apis.
"""

# see the cli function in cli.py for the entry point
import sys
from spydertop.cli import cli

if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    # if frozen, then we are running as a pyinstaller executable
    if getattr(sys, "frozen", False):
        cli(sys.argv[1:])

    # otherwise, we are running as a python module, likely for debugging
    # default to debug logging
    cli(["--log-level", "DEVELOPMENT+", "load"] + sys.argv[1:])
