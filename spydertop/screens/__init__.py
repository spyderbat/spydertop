#
# __init__.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
The screens module contains all of the frames in the application and
the start_screen function, which initiates the main portion of the application
"""

from os import environ
import os
from asciimatics.screen import ManagedScreen
from asciimatics.scene import Scene
from asciimatics.exceptions import ResizeScreenError
from spydertop.config import Config

from spydertop.model import AppModel
from spydertop.screens.loading import LoadingFrame
from spydertop.screens.main import MainFrame
from spydertop.screens.help import HelpFrame
from spydertop.screens.failure import FailureFrame
from spydertop.screens.config import ConfigurationFrame
from spydertop.screens.feedback import FeedbackFrame
from spydertop.screens.quit import QuitFrame
from spydertop.utils import log
from spydertop.constants import API_LOG_TYPES


def start_screen(config: Config) -> None:
    """Initializes and manages the asciimatics screen"""
    log.debug("Initial config:\n", config)

    last_scene = None
    model = AppModel(config)
    model.log_api(API_LOG_TYPES["startup"], {"term": environ.get("TERM", "unknown")})

    # set delay for escape key
    os.environ.setdefault("ESCDELAY", "10")

    while True:
        try:
            with ManagedScreen() as screen:
                screen.play(
                    [
                        Scene([ConfigurationFrame(screen, model)], -1, name="Config"),
                        Scene([LoadingFrame(screen, model)], -1, name="Loading"),
                        Scene([MainFrame(screen, model)], -1, name="Main"),
                        Scene([HelpFrame(screen, model)], -1, name="Help"),
                        Scene([FailureFrame(screen, model)], -1, name="Failure"),
                        Scene([FeedbackFrame(screen, model)], -1, name="Feedback"),
                        Scene([QuitFrame(screen, model)], -1, name="Quit"),
                    ],
                    stop_on_resize=True,
                    start_scene=last_scene,
                    allow_int=True,
                )

            # save settings which should persist across sessions
            config.dump()
            config.cleanup()

            model.log_api(
                API_LOG_TYPES["shutdown"],
                {"failure_state": model.failure_reason if model.failed else "None"},
            )

            log.info("Gracefully exiting")
            # If we get here, we have exited the screen,
            # it is safe to print logs
            log.dump()
            return
        except ResizeScreenError as exc:
            log.info("Screen resized")
            log.dump()
            last_scene = exc.scene
