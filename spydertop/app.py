#
# app.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
Contains the main application object
"""

from os import environ

from textual.app import App

from spydertop.config import Config
from spydertop.constants import API_LOG_TYPES
from spydertop.model import AppModel
from spydertop.screens.config import ConfigScreen
from spydertop.screens.failure import Failure
from spydertop.screens.feedback import FeedbackScreen
from spydertop.screens.loading import Loading
from spydertop.screens.main import Main
from spydertop.screens.quit import Quit


class SpydertopApp(App):
    """The main spydertop app class"""

    config: Config
    model: AppModel

    CSS_PATH = "styles/app.css"

    def on_mount(self) -> None:
        """Called when the app is mounted"""
        assert self.config is not None

        # create the model
        self.model = AppModel(self.config)
        self.model.log_api(
            API_LOG_TYPES["startup"], {"term": environ.get("TERM", "unknown")}
        )

        # create and mount the screens
        self.install_screen(ConfigScreen(self.model), "config")
        self.install_screen(Loading(self.model), "loading")
        self.install_screen(Failure(self.model), "failure")
        self.install_screen(FeedbackScreen(self.model), "feedback")
        self.install_screen(Main(self.model), "main")
        self.install_screen(Quit(self.model), "quit")

        # set the initial screen
        self.push_screen("config")

    def set_config(self, config: Config) -> "SpydertopApp":
        """Set the config for the app"""
        self.config = config
        return self


def run(**_kwargs) -> None:
    """Run the app"""

    app = SpydertopApp()
    app.set_config(
        Config(
            None,
            None,
            # pylint: disable=consider-using-with
            open("examples/minikube-sock-shop.json.gz", "r", encoding="utf-8"),
            None,
            None,
            900,
            True,
            "NOTSET+",
        )
    )
    app.run()
