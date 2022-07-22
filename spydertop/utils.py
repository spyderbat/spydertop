#
# utils.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
Various utilities for spydertop
"""

import bisect
import re
import traceback
from datetime import datetime
from textwrap import TextWrapper
from typing import Callable, List, Tuple

import click
from asciimatics.screen import Screen
from asciimatics.widgets.utilities import THEMES
from asciimatics.parsers import Parser

# matches all of the escape sequences that are used in the Asciimatics parser
COLOR_REGEX = r"\${(-?\d+)(, ?(\d+)(, ?(-?\d+))?)?}"
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
            milliseconds = int(time * 1_000)
            if milliseconds == 0:
                microseconds = int(time * 1_000_000)
                return f"{microseconds}μs"
            return f"{milliseconds}ms"
        return f"{minutes}:{seconds:02d}.{centiseconds:02d}"
    else:
        return f"${{6}}{hours}h${{7}}{minutes:02d}:{seconds:02d}"


def pretty_datetime(d_time: datetime) -> str:
    """Format a datetime in a short format, and color based on the distance from now"""
    now = datetime.now(tz=d_time.tzinfo)
    delta = now - d_time
    if delta.days == 0:
        if delta.seconds < 60:
            return f"${{2}}{delta.seconds} seconds ago"
        elif delta.seconds < 3600:
            return f"${{2}}{delta.seconds // 60} minutes ago"
        else:
            return f"${{3}}{delta.seconds // 3600} hours ago"
    elif delta.days == 1:
        return "${3}Yesterday"
    elif delta.days < 7:
        return f"${{3}}{delta.days} days ago"
    elif delta.days < 365:
        return f"${{1}}{delta.days // 7} weeks ago"
    else:
        return f"${{1}}{delta.days // 365} years ago"


def pretty_address(ip_addr: int, port: int) -> str:
    """Format an IP address and port number in a fancy, colored format"""
    return f"{ip_addr:>15}${{8}}:${{7,1}}{port:<5}"


def convert_to_seconds(value: str) -> float:
    """Convert a time string to seconds, with an optional suffix unit"""
    try:
        timestamp = float(value)
    except ValueError:
        # assume that this is a custom time value
        time_type = value[-1]
        timestamp = float(value[:-1])
        # convert to seconds
        switch = {"s": 1, "m": 60, "h": 3600, "d": 3600 * 24, "y": 3600 * 24 * 365}
        timestamp *= switch[time_type]
    return timestamp


def pretty_bytes(n_bytes: int) -> str:
    """Format a number of bytes in a human readable format, with coloring"""
    for (suffix, color) in [("", None), ("K", None), ("M", 6), ("G", 2), ("T", 1)]:
        if n_bytes < 1000:
            if suffix == "K" or suffix == "":
                return f"{int(n_bytes)}{suffix}"
            else:
                precision = 2 if n_bytes < 10 else 1 if n_bytes < 100 else 0
                return f"${{{color}}}{n_bytes:.{precision}f}{suffix}"
        n_bytes /= 1024
    return f"${{1,1}}{n_bytes}P"


def header_bytes(n_bytes: int) -> str:
    """Format a number of bytes in a human readable format, without coloring for the header"""
    for suffix in ["", "K", "M", "G", "T"]:
        if n_bytes < 100:
            n_bytes = round(n_bytes, 2)
            return f"{n_bytes}{suffix}"
        n_bytes /= 1024
    return f"{n_bytes}P"


def add_palette(text, model, **kwargs) -> Callable[[], str]:
    """formats the text with a few keys from the palette"""
    palette = THEMES[model.config["theme"]]
    # this is necessary because the palette may be a defaultdict
    concrete_palette = {
        "background": palette["background"][0],
        "borders": palette["borders"][0],
        "button": palette["button"][0],
        "button_bg": palette["button"][2],
        "label": palette["label"][0],
        "meter_label": (palette.get("meter_label", palette["label"]))[0],
    }
    return text.format(**concrete_palette, **kwargs)


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

API_LOG_TYPES = {
    "startup": "SpydertopStartup",
    "shutdown": "SpydertopShutdown",
    "loaded_data": "SpydertopLoadedData",
    "orgs": "SpydertopOrgsListed",
    "sources": "SpydertopSourcesListed",
    "feedback": "SendFeedback",
    "navigation": "SpydertopNavigation",
    "account_created": "SpydertopAccountCreated",
}


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
        """Print all logs to the console."""
        for (level, log_lines) in self._logs:
            for line in log_lines.split("\n"):
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
        """Log a message to the console, by default at DEBUG level."""
        if log_level >= self.log_level:
            self._logs.append((log_level, str(message)))

    def debug(self, message: str):
        """Log an info message to the console."""
        self.log(message, self.DEBUG)

    def info(self, message: str):
        """Log an info message to the console."""
        self.log(message, self.INFO)

    def warn(self, message: str):
        """Log a warning message to the console."""
        self.log(message, self.WARN)

    def err(self, message: str):
        """Log an error message to the console."""
        self.log(message, self.ERR)

    def traceback(self, exception: Exception):
        """Log a traceback to the console."""
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
    def lines(self) -> List[str]:
        """All logs within the log level as a list"""
        return [line for level, line in self._logs if level >= self.log_level]


global log  # pylint: disable=global-at-module-level,invalid-name
# the global log object, used everywhere
log = DelayedLog()


class CustomTextWrapper(TextWrapper):
    """
    A custom text wrapper that handles asciimatics' color escape codes,
    removing them from width calculations and carrying them over from
    line to line.
    """

    def __init__(
        self,
        width: int,
        initial_indent: str = "",
        subsequent_indent: str = "",
        expand_tabs: bool = True,
        replace_whitespace: bool = False,
        fix_sentence_endings: bool = False,
        break_long_words: bool = True,
        drop_whitespace: bool = True,
        break_on_hyphens: bool = True,
        tabsize: int = 8,
    ) -> None:
        # for simplicity, this does not support max_lines
        super().__init__(
            width,
            initial_indent,
            subsequent_indent,
            expand_tabs,
            replace_whitespace,
            fix_sentence_endings,
            break_long_words,
            drop_whitespace,
            break_on_hyphens,
            tabsize,
            max_lines=None,
        )

    def _wrap_chunks(self, chunks: list[str]) -> list[str]:
        """
        Override the default _wrap_chunks to remove the color escape codes
        from the width calculations.

        This is heavily based on the original implementation in the standard
        library.
        """
        # -- from standard implementation --

        if self.width <= 0:
            raise ValueError(f"invalid width {self.width} (must be > 0)")

        lines = []
        cur_style = ""

        chunks.reverse()

        # -- end standard implementation --

        # lines loop
        while chunks:
            # the line should always start with the previous style
            cur_line = []
            cur_len = 0

            # -- from standard implementation --

            # Figure out which static string will prefix this line.
            if lines:
                indent = self.subsequent_indent
            else:
                indent = self.initial_indent

            # Maximum width for this line.
            width = self.width - len(indent)

            # First chunk on line is whitespace -- drop it, unless this
            # is the very beginning of the text (ie. no lines started yet).
            if self.drop_whitespace and chunks[-1].strip() == "" and lines:
                del chunks[-1]

            # -- end standard implementation --

            cur_line.append(indent)
            cur_line.append(cur_style)

            # words loop
            while chunks:
                matches = re.findall(f"({COLOR_REGEX})", chunks[-1])
                length = len(chunks[-1])
                if matches != []:
                    # update the current style
                    cur_style = matches[-1][0]
                    # don't count the color escape code in the width
                    for match in matches:
                        length -= len(match[0])

                if cur_len + length <= width:
                    cur_line.append(chunks.pop())
                    cur_len += length
                else:
                    break

            # The current line is full, and the next chunk is too big to
            # fit on *any* line (not just this one).
            if chunks and len(chunks[-1]) > width:
                color_match = re.match(COLOR_REGEX, chunks[-1])
                if color_match is not None:
                    cur_style = color_match.group()
                    cur_line.append(cur_style)
                    chunks[-1] = chunks[-1][len(color_match.group()) :]
                self._handle_long_word(chunks, cur_line, cur_len, width)
                cur_len = sum(map(len, cur_line))

            # -- from standard implementation --

            # If the last chunk on this line is all whitespace, drop it.
            if self.drop_whitespace and cur_line and cur_line[-1].strip() == "":
                cur_len -= len(cur_line[-1])
                del cur_line[-1]

            # -- end standard implementation --

            # add the current line to the result
            lines.append("".join(cur_line))
        return lines


class TimeSpanTracker:
    """A class designed to keep track of which time spans have been loaded.
    It can take a pair of datetimes and merge them into the time span list
    using a union operation, and it can take a single datetime and tell
    whether it has been loaded or not."""

    # times is a sorted list of times, which each represent a start or end of a time span
    times = []

    def __init__(self):
        pass

    def add_time_span(self, start, end):
        """Add a time span to the list of time spans."""
        if len(self.times) == 0:
            self.times = [start, end]
            return
        # locate the correct place for the start time
        start_index = bisect.bisect_left(self.times, start)
        inserted = False

        if start_index != len(self.times) and self.times[start_index] == start:
            # the start time is already in the list.
            # If it is an end time, we set the previous time as start.
            # if it is the start time, we do nothing
            if start_index % 2 == 1:
                start_index -= 1
        else:
            # the start time is not in the list.
            # If it is in the middle of a time span, we go back to the previous time;
            # if it is in-between time spans, we insert the start time
            if start_index % 2 == 1:
                start_index -= 1
            else:
                self.times.insert(start_index, start)
                inserted = True

        # locate the correct place for the end time
        end_index = bisect.bisect_left(self.times, end)

        if end_index != len(self.times) and self.times[end_index] == end:
            # the end time is already in the list.
            # If it is a start time, we set the next time as end.
            # if it is the end time, we do nothing
            is_end_offset = 0 if inserted else 1
            if end_index % 2 == is_end_offset:
                end_index += 1
        else:
            # the end time is not in the list.
            # If it is in the middle of a time span, we go forward to the next time;
            # if it is in-between time spans, we insert the end time
            in_the_middle_offset = 0 if inserted else 1
            if end_index % 2 == in_the_middle_offset:
                end_index += 1
            else:
                self.times.insert(end_index, end)

        # we need to remove all the times between the start and end indices
        self.times = self.times[: start_index + 1] + self.times[end_index:]

    def is_loaded(self, time: datetime):
        """Return whether the given time has been loaded."""
        # locate the correct place for the time
        index = bisect.bisect_left(self.times, time)
        # if the index is odd, then it is in the middle of a time span
        return index % 2 == 1 or time in self.times

    def __str__(self) -> str:
        return "".join(
            [
                str(time) + (" <-> " if i % 2 == 0 else " | ")
                for i, time in enumerate(self.times)
            ]
        )


class BetterDefaultDict(dict):
    """A default dict that uses a lambda that takes in the key to
    determine the default value"""

    def __init__(self, default_factory, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_factory = default_factory

    def __missing__(self, key):
        self[key] = self.default_factory(key)
        return self[key]

    # overload copy to use the same default factory
    def copy(self):
        return BetterDefaultDict(self.default_factory, self)


class ExtendedParser(Parser):
    """An extended version of the AsciimaticsParser which allows for
    all color codes, including resetting"""

    _color_regex = re.compile(COLOR_REGEX)

    def parse(self):
        if self._state.attributes:
            yield (0, Parser.CHANGE_COLOURS, tuple(self._state.attributes))
        offset = last_offset = 0
        while len(self._state.text) > 0:
            match = self._color_regex.match(str(self._state.text))

            if match is None:
                yield (last_offset, Parser.DISPLAY_TEXT, self._state.text[0])
                self._state.text = self._state.text[1:]
                offset += 1
                last_offset = offset
            else:
                attributes = (
                    int(match.group(1)),
                    int(match.group(3) or 0),
                    int(match.group(5)) if match.group(5) is not None else None,
                )
                yield (last_offset, Parser.CHANGE_COLOURS, attributes)
                offset += len(match.group())
                self._state.text = self._state.text[len(match.group()) :]
