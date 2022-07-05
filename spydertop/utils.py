#
# utils.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc.  All rights reserved.
#

"""
Various utilities for spydertop
"""

import traceback
import click
from typing import Callable, List, Tuple

from asciimatics.screen import Screen
from asciimatics.widgets.utilities import THEMES

# matches all of the escape sequences that are used in the Asciimatics parser
COLOR_REGEX = r"\${(\d+)(, ?\d+(, ?\d+)?)?}"
# the page size to use when converting to bytes
PAGE_SIZE = 4096


def pretty_time(time: float) -> str:
    """Format a time in a human readable format, similar to the format used in htop"""
    seconds = int(time) % 60
    minutes = int(time / 60) % 60
    hours = int(time / 3600)
    centiseconds = int(time * 100) % 100
    if hours == 0:
        if time < 0.1:
            millis = int(time * 1_000)
            if millis == 0:
                microseconds = int(time * 1_000_000)
                return f"{microseconds}μs"
            return f"{millis}ms"
        return f"{minutes}:{seconds:02d}.{centiseconds:02d}"
    else:
        return f"${{6}}{hours}h${{7}}{minutes:02d}:{seconds:02d}"


def pretty_address(ip: int, port: int) -> str:
    """Format an IP address and port number in a fancy, colored format"""
    return f"{ip:>15}${{8}}:${{7,1}}{port:<5}"


def convert_to_seconds(value: str) -> float:
    """Convert a time string to seconds, with an optional suffix unit"""
    try:
        timestamp = float(value)
    except ValueError as e:
        # assume that this is a custom time value
        time_type = value[-1]
        timestamp = float(value[:-1])
        # convert to seconds
        switch = {"s": 1, "m": 60, "h": 3600, "d": 3600 * 24, "y": 3600 * 24 * 365}
        timestamp *= switch[time_type]
    return timestamp


def pretty_bytes(bytes: int) -> str:
    """Format a number of bytes in a human readable format, with coloring"""
    for (suffix, color) in [("", None), ("K", None), ("M", 6), ("G", 2), ("T", 1)]:
        if bytes < 1000:
            if suffix == "K" or suffix == "":
                return f"{int(bytes)}{suffix}"
            else:
                precision = 2 if bytes < 10 else 1 if bytes < 100 else 0
                return f"${{{color}}}{bytes:.{precision}f}{suffix}"
        bytes /= 1024
    return f"${{1,1}}{bytes}P"


def header_bytes(bytes: int) -> str:
    """Format a number of bytes in a human readable format, without coloring for the header"""
    for suffix in ["", "K", "M", "G", "T"]:
        if bytes < 100:
            bytes = round(bytes, 2)
            return f"{bytes}{suffix}"
        bytes /= 1024
    return f"{bytes}P"


def add_palette(text, model, **kwargs) -> Callable[[], str]:
    """formats the text with a few keys from the palette"""
    palette = THEMES[model.config["theme"]]
    # this is necessary because the palette may be a defaultdict
    concrete_palette = {
        "background": palette["background"][0],
        "borders": palette["borders"][0],
        "label": palette["label"][0],
        "meter_label": (
            palette["meter_label"] if "meter_label" in palette else palette["label"]
        )[0],
    }
    # -1 is not a valid color in the parser, but stands for the default color
    # assume that the default color is white
    for key, value in concrete_palette.items():
        if value == -1:
            concrete_palette[key] = 7
    return text.format(**concrete_palette, **kwargs)


# a palette of colors imitating the default look of htop
HTOP_PALETTE = {
    "background": (Screen.COLOUR_DEFAULT, Screen.A_NORMAL, Screen.COLOUR_DEFAULT),
    "borders": (Screen.COLOUR_DEFAULT, Screen.A_NORMAL, Screen.COLOUR_DEFAULT),
    "button": (Screen.COLOUR_BLACK, Screen.A_NORMAL, Screen.COLOUR_WHITE),
    "control": (Screen.COLOUR_CYAN, Screen.A_NORMAL, Screen.COLOUR_DEFAULT),
    "disabled": (Screen.COLOUR_DEFAULT, Screen.A_NORMAL, Screen.COLOUR_MAGENTA),
    "edit_text": (Screen.COLOUR_BLACK, Screen.A_NORMAL, Screen.COLOUR_CYAN),
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
    "selected_field": (Screen.COLOUR_BLACK, Screen.A_NORMAL, Screen.COLOUR_WHITE),
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
    "edit_text": (Screen.COLOUR_BLACK, Screen.A_NORMAL, 75),
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


class DelayedLog:
    """
    Saves a list of logs and dumps them to the console
    on graceful exit or on manual dump call.

    This is used to circumvent asciimatics' screen, which would
    interfere with any normal logging method.
    """

    _logs: List[Tuple[int, str]] = []
    log_level: int

    LOG_LEVELS = ["DEBUG", "INFO", "WARN", "ERR"]
    DEBUG = 0
    INFO = 1
    WARN = 2
    ERR = 3
    LOG_FG_COLORS = ["black", "black", "black", "black"]
    LOG_BG_COLORS = ["blue", "white", "yellow", "red"]

    def __init__(self):
        # require log_level to be set before logging
        pass

    def dump(self):
        for (level, log) in self._logs:
            for line in log.split("\n"):
                click.echo(
                    click.style(
                        f"[{self.LOG_LEVELS[level]}]",
                        fg=self.LOG_FG_COLORS[level],
                        bg=self.LOG_BG_COLORS[level],
                    ),
                    nl=False,
                )
                click.echo(f": {line}")
        self._logs = []

    def log(self, message: str, log_level: int = 0):
        if log_level >= self.log_level:
            self._logs.append((log_level, str(message)))

    def info(self, message: str):
        self.log(message, self.INFO)

    def warn(self, message: str):
        self.log(message, self.WARN)

    def err(self, message: str):
        self.log(message, self.ERR)

    def traceback(self, exception: Exception):
        self._logs.append(
            (
                0,
                "".join(
                    traceback.format_exception(
                        type(exception), exception, exception.__traceback__
                    )
                ),
            )
        )

    def __del__(self):
        self.dump()

    @property
    def lines(self) -> str:
        return [line for level, line in self._logs if level >= self.log_level]


global log
# the global log object, used everywhere
log = DelayedLog()
