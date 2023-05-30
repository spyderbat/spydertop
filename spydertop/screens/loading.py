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
from spydertop.model import AppModel

from spydertop.constants import COLOR_REGEX
from spydertop.utils import log
from spydertop.utils.types import Alignment, ExtendedParser
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
                align=Alignment.CENTER,
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

        self._label = FuncLabel(
            update_bar, align=Alignment.CENTER, parser=ExtendedParser()
        )
        layout.add_widget(self._label)
        layout.add_widget(
            FuncLabel(
                lambda: "${8,1} " + log.get_last_line(log.INFO),
                align=Alignment.CENTER,
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
