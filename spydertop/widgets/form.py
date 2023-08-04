#
# form.py
#
# Author: Griffith Thomas
# Copyright 2023 Spyderbat, Inc. All rights reserved.
#

"""
This module contains a form layout which creates a collection of typed inputs
from a dictionary of field names and default values.
"""

from typing import Callable, Dict, Optional, Union, TypeVar

from asciimatics.widgets import CheckBox, Layout, Text, Widget, RadioButtons

FormData = Union[str, int, float, bool, set]

T = TypeVar("T")


def value_to_widget(
    label: str, value: T, on_change: Callable[[str, T], None]
) -> Widget:
    """Convert a value to a widget, with a callback to be called when the value changes."""

    widget: Widget = None  # type: ignore

    def on_change_wrapper(value):
        on_change(label, value)

    if isinstance(value, bool):
        # make checkbox
        widget = CheckBox(label, on_change=lambda: on_change_wrapper(widget.value))

    if isinstance(value, set):
        # make radio
        widget = RadioButtons(
            [(x, x) for x in value],
            label=label,
            on_change=lambda: on_change_wrapper(widget.value),
        )

    if isinstance(value, str):
        # make textbox
        widget = Text(label=label, on_change=lambda: on_change_wrapper(widget.value))

    if isinstance(value, float):
        # make numerical input
        def validate(value):
            try:
                _ = float(value)
                return True
            except (ValueError, TypeError):
                return False

        widget = Text(
            label=label,
            validator=validate,
            on_change=lambda: (
                on_change_wrapper(float(widget.value))
                if validate(widget.value)
                else None
            ),
        )

    if isinstance(value, int) and not isinstance(value, bool):
        # make numerical input
        def validate_int(value):
            try:
                _ = int(value)
                return True
            except (ValueError, TypeError):
                return False

        widget = Text(
            label=label,
            validator=validate_int,
            on_change=lambda: (
                on_change_wrapper(int(widget.value))
                if validate_int(widget.value)
                else None
            ),
        )

    if widget is not None:
        #     if isinstance(widget, Text):
        #         widget.value = str(value)
        #     elif not isinstance(widget, RadioButtons):
        #         widget.value = value
        return widget

    raise ValueError(f"Invalid value type: {type(value)}")


class Form(Layout):
    """
    A colored bar graph in the style of htop, using a list of values and colors.

    The form layout is determined by the initial data that is passed to it. The
    form will create a widget for each key in the data dictionary, and will use
    the value of the key to determine the type of widget to create. When the user
    submits the form, the data dictionary will be updated and passed to an
    on_submit callback function.
    """

    _data: Dict[str, FormData]
    _widgets: Dict[str, Widget]

    def __init__(self, initial_data: Optional[Dict[str, FormData]] = None):
        """
        :param initial_data: The initial data to populate the form with. The keys
            of the dictionary will be used as the labels for the form fields, and
            the values will be used to determine the type of widget to create.
        :param on_submit: A callback function that will be called when the user
            submits the form. The callback will be passed the current data of the
            form.
        :param on_cancel: A callback function that will be called when the user
            cancels the form.
        """
        super().__init__([1])

        self._data = initial_data if initial_data is not None else {}

        # build the form
        for key, value in self.data.items():
            widget = value_to_widget(key, value, self._on_change)

            self._widgets[key] = widget
            self.add_widget(widget, column=0)

    @property
    def data(self) -> Dict[str, FormData]:
        """The current data of the form."""
        return self._data

    def set_value(self, label: str, value: FormData):
        """Set the value of a form field."""
        self._widgets[label].value = value
        self._data[label] = value

    def _on_change(self, label: str, value: FormData):
        """Update the data dictionary when a form field changes."""
        self._data[label] = value
