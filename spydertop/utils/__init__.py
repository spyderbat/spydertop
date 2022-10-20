#
# __init__.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
Various utilities for spydertop
"""

from datetime import datetime, timezone
from typing import Callable, List, Optional, TypeVar

from asciimatics.widgets.utilities import THEMES

from spydertop.utils.types import DelayedLog

global log  # pylint: disable=global-at-module-level,invalid-name
# the global log object, used everywhere
log = DelayedLog()


T = TypeVar("T")
U = TypeVar("U")


def map_optional(func: Callable[[T], U], value: Optional[T]) -> Optional[U]:
    """Map a function over an optional value, returning None if the value is None"""
    if value is None:
        return None
    return func(value)


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
    return f"${{6}}{hours}h${{7}}{minutes:02d}:{seconds:02d}"


def pretty_datetime(  # pylint: disable=too-many-return-statements
    d_time: datetime,
) -> str:
    """Format a datetime in a short format, and color based on the distance from now"""
    now = datetime.now(tz=d_time.tzinfo)
    delta = now - d_time
    if delta.days == 0:
        if delta.seconds < 60:
            return f"${{2}}{delta.seconds} seconds ago"
        if delta.seconds < 3600:
            return f"${{2}}{delta.seconds // 60} minutes ago"
        return f"${{3}}{delta.seconds // 3600} hours ago"
    if delta.days == 1:
        return "${3}Yesterday"
    if delta.days < 7:
        return f"${{3}}{delta.days} days ago"
    if delta.days < 365:
        return f"${{1}}{delta.days // 7} weeks ago"
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


def header_bytes(n_bytes: int) -> str:
    """Format a number of bytes in a human readable format, without coloring for the header"""
    for suffix in ["", "K", "M", "G", "T"]:
        if n_bytes < 100:
            n_bytes = round(n_bytes, 2)
            return f"{n_bytes}{suffix}"
        n_bytes = int(n_bytes / 1024)
    return f"{n_bytes}P"


def add_palette(text, model, **kwargs) -> str:
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


def get_timezone(model):
    """Get the timezone based on the config"""
    return (
        timezone.utc if model.config["utc_time"] else datetime.now().astimezone().tzinfo
    )


def is_event_in_widget(event, widget):
    """Determine if the event is in the area of the widget"""
    return (
        widget.rebase_event(event).x < 0
        or widget.rebase_event(event).x > widget.canvas.width
        or widget.rebase_event(event).y < 0
        or widget.rebase_event(event).y > widget.canvas.height
    )


def calculate_widths(screen_width, desired_columns: List[int]) -> List[int]:
    """Manually calculate the widths for a Layout, as the default has rounding errors."""
    total_desired = sum(desired_columns)
    actual_widths = [int(x / total_desired * screen_width) for x in desired_columns]
    actual_widths[-1] += screen_width - sum(actual_widths)
    return actual_widths
