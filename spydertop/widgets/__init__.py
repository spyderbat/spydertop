#
# __init__.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
A series of useful widgets for displaying htop-like content, including
bar graphs and dynamic labels.
"""

import re
from typing import Callable, Optional
from asciimatics.widgets import Widget
from asciimatics.parsers import Parser
from asciimatics.strings import ColouredText

from spydertop.utils.types import Alignment, CustomTextWrapper
from spydertop.constants import COLOR_REGEX

# reexports
from spydertop.widgets.table import Table
from spydertop.widgets.meter import Meter


class Padding(Widget):
    """A simple, empty widget that takes up space"""

    _height: int

    def __init__(self, height=1):
        super().__init__(None, tab_stop=False)
        self.height = height

    def process_event(self, event):
        return event

    def reset(self):
        pass

    def required_height(self, offset, width):
        return self._height

    def update(self, frame_no):
        pass

    @property
    def height(self):
        """The height of the padding, in lines."""
        return self._height

    @height.setter
    def height(self, height):
        self._height = max(round(height), 0)

    @property
    def value(self):
        """Padding has no value."""
        return None


class FuncLabel(Widget):
    """
    A label widget which dynamically determines its own text based on a generator
    function at display time. It also supports parsing colors
    """

    parser: Optional[Parser]
    align: Alignment
    generator: Callable[[], str]
    color: str
    indent: str

    def __init__(
        self,
        generator: Callable[[], str],
        align: Alignment = Alignment.LEFT,
        parser=None,
        name=None,
        color="label",
        indent="",
        **kwargs,
    ):  # pylint: disable=too-many-arguments
        """
        :param generator: a function which generates the text to display on screen.
            This function is assumed to have no side effects, and can be run often
        :param align: an alignment string, either '<', '^' or '>'
        :param parser: a parser to use when coloring the generated text
        :param color: the theme color to use by default. Must be a key in the theme.
        """
        super().__init__(name, tab_stop=False)

        self.generator = generator
        self.align = align
        self.parser = parser
        self.color = color
        self.indent = indent
        self.wrapper_kwargs = kwargs

    def process_event(self, event):
        return event

    def reset(self):
        pass

    def required_height(self, offset, width):
        text = self.generator()
        height = 0
        wrapper = CustomTextWrapper(
            width=width, subsequent_indent=self.indent, **self.wrapper_kwargs
        )
        for para in text.split("\n"):
            if para == "":
                height += 1
                continue
            height += len(wrapper.wrap(para))
        return height

    def update(self, frame_no):
        assert self._frame is not None
        (color, attr, background) = self._frame.palette[self.color]
        text = self.generator()
        wrapper = CustomTextWrapper(
            width=self._w, subsequent_indent=self.indent, **self.wrapper_kwargs
        )

        offset = 0
        for para in text.split("\n"):
            if para == "":
                offset += 1
                continue
            for line in wrapper.wrap(para):
                # first, the space needed to pad the text to the correct alignment
                # is calculated.
                extra_space = self._w - len(re.sub(COLOR_REGEX, "", line))
                left_space = (
                    0
                    if self.align == Alignment.LEFT
                    else extra_space // 2
                    if self.align == Alignment.CENTER
                    else extra_space
                )
                spaces = " " * left_space
                line = f"{spaces}{line}"

                # then, the text is colored if a parser is provided
                if self.parser:
                    line = ColouredText(line, self.parser)

                # finally, the text is drawn
                self._frame.canvas.paint(
                    line,
                    self._x,
                    self._y + offset,
                    color,
                    attr,
                    background,
                    colour_map=line.colour_map  # type: ignore
                    if hasattr(line, "colour_map")
                    else None,
                )
                offset += 1

    @property
    def value(self):
        """The text of the label."""
        return self.generator()
