#
# config.py
#
# Author: Griffith Thomas
# Copyright 2023 Spyderbat, Inc. All rights reserved.
#

"""
Configuration object and associated functions
"""

from platformdirs import PlatformDirs


DIRS = PlatformDirs(  # pylint: disable=unexpected-keyword-arg
    "spydertop",
    "Spyderbat",
    roaming=True,
    ensure_exists=True,
)
DEFAULT_API_URL = "https://api.spyderbat.com"
