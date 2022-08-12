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
from spydertop.cli import cli

if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter

    # add arguments as an array of strings as they
    # would come from the command line for debugging
    cli(["--log-level", "DEBUG+"])
