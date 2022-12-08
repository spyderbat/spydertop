#
# failure.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
A failure screen to alert the user that data has failed to load,
and to allow them to recover or quit.
"""

from asciimatics.screen import Screen
from asciimatics.widgets import Frame, Layout, Button
from asciimatics.exceptions import NextScene, StopApplication
from asciimatics.event import KeyboardEvent

from textual.app import ComposeResult
from textual.screen import Screen as TScreen
from textual.widgets import Static
from textual.widgets import Button as TButton

from spydertop.model import AppModel
from spydertop.utils.types import ExtendedParser
from spydertop.widgets import Padding, FuncLabel


class FailureFrame(Frame):
    """A failure screen to alert the user that data has failed to load,
    and to allow them to recover or quit."""

    _model: AppModel
    _time_button: Button

    def __init__(self, screen: Screen, model: AppModel) -> None:
        # pylint: disable=duplicate-code
        super().__init__(
            screen,
            screen.height,
            screen.width,
            has_border=False,
            reduce_cpu=True,
            can_scroll=False,
        )

        self._model = model

        layout = Layout([1])
        self.add_layout(layout)

        layout.add_widget(Padding((screen.height - 1) // 2 - 5))
        layout.add_widget(
            FuncLabel(
                lambda: """\
 ${1,1}⡇⢸ ⣇⡀ ⢀⡀ ⢀⡀ ⣀⡀ ⢀⣀ ⡇
 ${1,1}⠟⠻ ⠇⠸ ⠣⠜ ⠣⠜ ⡧⠜ ⠭⠕ ⠅
 
 Something went wrong, and I can't fix it:""",
                align="^",
                parser=ExtendedParser(),
            )
        )
        layout.add_widget(Padding(1))
        layout.add_widget(
            FuncLabel(
                lambda: f"${{1,1}}{model.failure_reason}",
                align="^",
                parser=ExtendedParser(),
            )
        )
        layout.add_widget(Padding(1))
        layout.add_widget(
            FuncLabel(
                lambda: "What do you want to do?",
                align="^",
            )
        )
        layout.add_widget(Padding(2))

        layout2 = Layout([1])
        self.add_layout(layout2)

        layout2.add_widget(
            Button("Revert to last loaded time", lambda: self._recover("revert"))
        )
        layout2.add_widget(
            Button("Go to the earliest loaded time", lambda: self._recover("reload"))
        )
        self._time_button = Button(
            "",
            lambda: self._recover("retry"),
        )
        layout2.add_widget(Button("Quit", self._quit))

        self.set_theme(model.config["theme"])
        self.fix()

    def update(self, frame_no):
        self.set_theme(self._model.config["theme"])
        self._time_button.text = (
            f"Reload {self._model.time}"
            if self._model.time is not None
            else "Retry loading"
        )
        super().update(frame_no)

    # pylint: disable=duplicate-code
    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code in {ord("q"), ord("Q")}:
                self._quit()
        return super().process_event(event)

    def _recover(self, action: str) -> None:
        self._model.recover(action)
        raise NextScene("Main")

    @staticmethod
    def _quit():
        raise StopApplication("User quit after failure")


# rewrite to use textual


class Failure(TScreen):
    """A failure screen to alert the user that data has failed to load,
    and to allow them to recover or quit."""

    def __init__(self, model: AppModel) -> None:
        super().__init__()
        self.model = model

    def compose(self) -> ComposeResult:
        yield Static(
            """\
[#F56155]⡇⢸ ⣇⡀ ⢀⡀ ⢀⡀ ⣀⡀ ⢀⣀ ⡇[/]
[#F56155]⠟⠻ ⠇⠸ ⠣⠜ ⠣⠜ ⡧⠜ ⠭⠕ ⠅[/]

Something went wrong, and I can't fix it:
"""
        )
        yield Static(id="reason")
        yield Static("What do you want to do?")
        yield TButton("Revert to last loaded time", id="revert")
        yield TButton("Go to the earliest loaded time", id="reload")
        yield TButton("Quit", id="quit")

    def on_mount(self) -> None:
        """Called when the screen is mounted."""
        self.query_one("#reason").update(self.model.failure_reason)  # type: ignore

    async def on_button_pressed(self, event: TButton.Pressed) -> None:
        """Called when a button is pressed."""
        if event.button.id == "revert":
            self.model.recover("revert")
            self.app.switch_screen("Main")
        elif event.button.id == "reload":
            self.model.recover("reload")
            self.app.switch_screen("Main")
        elif event.button.id == "quit":
            await self.app.action_quit()
