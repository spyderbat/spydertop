#
# __init__.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
This module contains a set of constant values, including the column specifications
and color palettes.
"""

import spydertop.constants.palettes

# matches all of the escape sequences that are used in the Asciimatics parser
COLOR_REGEX = r"\${(-?\d+)(, ?(\d+)(, ?(-?\d+))?)?}"
# the page size to use when converting to bytes
PAGE_SIZE = 4096

API_LOG_TYPES = {
    "startup": "SpydertopStartup",
    "shutdown": "SpydertopShutdown",
    "loaded_data": "SpydertopLoadedData",
    "orgs": "SpydertopOrgsListed",
    "sources": "SpydertopSourcesListed",
    "clusters": "SpydertopClustersListed",
    "feedback": "SendFeedback",
    "navigation": "SpydertopNavigation",
    "account_created": "SpydertopAccountCreated",
}
