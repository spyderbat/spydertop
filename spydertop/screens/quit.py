#
# quit.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
This screen is started when the user decides to quit the application.
It handles any before-quit events.
"""

import os
from typing import Any, Callable, Dict
from asciimatics.screen import Screen
from asciimatics.widgets import Frame, Layout, TextBox, Button
from asciimatics.exceptions import StopApplication

from spydertop.model import AppModel
from spydertop.widgets import FuncLabel, Padding
from spydertop.utils.types import ExtendedParser


class QuitFrame(Frame):
    """A quitting screen that provides a last chance to submit feedback for new users"""

    _model: AppModel
    _single_column = Layout([1])
    _double_column = Layout([1, 1])
    _needs_update = True
    _state: Dict[str, Any]
    _set_state: Callable

    def __init__(self, screen: Screen, model: AppModel) -> None:
        # pylint: disable=line-too-long
        super().__init__(screen, screen.height, screen.width, reduce_cpu=True)
        self._model = model
        self.add_layout(self._single_column)
        self.add_layout(self._double_column)
        self._state, self._set_state = model.use_state(
            "quit_frame",
            {
                "feedback_text": "",
                "enjoyed_spydertop": None,
            },
        )

    def update(self, frame_no):
        self.set_theme(self._model.config["theme"])
        if self._needs_update:
            self.build_feedback_widget()
            self.reset()
            self.fix()
            self._needs_update = False
        return super().update(frame_no)

    def build_feedback_widget(self):
        """Construct the current view of the feedback widget"""
        self._single_column.clear_widgets()
        self._double_column.clear_widgets()

        # quit early if the user has already submitted feedback
        # or do not have a settings file (i.e. they have not yet installed)
        if (
            self._model.config["has_submitted_feedback"]
            and self._state["enjoyed_spydertop"] is None
        ) or not os.path.exists(
            os.path.join(
                os.environ.get("HOME"), ".spyderbat-api/.spydertop-settings.yaml"  # type: ignore
            )
        ):
            raise StopApplication("User Quit and does not need feedback")

        self._single_column.add_widget(
            FuncLabel(
                lambda: """\
 ⣏⡉ ⢀⡀ ⢀⡀ ⢀⣸ ⣇⡀ ⢀⣀ ⢀⣀ ⡇⡠
 ⠇  ⠣⠭ ⠣⠭ ⠣⠼ ⠧⠜ ⠣⠼ ⠣⠤ ⠏⠢
""",
                parser=ExtendedParser(),
            )
        )

        if self._state["enjoyed_spydertop"] is None:
            self._single_column.add_widget(
                FuncLabel(
                    lambda: """\
Have you enjoyed using Spydertop?
""",
                )
            )

            def answer(value):
                self._set_state(enjoyed_spydertop=value)
                self._model.submit_feedback(
                    "User " + ("enjoyed" if value else "did not enjoy") + " Spydertop"
                )
                self._needs_update = True

            self._double_column.add_widget(Button("Yes", lambda: answer(True)), 0)
            self._double_column.add_widget(Button("No", lambda: answer(False)), 1)
            return

        self._single_column.add_widget(
            FuncLabel(
                lambda: """\
Do you have any feedback about your experience with Spydertop? \
If you are too busy now, you can always send us your thoughts \
later through the Support and Feedback menu on the help screen.
""",
            )
        )

        self._single_column.add_widget(Padding())

        textbox = TextBox(
            10,
            as_string=True,
            name="feedback_text",
            on_change=lambda: self._set_state(feedback_text=textbox.value),
        )
        self._single_column.add_widget(textbox)

        self._double_column.add_widget(
            Button(
                "Submit Feedback",
                self._submit_feedback,
            ),
            column=1,
        )
        self._double_column.add_widget(
            Button(
                "Quit",
                self._quit,
            ),
            column=0,
        )

    def _quit(self):
        raise StopApplication("User Quit without submitting feedback")

    def _submit_feedback(self):
        self._model.submit_feedback(self._state["feedback_text"])
        raise StopApplication("User Quit after submitting feedback")
