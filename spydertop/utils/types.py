#
# types.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
Custom or modified types for use in the application.
"""

import bisect
from datetime import datetime
from enum import Enum
import re
from textwrap import TextWrapper
import traceback
from typing import Dict, List, NewType, Optional, Tuple, Union, Any
import logging

import click
from asciimatics.parsers import Parser

from spydertop.constants import COLOR_REGEX

# custom types for data held in the model
Tree = NewType("Tree", Dict[str, Optional[Tuple[bool, "Tree"]]])
RecordInternal = NewType("RecordInternal", Any)
Record = NewType("Record", Dict[str, RecordInternal])


class APIError(Exception):
    """
    An error that occurs when communicating with the API
    """


# custom types for adding context to values and formatting
class Bytes:
    """A class for formatting bytes in a human readable format"""

    value: int

    def __init__(self, value: Union[int, str]):
        if isinstance(value, str):
            self.value = int(Bytes.parse_bytes(value))
        else:
            self.value = int(value)

    def __str__(self) -> str:
        n_bytes = self.value
        for suffix, color in [("", None), ("K", None), ("M", 6), ("G", 2), ("T", 1)]:
            if n_bytes < 1000:
                if suffix in {"K", ""}:
                    return f"{int(n_bytes)}{suffix}"
                precision = 2 if n_bytes < 10 else 1 if n_bytes < 100 else 0
                return f"${{{color}}}{n_bytes:.{precision}f}{suffix}"
            n_bytes /= 1024
        return f"${{1,1}}{n_bytes}P"

    def __eq__(self, __value: object) -> bool:
        if isinstance(__value, Bytes):
            return self.value == __value.value
        if isinstance(__value, int):
            return self.value == __value
        if isinstance(__value, str):
            return self.value == Bytes.parse_bytes(__value)
        return False

    def __lt__(self, __value: object) -> bool:
        if isinstance(__value, Bytes):
            return self.value < __value.value
        if isinstance(__value, int):
            return self.value < __value
        if isinstance(__value, str):
            return self.value < Bytes.parse_bytes(__value)
        return False

    def __le__(self, __value: object) -> bool:
        return self < __value or self == __value

    def __gt__(self, __value: object) -> bool:
        return not self <= __value

    def __ge__(self, __value: object) -> bool:
        return not self < __value

    @staticmethod
    def parse_bytes(value: str) -> int:
        """Parse a string into bytes"""
        if value.endswith("B"):
            value = value[:-1]
        if value.endswith("K"):
            return int(float(value[:-1]) * 1024)
        if value.endswith("M"):
            return int(float(value[:-1]) * 1024 * 1024)
        if value.endswith("G"):
            return int(float(value[:-1]) * 1024 * 1024 * 1024)
        if value.endswith("T"):
            return int(float(value[:-1]) * 1024 * 1024 * 1024 * 1024)
        return int(value)


class Alignment(Enum):
    """The alignment of a column"""

    LEFT = "<"
    RIGHT = ">"
    CENTER = "^"

    def __str__(self) -> str:
        return self.value


class Status(Enum):
    """The status of a process"""

    RUNNING = "R"
    SLEEPING = "S"
    WAITING = "D"
    ZOMBIE = "Z"
    STOPPED = "T"
    TRACING_STOP = "t"
    PAGING = "W"
    DEAD = "X"
    WAKE_KILL = "K"
    WAKING = "W"
    PARKED = "P"
    UNKNOWN = "?"

    def __lt__(self, other: "Status") -> bool:
        return self.value < other.value

    def __gt__(self, other: "Status") -> bool:
        return self.value > other.value

    def __le__(self, other: "Status") -> bool:
        return self.value <= other.value

    def __ge__(self, other: "Status") -> bool:
        return self.value >= other.value

    def __str__(self) -> str:
        return self.value


class Severity(Enum):
    """Severity levels for flags."""

    INFO = -1
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3

    def __lt__(self, other: "Severity") -> bool:
        return self.value < other.value

    def __gt__(self, other: "Severity") -> bool:
        return self.value > other.value

    def __le__(self, other: "Severity") -> bool:
        return self.value <= other.value

    def __ge__(self, other: "Severity") -> bool:
        return self.value >= other.value


class DelayedLog:
    """
    Saves a list of logs and dumps them to the console
    on graceful exit or on manual dump call.

    This is used to circumvent asciimatics' screen, which would
    interfere with any normal logging method.
    """

    _logs: List[Tuple[int, str, datetime]] = []
    log_level: int
    logger: Optional[logging.Logger] = None

    TRACEBACK = logging.DEBUG - 1
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARN = logging.WARN
    ERR = logging.ERROR
    LOG_COLORS = {
        logging.DEBUG - 1: "black",
        logging.DEBUG: "blue",
        logging.INFO: "cyan",
        logging.WARN: "yellow",
        logging.ERROR: "red",
    }

    def __init__(self):
        # require log_level to be set before logging
        logging.addLevelName(self.TRACEBACK, "TRACEBACK")

    def initialize_development_logging(self):
        """Initialize logging for development purposes, saving to a file."""
        logging.basicConfig(level=self.log_level, filename="spydertop.log")
        self.logger = logging.getLogger("spydertop")
        # disable noisy logging for asciimatics
        logging.getLogger("asciimatics").setLevel(logging.WARNING)

    def dump(self):
        """Print all logs to the console."""
        for level, log_lines, time in self._logs:
            if level >= self.log_level:
                for line in log_lines.split("\n"):
                    click.echo(
                        click.style(
                            f"[{logging.getLevelName(level)}]".ljust(9),
                            fg=self.LOG_COLORS.get(level, None),
                        ),
                        nl=False,
                    )
                    click.echo(time.strftime("%H:%M:%S") + " " + line)
        self._logs = []

    def log(self, *messages: Any, log_level: int = logging.NOTSET):
        """Log a message to the console, by default at DEBUG level."""
        line = " ".join([str(_) for _ in messages])
        time = datetime.now()
        if self.logger is not None:
            self.logger.log(log_level, "%.3f %s", time.timestamp(), line)
        self._logs.append((log_level, line, time))

    def debug(self, *messages: Any):
        """Log an info message to the console."""
        self.log(*messages, log_level=self.DEBUG)

    def info(self, *messages: Any):
        """Log an info message to the console."""
        self.log(*messages, log_level=self.INFO)

    def warn(self, *messages: Any):
        """Log a warning message to the console."""
        self.log(*messages, log_level=self.WARN)

    def err(self, *messages: Any):
        """Log an error message to the console."""
        self.log(*messages, log_level=self.ERR)

    def traceback(self, exception: Exception):
        """Log a traceback to the console."""
        self.log(
            "".join(
                traceback.format_exception(
                    type(exception), exception, exception.__traceback__
                )
            ),
            log_level=self.TRACEBACK,
        )

    def __del__(self):
        self.dump()

    def get_last_line(self, log_level: Optional[int] = None) -> str:
        """All logs within the log level as a list"""
        if log_level is None:
            log_level = self.log_level
        filtered_logs = [line for level, line, _ in self._logs if level >= log_level]
        if filtered_logs:
            return filtered_logs[-1]
        return ""


class CustomTextWrapper(TextWrapper):
    """
    A custom text wrapper that handles asciimatics' color escape codes,
    removing them from width calculations and carrying them over from
    line to line.
    """

    def __init__(  # pylint: disable=too-many-arguments
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

    def _wrap_chunks(  # pylint: disable=too-many-branches
        self, chunks: List[str]
    ) -> List[str]:
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
                cur_len = sum(map(len, cur_line), 0)

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

    def is_loaded(self, time: float):
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
        if self._state is None or self._state.text is None:
            return
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
