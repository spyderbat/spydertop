#
# meter.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
This module contains a meter widget which displays a range of values
similarly to HTOP's CPU meter.
"""

from typing import List, Optional, Union

from asciimatics.widgets import Widget

from spydertop.utils import header_bytes


class Meter(Widget):
    """
    A colored bar graph in the style of htop, using a list of values and colors.

    It requires "meter_label", "meter_bracket", and "meter_value" to be set in the
    theme.
    """

    total: Optional[float]

    def __init__(  # pylint: disable=too-many-arguments
        self,
        label: str,
        values: Union[List[float], List[int]],
        total: float,
        important_value: int,
        colors: List[int],
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

    # pylint: disable=duplicate-code
    def process_event(self, event):
        return event

    def reset(self):
        pass

    def required_height(self, offset, width):
        return 1  # meters are always 1-line

    def update(self, frame_no):  # pylint: disable=too-many-locals
        """
        Draws the metric onto the screen as:
          LBL[|||||||||||       VALUE]
        with padding before and after.
        """
        assert self._frame is not None

        padding_start = 2
        padding_end = 1
        label_width = len(self._label)

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
        if not self._values or not self.total:
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
            # typing seems to not understand that sum works on lists of floats
            sum_bytes = header_bytes(sum(self._values[: self.important_value + 1]))  # type: ignore
            end_label = f"{sum_bytes}/{header_bytes(int(self.total))}"
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
            for i, value in enumerate(self._values):
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
    def value(self, value: Optional[Union[List[float], List[int]]]):
        self._values = value
        if value is not None:
            assert len(value) == len(self.colors)
            assert self.important_value < len(value)
            assert self.total is not None
