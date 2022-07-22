#
# widgets.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
A series of useful widgets for displaying htop-like content, including
bar graphs and dynamic labels.
"""

import re
from typing import Callable, List
from asciimatics.widgets import Widget
from asciimatics.parsers import Parser
from asciimatics.strings import ColouredText

from spydertop.utils import CustomTextWrapper, header_bytes, COLOR_REGEX


class Meter(Widget):
    """
    A colored bar graph in the style of htop, using a list of values and colors.

    It requires "meter_label", "meter_bracket", and "meter_value" to be set in the
    theme.
    """

    def __init__(
        self,
        label: str,
        values: List[float],
        total: float,
        important_value: int,
        colors: List[tuple],
        percent=False,
    ):
        """
        :param label: the three-character-wide label for this bar graph, displayed on the left
        :param values: a list of numerical values that determine the color stops for the graph.
            these values are not considered cumulative, and their sum should not exceed `total`
        :param total: the maximum possible sum of values for this metric
        :param important_value: which index in `values` to use for the numerical value shown at
            the end of the bar
        :param colors: a list of (foreground,format,background) values for each portion of the
            bar. This list should be equal in length to `values`
        :param percent: whether the end value should be displayed as a percent or a fraction in
            bytes out of `total`
        """
        super().__init__(name=None, tab_stop=False)

        self._label = label
        self._percent = percent
        self._values = values
        self.colors = colors
        self.total = total
        self.important_value = important_value

    def process_event(self, event):
        return event

    def reset(self):
        pass

    def required_height(self, offset, width):
        return 1  # meters are always 1-line

    def update(self, frame_no):
        """
        Draws the metric onto the screen as:
          LBL[|||||||||||       VALUE]
        with padding before and after.
        """
        padding_start = 2
        padding_end = 1
        label_width = 3

        # draw label
        (color, attr, background) = (
            self._frame.palette["meter_label"]
            if "meter_label" in self._frame.palette
            else self._frame.palette["label"]
        )
        self._frame.canvas.paint(
            (" " * padding_start) + f"{self._label:<{label_width}}",
            self._x,
            self._y,
            color,
            attr,
            background,
        )

        # print frame
        (color, attr, background) = (
            self._frame.palette["meter_bracket"]
            if "meter_bracket" in self._frame.palette
            else self._frame.palette["border"]
        )
        self._frame.canvas.paint(
            "[", self._x + padding_start + label_width, self._y, color, attr, background
        )
        self._frame.canvas.paint(
            "]", self._x + self._w - 1 - padding_end, self._y, color, attr, background
        )

        color, attr, background = (
            self._frame.palette["meter_value"]
            if "meter_value" in self._frame.palette
            else self._frame.palette["background"]
        )
        # early exit if values is empty
        if not self._values:
            end_label = "No data"
            self._frame.canvas.paint(
                end_label,
                self._x + self._w - 1 - len(end_label) - padding_end,
                self._y,
                color,
                attr,
                background,
            )
            return

        # print end label
        if self._percent:
            # convert value to a percentage
            end_label = (
                str(
                    round(
                        sum(self._values[: self.important_value + 1])
                        / self.total
                        * 100,
                        1,
                    )
                )
                + "%"
            )
        else:
            # pretty print value / total
            end_label = f"\
{header_bytes(sum(self._values[:self.important_value+1]))}/{header_bytes(self.total)}"
        self._frame.canvas.paint(
            end_label,
            self._x + self._w - 1 - len(end_label) - padding_end,
            self._y,
            color,
            attr,
            background,
        )

        # print bar
        width = self._w - 2 - padding_start - label_width - padding_end
        for character in range(width):
            chr_val = character / width * self.total
            val_sum = 0

            # find what color the character should be
            for (i, value) in enumerate(self._values):
                val_sum += value
                if chr_val < val_sum:
                    color = self.colors[i]

                    # determine what letter it should be
                    letter = "|"
                    if width - character <= len(end_label):
                        letter = end_label[-(width - character)]

                    self._frame.canvas.paint(
                        letter,
                        self._x + character + 1 + padding_start + label_width,
                        self._y,
                        color,
                        attr,
                        background,
                    )
                    break

    @property
    def value(self):
        """The values of the bar graph."""
        return self._values

    @value.setter
    def value(self, value):
        self._values = value
        if value is not None:
            assert len(value) == len(self.colors)
            assert self.important_value < len(value)
            assert self.total is not None


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

    parser: Parser
    align: str
    generator: Callable[[], str]
    color: str
    indent: str

    def __init__(
        self,
        generator: lambda: str,
        align="<",
        parser=None,
        name=None,
        color="label",
        indent="",
        **kwargs,
    ):
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
                    if self.align == "<"
                    else extra_space // 2
                    if self.align == "^"
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
                    colour_map=line.colour_map if hasattr(line, "colour_map") else None,
                )
                offset += 1

    @property
    def value(self):
        """The text of the label."""
        return self.generator()
