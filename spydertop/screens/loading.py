#
# loading.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
A loading screen to show progress toward loading a set of records
"""

import re
from asciimatics.screen import Screen
from asciimatics.widgets import Frame, Layout, Label
from asciimatics.exceptions import NextScene
from asciimatics.event import KeyboardEvent

from textual import events
from textual.screen import Screen as TScreen
from textual.widgets import Static
from textual.message import Message, MessageTarget
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive

from spydertop.model import AppModel
from spydertop.constants import COLOR_REGEX
from spydertop.utils.types import ExtendedParser
from spydertop.widgets import FuncLabel

LOGO = """\
${4}        ▂▄▅▆${0,2,4}▂▂▃▃▂${4,2,-1}▇▆▅▄▂        
${4}     ▂▅${0,2,4}▂▄▆${4,2,-1}      ▄${0,2,4} ${4,2,-1}▌ ${0,2,4}▆▄▂${4,2,-1}▅▂     
${4}   ▗▆${0,2,4}▃${4,2,-1}        ▗${0,2,4}▘   ${4,2,-1}▄▃▁  ${0,2,4}▃${4,2,-1}▆▖   
  ${0,2,4}▘▗${4,2,-1}▘       ▃${0,2,4}▘       ${4,2,-1}▘   ▝${0,2,4}▖▝${4,2,-1}  
 ${0,2,4}▘▗${4,2,-1}       ▃▆${0,2,4}        ${4,2,-1}▊      ${0,2,4}▖▝${4,2,-1} 
${0,2,4}▌ ${4,2,-1}      ▄${0,2,4}           ${4,2,-1}▋       ${0,2,4} ${4,2,-1}▌
${0,2,4} ${4,2,-1}▌      ${0,2,4}▅            ${4,2,-1}▖      ${0,2,4}▌ ${4,2,-1}
${0,2,4} ${4,2,-1}▍        ${0,2,4}▅          ▅${4,2,-1}      ${0,2,4}▋ ${4,2,-1}
${0,2,4} ${4,2,-1}▌          ${0,2,4}▅        ${4,2,-1}       ${0,2,4}▌ ${4,2,-1}
${0,2,4}▌ ${4,2,-1}        ▖  ${0,2,4}▍        ${4,2,-1}▃     ${0,2,4} ${4,2,-1}▌
 ${0,2,4}▖▝${4,2,-1}      ${0,2,4}▊ ▝${4,2,-1}▃${0,2,4}          ${4,2,-1}▅▖  ${0,2,4}▘▗${4,2,-1} 
  ${0,2,4}▖▝${4,2,-1}▖ ▗▄${0,2,4}                 ▝▘▗${4,2,-1}  
${4}   ▝${0,2,4}▂${4,2,-1}▅ ${0,2,4}▅▄▄▄▃▃▃▂           ${4,2,-1}▘   
     ${0,2,4}▆▃${4,2,-1}▆▄▂        ${0,2,4}▆▅╾╴ ▃▆${4,2,-1}     
        ${0,2,4}▆▄▃▂${4,2,-1}▆▆▅▅▆▆${0,2,4}▂▃▄▆${4,2,-1}        
"""

BIG_NAME = """\
${8}░${4}█▀▀${8}░${4}█▀█${8}░${4}█${8}░${4}█${8}░${4}█▀▄${8}░${4}█▀▀${8}░${4}█▀▄${8}░${4}▀█▀${8}░${4}█▀█${8}░${4}█▀█
${8}░${4}▀▀█${8}░${4}█▀▀${8}░░${4}█${8}░░${4}█${8}░${4}█${8}░${4}█▀▀${8}░${4}█▀▄${8}░░${4}█${8}░░${4}█${8}░${4}█${8}░${4}█▀▀
${8}░${4}▀▀▀${8}░${4}▀${8}░░░░${4}▀${8}░░${4}▀▀${8}░░${4}▀▀▀${8}░${4}▀${8}░${4}▀${8}░░${4}▀${8}░░${4}▀▀▀${8}░${4}▀${8}░░
"""

HUGE_NAME = """\
${4}███████${8}╗${4}██████${8}╗ ${4}██${8}╗   ${4}██${8}╗${4}██████${8}╗ ${4}███████${8}╗${4}██████${8}╗ ${4}████████${8}╗ ${4}██████${8}╗ ${4}██████${8}╗ 
${4}██${8}╔════╝${4}██${8}╔══${4}██${8}╗╚${4}██${8}╗ ${4}██${8}╔╝${4}██${8}╔══${4}██${8}╗${4}██${8}╔════╝${4}██${8}╔══${4}██${8}╗╚══${4}██${8}╔══╝${4}██${8}╔═══${4}██${8}╗${4}██${8}╔══${4}██${8}╗
${4}███████${8}╗${4}██████${8}╔╝ ╚${4}████${8}╔╝ ${4}██${8}║  ${4}██${8}║${4}█████${8}╗  ${4}██████${8}╔╝   ${4}██${8}║   ${4}██${8}║   ${4}██${8}║${4}██████${8}╔╝
${8}╚════${4}██${8}║${4}██${8}╔═══╝   ╚${4}██${8}╔╝  ${4}██${8}║  ${4}██${8}║${4}██${8}╔══╝  ${4}██${8}╔══${4}██${8}╗   ${4}██${8}║   ${4}██${8}║   ${4}██${8}║${4}██${8}╔═══╝ 
${4}███████${8}║${4}██${8}║        ${4}██${8}║   ${4}██████${8}╔╝${4}███████${8}╗${4}██${8}║  ${4}██${8}║   ${4}██${8}║   ╚${4}██████${8}╔╝${4}██${8}║     
${8}╚══════╝╚═╝        ╚═╝   ╚═════╝ ╚══════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝     
"""


class LoadingFrame(Frame):
    """A loading screen, displaying a dynamic logo and a progress bar.
    This screen is shown when the model is in a loading state, fetching
    data and processing records."""

    _model: AppModel
    _label: Label

    def __init__(self, screen: Screen, model: AppModel) -> None:
        # pylint: disable=duplicate-code
        super().__init__(
            screen,
            screen.height,
            screen.width,
            has_border=False,
            can_scroll=False,
        )

        self._model = model

        layout = Layout([1], fill_frame=True)
        self.add_layout(layout)

        layout.add_widget(
            FuncLabel(
                self.update_logo,
                align="^",
                parser=ExtendedParser(),
                drop_whitespace=False,
            )
        )

        def update_bar():
            # update the label
            max_bars = int(self.screen.width / 3)
            bars = int(self._model.progress * max_bars)
            return (
                "${-1}Loading: ${8}[${4}"
                + ("|" * bars)
                + (" " * (max_bars - bars))
                + f"${{8}}]${{-1}} {round(self._model.progress*100,1):>5}%"
            )

        self._label = FuncLabel(update_bar, align="^", parser=ExtendedParser())
        layout.add_widget(self._label)
        layout.add_widget(
            FuncLabel(
                lambda: "${8,1}Loading time " + str(model.time)
                if model.time is not None
                else "${8,1}Loading from " + model.config.input.name
                if not isinstance(model.config.input, str)
                else "${8,1}Loading from " + model.config.input,
                align="^",
                parser=ExtendedParser(),
            )
        )

        self.set_theme(self._model.config["theme"])
        self.fix()

    def update_logo(self):
        """Update the logo"""
        if self.screen.width < 80:
            header_padding = max(round(self.screen.height / 2 - 13), 0)
            return ("\n" * header_padding) + LOGO + "\n" + BIG_NAME
        if self.screen.width < 110:
            header_padding = max(round(self.screen.height / 2 - 15), 0)
            return ("\n" * header_padding) + LOGO + "\n" + HUGE_NAME
        header_padding = max(round(self.screen.height / 2 - 9), 0)
        name_len = len(re.sub(COLOR_REGEX, "", HUGE_NAME.split("\n", maxsplit=1)[0]))
        padding = (" " * name_len + "\n") * 5
        extended_huge_name = padding + HUGE_NAME + padding
        return ("\n" * header_padding) + "\n".join(
            [
                logoline + " " + nameline
                for logoline, nameline in zip(
                    LOGO.split("\n"), extended_huge_name.split("\n")
                )
            ]
        )

    def update(self, frame_no):
        self.set_theme(self._model.config["theme"])

        # see if the model is done
        if self._model.thread is not None:
            if self._model.failed:
                self._model.thread.join()
                raise NextScene("Failure")
            if self._model.loaded:
                self._model.thread.join()
                self._quit()
        super().update(frame_no)

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code in {ord("q"), ord("Q")}:
                self._quit()
        return super().process_event(event)

    @staticmethod
    def _quit():
        raise NextScene("Main")

    @property
    def frame_update_count(self):
        # we need to update regularly, because the model loading is asynchronous
        return 1


# rewrite the above screen to use the textual library

LOGO = """\
[#48A3FF on #1E232C]        ▂▄▅▆[#1E232C on #48A3FF]▂▂▃▃▂[#48A3FF on #1E232C]▇▆▅▄▂        
[#48A3FF]     ▂▅[#1E232C on #48A3FF]▂▄▆[#48A3FF on #1E232C]      ▄[#1E232C on #48A3FF] [#48A3FF on #1E232C]▌ [#1E232C on #48A3FF]▆▄▂[#48A3FF on #1E232C]▅▂     
[#48A3FF]   ▗▆[#1E232C on #48A3FF]▃[#48A3FF on #1E232C]        ▗[#1E232C on #48A3FF]▘   [#48A3FF on #1E232C]▄▃▁  [#1E232C on #48A3FF]▃[#48A3FF on #1E232C]▆▖   
  [#1E232C on #48A3FF]▘▗[#48A3FF on #1E232C]▘       ▃[#1E232C on #48A3FF]▘       [#48A3FF on #1E232C]▘   ▝[#1E232C on #48A3FF]▖▝[#48A3FF on #1E232C]  
 [#1E232C on #48A3FF]▘▗[#48A3FF on #1E232C]       ▃▆[#1E232C on #48A3FF]        [#48A3FF on #1E232C]▊      [#1E232C on #48A3FF]▖▝[#48A3FF on #1E232C] 
[#1E232C on #48A3FF]▌ [#48A3FF on #1E232C]      ▄[#1E232C on #48A3FF]           [#48A3FF on #1E232C]▋       [#1E232C on #48A3FF] [#48A3FF on #1E232C]▌
[#1E232C on #48A3FF] [#48A3FF on #1E232C]▌      [#1E232C on #48A3FF]▅            [#48A3FF on #1E232C]▖      [#1E232C on #48A3FF]▌ [#48A3FF on #1E232C]
[#1E232C on #48A3FF] [#48A3FF on #1E232C]▍        [#1E232C on #48A3FF]▅          ▅[#48A3FF on #1E232C]      [#1E232C on #48A3FF]▋ [#48A3FF on #1E232C]
[#1E232C on #48A3FF] [#48A3FF on #1E232C]▌          [#1E232C on #48A3FF]▅        [#48A3FF on #1E232C]       [#1E232C on #48A3FF]▌ [#48A3FF on #1E232C]
[#1E232C on #48A3FF]▌ [#48A3FF on #1E232C]        ▖  [#1E232C on #48A3FF]▍        [#48A3FF on #1E232C]▃     [#1E232C on #48A3FF] [#48A3FF on #1E232C]▌
 [#1E232C on #48A3FF]▖▝[#48A3FF on #1E232C]      [#1E232C on #48A3FF]▊ ▝[#48A3FF on #1E232C]▃[#1E232C on #48A3FF]          [#48A3FF on #1E232C]▅▖  [#1E232C on #48A3FF]▘▗[#48A3FF on #1E232C] 
  [#1E232C on #48A3FF]▖▝[#48A3FF on #1E232C]▖ ▗▄[#1E232C on #48A3FF]                 ▝▘▗[#48A3FF on #1E232C]  
[#48A3FF]   ▝[#1E232C on #48A3FF]▂[#48A3FF on #1E232C]▅ [#1E232C on #48A3FF]▅▄▄▄▃▃▃▂           [#48A3FF on #1E232C]▘   
     [#1E232C on #48A3FF]▆▃[#48A3FF on #1E232C]▆▄▂        [#1E232C on #48A3FF]▆▅╾╴ ▃▆[#48A3FF on #1E232C]     
        [#1E232C on #48A3FF]▆▄▃▂[#48A3FF on #1E232C]▆▆▅▅▆▆[#1E232C on #48A3FF]▂▃▄▆[#48A3FF on #1E232C]        
"""

BIG_NAME = """\
[bold white on #1E232C]░[#48A3FF]█▀▀[bold white on #1E232C]░[#48A3FF]█▀█[bold white on #1E232C]░[#48A3FF]█[bold white on #1E232C]░[#48A3FF]█[bold white on #1E232C]░[#48A3FF]█▀▄[bold white on #1E232C]░[#48A3FF]█▀▀[bold white on #1E232C]░[#48A3FF]█▀▄[bold white on #1E232C]░[#48A3FF]▀█▀[bold white on #1E232C]░[#48A3FF]█▀█[bold white on #1E232C]░[#48A3FF]█▀█
[bold white on #1E232C]░[#48A3FF]▀▀█[bold white on #1E232C]░[#48A3FF]█▀▀[bold white on #1E232C]░░[#48A3FF]█[bold white on #1E232C]░░[#48A3FF]█[bold white on #1E232C]░[#48A3FF]█[bold white on #1E232C]░[#48A3FF]█▀▀[bold white on #1E232C]░[#48A3FF]█▀▄[bold white on #1E232C]░░[#48A3FF]█[bold white on #1E232C]░░[#48A3FF]█[bold white on #1E232C]░[#48A3FF]█[bold white on #1E232C]░[#48A3FF]█▀▀
[bold white on #1E232C]░[#48A3FF]▀▀▀[bold white on #1E232C]░[#48A3FF]▀[bold white on #1E232C]░░░░[#48A3FF]▀[bold white on #1E232C]░░[#48A3FF]▀▀[bold white on #1E232C]░░[#48A3FF]▀▀▀[bold white on #1E232C]░[#48A3FF]▀[bold white on #1E232C]░[#48A3FF]▀[bold white on #1E232C]░░[#48A3FF]▀[bold white on #1E232C]░░[#48A3FF]▀▀▀[bold white on #1E232C]░[#48A3FF]▀[bold white on #1E232C]░░
"""

HUGE_NAME = """\
[#48A3FF]███████[bold white on #1E232C]╗[#48A3FF]██████[bold white on #1E232C]╗ [#48A3FF]██[bold white on #1E232C]╗   [#48A3FF]██[bold white on #1E232C]╗[#48A3FF]██████[bold white on #1E232C]╗ [#48A3FF]███████[bold white on #1E232C]╗[#48A3FF]██████[bold white on #1E232C]╗ [#48A3FF]████████[bold white on #1E232C]╗ [#48A3FF]██████[bold white on #1E232C]╗ [#48A3FF]██████[bold white on #1E232C]╗ 
[#48A3FF]██[bold white on #1E232C]╔════╝[#48A3FF]██[bold white on #1E232C]╔══[#48A3FF]██[bold white on #1E232C]╗╚[#48A3FF]██[bold white on #1E232C]╗ [#48A3FF]██[bold white on #1E232C]╔╝[#48A3FF]██[bold white on #1E232C]╔══[#48A3FF]██[bold white on #1E232C]╗[#48A3FF]██[bold white on #1E232C]╔════╝[#48A3FF]██[bold white on #1E232C]╔══[#48A3FF]██[bold white on #1E232C]╗╚══[#48A3FF]██[bold white on #1E232C]╔══╝[#48A3FF]██[bold white on #1E232C]╔═══[#48A3FF]██[bold white on #1E232C]╗[#48A3FF]██[bold white on #1E232C]╔══[#48A3FF]██[bold white on #1E232C]╗
[#48A3FF]███████[bold white on #1E232C]╗[#48A3FF]██████[bold white on #1E232C]╔╝ ╚[#48A3FF]████[bold white on #1E232C]╔╝ [#48A3FF]██[bold white on #1E232C]║  [#48A3FF]██[bold white on #1E232C]║[#48A3FF]█████[bold white on #1E232C]╗  [#48A3FF]██████[bold white on #1E232C]╔╝   [#48A3FF]██[bold white on #1E232C]║   [#48A3FF]██[bold white on #1E232C]║   [#48A3FF]██[bold white on #1E232C]║[#48A3FF]██████[bold white on #1E232C]╔╝
[bold white on #1E232C]╚════[#48A3FF]██[bold white on #1E232C]║[#48A3FF]██[bold white on #1E232C]╔═══╝   ╚[#48A3FF]██[bold white on #1E232C]╔╝  [#48A3FF]██[bold white on #1E232C]║  [#48A3FF]██[bold white on #1E232C]║[#48A3FF]██[bold white on #1E232C]╔══╝  [#48A3FF]██[bold white on #1E232C]╔══[#48A3FF]██[bold white on #1E232C]╗   [#48A3FF]██[bold white on #1E232C]║   [#48A3FF]██[bold white on #1E232C]║   [#48A3FF]██[bold white on #1E232C]║[#48A3FF]██[bold white on #1E232C]╔═══╝ 
[#48A3FF]███████[bold white on #1E232C]║[#48A3FF]██[bold white on #1E232C]║        [#48A3FF]██[bold white on #1E232C]║   [#48A3FF]██████[bold white on #1E232C]╔╝[#48A3FF]███████[bold white on #1E232C]╗[#48A3FF]██[bold white on #1E232C]║  [#48A3FF]██[bold white on #1E232C]║   [#48A3FF]██[bold white on #1E232C]║   ╚[#48A3FF]██████[bold white on #1E232C]╔╝[#48A3FF]██[bold white on #1E232C]║     
[bold white on #1E232C]╚══════╝╚═╝        ╚═╝   ╚═════╝ ╚══════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝     
"""


class Loading(TScreen):
    """A loading screen, displaying a dynamic logo and a progress bar.
    This screen is shown when the model is in a loading state, fetching
    data and processing records."""

    app_size = reactive(tuple)

    class Progressed(Message):
        """Color selected message."""

        def __init__(self, sender: MessageTarget, progress: float) -> None:
            self.progress = progress
            super().__init__(sender)

    def __init__(self, model: AppModel) -> None:
        super().__init__()
        self._model = model

    def on_mount(self) -> None:
        """When the screen is mounted, initializes app_size"""
        self.app_size = self.app.size
        self.set_interval(1 / 60, self.update_progress)

    def on_resize(self, event: events.Resize) -> None:
        """When the screen is resized, updates app_size, and redraw if needed"""
        if self.app_size != event.size:
            self.app_size = event.size
            # to get compose to be called, we need to remount the screen
            self.app.pop_screen()
            self.app.push_screen(Loading(self._model))

    def compose(self) -> ComposeResult:
        # update the logo
        if self.app.size.width < 80:
            yield Static(LOGO)
            yield Static(BIG_NAME)
        elif self.app.size.width < 110:
            yield Static(LOGO)
            yield Static(HUGE_NAME)
        else:
            yield Horizontal(
                Static(LOGO, id="logo"),
                Static(HUGE_NAME, id="huge-name"),
            )

        yield Static("\n")
        yield ProgressBar(id="progress-bar")

    def update_progress(self):
        """Updates the progress bar"""
        # if we are not mounted, do nothing
        if self.app.screen_stack.count == 0 or self.app.screen_stack[-1] is not self:
            return
        # see if the model is done
        if self._model.thread is not None:
            if self._model.failed:
                self._model.thread.join()
                self.app.switch_screen("failure")
                return
            if self._model.loaded:
                self._model.thread.join()
                self.app.switch_screen("main")
                return
        self.get_child("progress-bar").post_message_no_wait(
            self.Progressed(self, self._model.progress)
        )


class ProgressBar(Static):
    """A simple progress bar"""

    def on_loading_progressed(self, event: Loading.Progressed) -> None:
        """update the progress bar on change"""
        max_bars = int(self.size.width / 3)
        bars = int(event.progress * max_bars)
        loading_text = (
            "Loading: ["
            + ("|" * bars)
            + (" " * (max_bars - bars))
            + f"] {round(event.progress*100,1):>5}%"
        )
        self.update(loading_text)
