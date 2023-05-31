#
# feedback.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
A feedback screen, allowing users to provide feedback about the application
and providing a collection of links to resources.
"""

from asciimatics.screen import Screen
from asciimatics.widgets import Frame, Layout, TextBox, Button
from asciimatics.exceptions import NextScene

from spydertop.model import AppModel
from spydertop.widgets import FuncLabel, Padding
from spydertop.utils import add_palette
from spydertop.utils.types import ExtendedParser


class FeedbackFrame(Frame):
    """A feedback screen with a collection of support links"""

    _model: AppModel
    _feedback_widget: TextBox

    def __init__(self, screen: Screen, model: AppModel) -> None:
        # pylint: disable=line-too-long
        super().__init__(screen, screen.height, screen.width, reduce_cpu=True)

        single_column = Layout([1])
        self.add_layout(single_column)
        single_column.add_widget(
            FuncLabel(
                lambda: """\
 ⢎⡑ ⡀⢀ ⣀⡀ ⣀⡀ ⢀⡀ ⡀⣀ ⣰⡀
 ⠢⠜ ⠣⠼ ⡧⠜ ⡧⠜ ⠣⠜ ⠏  ⠘⠤

Seeing something strange? Did the bugs get out again? Here’s how to reach us:
""",
            )
        )

        double_column = Layout([1, 1])
        self.add_layout(double_column)

        # left side
        double_column.add_widget(
            FuncLabel(
                lambda: add_palette(
                    """\
Contact:
- Email ${{4}}help@spyderbat.com${{{label}}}
- Slack ${{4}}spyderbatcommunity.slack.com${{{label}}}\
""",
                    model,
                ),
                parser=ExtendedParser(),
            )
        )

        # right side
        double_column.add_widget(
            FuncLabel(
                lambda: add_palette(
                    """\
Helpful Links:
- Product Videos ${{4}}https://www.youtube.com/channel/UCgAujmYaBZxwhvSz6x2362w/${{{label}}}
- How-tos ${{4}}https://spyderbat.com/how-tos/${{{label}}}
- Release Notes and Known Issues ${{4}}https://www.spyderbat.com/release-notes-and-known-issues/${{{label}}}\
""",
                    model,
                ),
                parser=ExtendedParser(),
            ),
            column=1,
        )

        single_column2 = Layout([1])
        self.add_layout(single_column2)
        single_column2.add_widget(
            FuncLabel(
                lambda: """\
 ⡇⢸ ⢀⡀   ⡇ ⢀⡀ ⡀⢀ ⢀⡀   ⣰⡁ ⢀⡀ ⢀⡀ ⢀⣸ ⣇⡀ ⢀⣀ ⢀⣀ ⡇⡠ ⡇
 ⠟⠻ ⠣⠭   ⠣ ⠣⠜ ⠱⠃ ⠣⠭   ⢸  ⠣⠭ ⠣⠭ ⠣⠼ ⠧⠜ ⠣⠼ ⠣⠤ ⠏⠢ ⠅

Help us prioritize our backlog! We have a web of features in our pipeline. \
Your feedback helps us prioritize new features, enhancements, bugs, etc. in \
upcoming releases. Also, if you have ideas or thoughts about your experience \
with Spyderbat, we'd love to hear it! Feedback from early adopters such as \
yourself is essential to helping us improve and create a better experience \
for all. Thank you!
""",
                parser=ExtendedParser(),
            )
        )

        self._feedback_widget = TextBox(10, as_string=True, name="feedback_text")
        single_column2.add_widget(self._feedback_widget)
        single_column2.add_widget(Padding())

        double_column2 = Layout([1, 1])
        self.add_layout(double_column2)
        double_column2.add_widget(
            Button(
                "Cancel",
                self._cancel,
            ),
            column=0,
        )
        double_column2.add_widget(
            Button(
                "Submit Feedback",
                self._submit_feedback,
            ),
            column=1,
        )

        self._model = model
        self.set_theme(model.config["theme"])

        self.fix()

    def update(self, frame_no):
        self.set_theme(self._model.config["theme"])
        return super().update(frame_no)

    def _cancel(self):
        raise NextScene("Main")

    def _submit_feedback(self):
        self._model.submit_feedback(str(self._feedback_widget.value))
        raise NextScene("Main")
