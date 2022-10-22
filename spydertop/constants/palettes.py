#
# palettes.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
A set of color palettes based on the asciimatics parser
"""

from asciimatics.screen import Screen
from asciimatics.widgets.utilities import THEMES

# a palette of colors imitating the default look of htop
HTOP_PALETTE = {
    "background": (Screen.COLOUR_DEFAULT, Screen.A_NORMAL, Screen.COLOUR_DEFAULT),
    "borders": (Screen.COLOUR_DEFAULT, Screen.A_NORMAL, Screen.COLOUR_DEFAULT),
    "button": (Screen.COLOUR_BLACK, Screen.A_NORMAL, Screen.COLOUR_WHITE),
    "control": (Screen.COLOUR_CYAN, Screen.A_NORMAL, Screen.COLOUR_DEFAULT),
    "disabled": (Screen.COLOUR_DEFAULT, Screen.A_NORMAL, Screen.COLOUR_MAGENTA),
    "edit_text": (Screen.COLOUR_DEFAULT, Screen.A_NORMAL, Screen.COLOUR_BLACK),
    "field": (Screen.COLOUR_DEFAULT, Screen.A_NORMAL, Screen.COLOUR_DEFAULT),
    "focus_button": (Screen.COLOUR_BLACK, Screen.A_NORMAL, Screen.COLOUR_CYAN),
    "focus_control": (Screen.COLOUR_CYAN, Screen.A_NORMAL, Screen.COLOUR_DEFAULT),
    "focus_edit_text": (Screen.COLOUR_CYAN, Screen.A_NORMAL, Screen.COLOUR_BLACK),
    "focus_field": (Screen.COLOUR_DEFAULT, Screen.A_NORMAL, Screen.COLOUR_DEFAULT),
    "focus_readonly": (Screen.COLOUR_DEFAULT, Screen.A_NORMAL, Screen.COLOUR_DEFAULT),
    "invalid": (Screen.COLOUR_RED, Screen.A_NORMAL, Screen.COLOUR_BLACK),
    "label": (Screen.COLOUR_DEFAULT, Screen.A_NORMAL, Screen.COLOUR_DEFAULT),
    "readonly": (Screen.COLOUR_DEFAULT, Screen.A_NORMAL, Screen.COLOUR_DEFAULT),
    "scroll": (Screen.COLOUR_DEFAULT, Screen.A_NORMAL, Screen.COLOUR_DEFAULT),
    "selected_control": (Screen.COLOUR_DEFAULT, Screen.A_BOLD, Screen.COLOUR_GREEN),
    "selected_field": (Screen.COLOUR_CYAN, Screen.A_BOLD, Screen.COLOUR_DEFAULT),
    "selected_focus_control": (
        Screen.COLOUR_BLACK,
        Screen.A_NORMAL,
        Screen.COLOUR_CYAN,
    ),
    "selected_focus_field": (Screen.COLOUR_BLACK, Screen.A_NORMAL, Screen.COLOUR_CYAN),
    "shadow": (Screen.COLOUR_BLACK, None, Screen.COLOUR_BLACK),
    "title": (Screen.COLOUR_BLACK, Screen.A_NORMAL, Screen.COLOUR_GREEN),
    "meter_label": (Screen.COLOUR_CYAN, Screen.A_NORMAL, Screen.COLOUR_DEFAULT),
    "meter_bracket": (Screen.COLOUR_WHITE, Screen.A_BOLD, Screen.COLOUR_DEFAULT),
    "meter_value": (8, Screen.A_BOLD, Screen.COLOUR_DEFAULT),
    "tab": (Screen.COLOUR_BLACK, Screen.A_NORMAL, Screen.COLOUR_BLUE),
    "selected_tab": (Screen.COLOUR_BLACK, Screen.A_NORMAL, Screen.COLOUR_GREEN),
}

THEMES["htop"] = HTOP_PALETTE

default_colors = (231, Screen.A_NORMAL, 234)

# a palette of colors following the Spyderbat color scheme
SPYDERBAT_PALETTE = {
    "background": default_colors,
    "borders": default_colors,
    "button": (231, Screen.A_NORMAL, 67),
    "control": (75, Screen.A_NORMAL, 234),
    "disabled": (231, Screen.A_NORMAL, Screen.COLOUR_MAGENTA),
    "edit_text": (231, Screen.A_NORMAL, 237),
    "field": (231, Screen.A_NORMAL, 234),
    "focus_button": (231, Screen.A_NORMAL, 75),
    "focus_control": (75, Screen.A_NORMAL, 234),
    "focus_edit_text": (75, Screen.A_NORMAL, 237),
    "focus_field": default_colors,
    "focus_readonly": default_colors,
    "invalid": (203, Screen.A_NORMAL, 237),
    "label": default_colors,
    "readonly": default_colors,
    "scroll": default_colors,
    "selected_control": (231, Screen.A_BOLD, 119),
    "selected_field": (231, Screen.A_NORMAL, 67),
    "selected_focus_control": (
        231,
        Screen.A_NORMAL,
        75,
    ),
    "selected_focus_field": (231, Screen.A_NORMAL, 75),
    "shadow": (234, None, 234),
    "title": (231, Screen.A_NORMAL, 243),
    "meter_label": (75, Screen.A_NORMAL, 234),
    "meter_bracket": default_colors,
    "meter_value": (243, Screen.A_BOLD, 234),
    "tab": (231, Screen.A_NORMAL, 237),
    "selected_tab": (231, Screen.A_NORMAL, 243),
}

THEMES["spyderbat"] = SPYDERBAT_PALETTE
