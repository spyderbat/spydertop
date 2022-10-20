#
# footer.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
The main frame's footer, handling the creation and resetting of the buttons widgets
as well as click handlers.
"""

from typing import Callable, List, Tuple

from asciimatics.widgets import Button, Layout, Frame, Widget


class Footer(Layout):
    """A footer layout to handle the creation and resetting of the buttons widgets
    as well as click handlers."""

    _buttons: List = []
    _on_clicks: List = []
    _end_widget: Widget
    _frame: Frame
    _widths: List[int]

    def __init__(
        self,
        columns: List[int],
        frame: Frame,
        buttons: List[Tuple[str, Callable]],
        end_widget: Widget,
    ):
        super().__init__(columns)
        self._widths = columns
        self._frame = frame
        self.set_buttons(buttons, end_widget)

    def set_buttons(self, buttons, end_widget=None):
        """Set the buttons to be displayed in the footer."""
        self.clear_widgets()
        self._buttons = []
        self._on_clicks = []
        for (i, (title, on_click)) in enumerate(buttons):
            # strip title to fit in the width
            width = self._widths[i]
            title = title[: width - 2]
            button = Button(title, on_click, f"F{i+1}", add_box=False)
            button.custom_colour = "focus_button"
            self._on_clicks.append(on_click)
            self._buttons.append(button)
            self.add_widget(button, column=i)

        if end_widget:
            self._end_widget = end_widget
        self.add_widget(self._end_widget, column=10)

    def click(self, index):
        """Trigger a click event on the button at the given index."""
        self._on_clicks[index]()

    def change_button_text(self, old_text, new_text):
        """Change the text of the button at the given index."""
        try:
            index = [b.text for b in self._buttons].index(old_text)
        except ValueError:
            return
        self._buttons[index].text = new_text
