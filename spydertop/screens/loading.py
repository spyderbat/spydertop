#
# loading.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc.  All rights reserved.
#

"""
A loading screen to show progress toward loading a set of records
"""

from asciimatics.screen import Screen
from asciimatics.widgets import Frame, Layout, Label
from asciimatics.exceptions import NextScene
from asciimatics.event import KeyboardEvent
from spydertop.model import AppModel

from spydertop.widgets import Padding, FuncLabel


class LoadingFrame(Frame):
    _model: AppModel
    _label: Label

    def __init__(self, screen: Screen, model: AppModel) -> None:
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

        layout.add_widget(Padding((screen.height - 1) // 2))
        self._label = Label("", align="^")
        layout.add_widget(self._label)
        layout.add_widget(
            FuncLabel(lambda: "Loading time " + str(model.time), align="^")
        )
        layout.add_widget(FuncLabel(lambda: model.state, align="^"))

        self.set_theme(self._model.config["theme"])
        self.fix()

    def update(self, frame_no):
        self.set_theme(self._model.config["theme"])

        # see if the model is done
        if self._model.failed:
            self._model.thread.join()
            raise NextScene("Failure")
        if self._model.loaded:
            self._model.thread.join()
            self._quit()
        else:
            # update the label
            max_bars = int(self._label._w / 3)
            bars = int(self._model.progress * max_bars)
            self._label.text = (
                "Loading: ["
                + ("|" * bars)
                + (" " * (max_bars - bars))
                + f"] {round(self._model.progress*100,1):>5}%"
            )
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
