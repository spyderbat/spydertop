#
# modals.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
A set of modal frames used for temporary input
"""

import re
from typing import Callable, Optional
from asciimatics.widgets import Frame, Text, Layout, Widget
from asciimatics.screen import Screen
from asciimatics.event import KeyboardEvent, MouseEvent
from spydertop.constants import COLOR_REGEX
from spydertop.utils import is_event_in_widget
from spydertop.utils.types import ExtendedParser

from spydertop.widgets import FuncLabel


class InputModal(Frame):
    """A modal frame for receiving input from the user"""

    _text_input: Widget
    _on_change: Callable[[Optional[str]], None]
    _on_submit: Callable[[str], None]
    _on_death: Callable[[], None]

    def __init__(  # pylint: disable=too-many-arguments
        self,
        screen: Screen,
        value=None,
        width=40,
        theme="htop",
        on_change: Optional[Callable[[Optional[str]], None]] = None,
        on_submit: Optional[Callable[[str], None]] = None,
        on_death: Optional[Callable[[], None]] = None,
        widget=Text,
        **kwargs,
    ) -> None:
        """
        :param screen: The screen to draw on
        :param value: The initial value of the input
        :param width: The width of the input modal
        :param theme: The theme to use
        :param on_change: A function to call when the value changes
        :param on_submit: A function to call when the user submits the input
        :param on_death: A function to call when the modal is closed
        :param widget: The widget to use for the input
        :param kwargs: Any additional keyword arguments to pass to the widget
        """

        # handle on_change to call with the value
        if on_change:
            self._text_input = widget(
                on_change=(
                    lambda: on_change(self._text_input.value)
                    if self._text_input.is_valid
                    else None
                ),
                **kwargs,
            )
        else:
            self._text_input = widget(**kwargs)

        super().__init__(
            screen,
            self._text_input.required_height(0, width) + 2,
            width + 2,
            is_modal=True,
            reduce_cpu=True,
            can_scroll=False,
        )
        self._on_change = on_change or (lambda _: None)
        self._on_submit = on_submit or (lambda _: None)
        self._on_death = on_death or (lambda: None)

        layout = Layout([1], fill_frame=True)
        self.add_layout(layout)

        layout.add_widget(self._text_input)

        self.set_theme(theme)

        self.fix()
        if value:
            self._text_input.value = value

    def process_event(self, event):
        assert self.scene is not None
        if isinstance(event, KeyboardEvent):
            if event.key_code == ord("\n") or event.key_code == Screen.KEY_F10:
                if self._text_input.is_valid:
                    self._on_submit(self._text_input.value)
                self.scene.remove_effect(self)
                self._on_death()
                return None
            if event.key_code == Screen.KEY_ESCAPE:
                # on escape, clear the input
                self._on_change(None)
                self.scene.remove_effect(self)
                self._on_death()
                return None
        elif isinstance(event, MouseEvent):
            if is_event_in_widget(event, self) and (event.buttons != 0):
                # when a click is outside the modal, close it
                self._on_change(None)
                self.scene.remove_effect(self)
                self._on_death()
                return None

        return super().process_event(event)


class NotificationModal(Frame):
    """A modal frame for displaying a notification"""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        screen: Screen,
        text: str,
        parent: Frame,
        frames: Optional[int] = 20,
        max_width: Optional[int] = None,
        **kwargs,
    ) -> None:
        """
        :param screen: The screen to draw on
        :param text: The text to display
        :param parent: The parent frame, used for passing events and the theme
        :param frames: The number of frames to display the notification (None for until closed)
        """
        if max_width is None:
            max_width = int(screen.width) // 2
        self._label = FuncLabel(lambda: text, parser=ExtendedParser(), indent="    ")
        max_len = min(
            max(len(re.sub(COLOR_REGEX, "", line)) for line in text.split("\n")),
            max_width,
        )
        height = self._label.required_height(0, max_len)
        super().__init__(
            screen,
            height + 2,
            max_len + 2,
            is_modal=True,
            can_scroll=False,
            **kwargs,
        )

        layout = Layout([1])
        self.add_layout(layout)
        self._parent = parent
        layout.add_widget(self._label)
        layout.blur()

        self.delete_count = frames

        self.palette = parent.palette

        self.fix()

    def process_event(self, event):
        assert self.scene is not None
        if isinstance(event, KeyboardEvent):
            if (
                event.key_code == ord("\n")
                or event.key_code == Screen.KEY_ESCAPE
                or self.delete_count is None
            ):
                self.scene.remove_effect(self)
                return None
        if isinstance(event, MouseEvent) and event.buttons != 0:
            self.scene.remove_effect(self)
        return self._parent.process_event(event)

    @property
    def frame_update_count(self):
        # this is needed to cause the frame to be deleted at the proper time
        return 1
