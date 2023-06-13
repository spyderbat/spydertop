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
from pathlib import Path
import sys
from typing import Callable, List, Optional, TextIO, Union
from asciimatics.screen import ManagedScreen, Screen
from asciimatics.scene import Scene
from asciimatics.exceptions import ResizeScreenError

from spydertop.config.config import Config
from spydertop.model import AppModel
from spydertop.recordpool import RecordPool
from spydertop.screens.loading import LoadingFrame
from spydertop.screens.main import MainFrame
from spydertop.screens.help import HelpFrame
from spydertop.screens.failure import FailureFrame
from spydertop.screens.config import ConfigurationFrame
from spydertop.screens.feedback import FeedbackFrame
from spydertop.screens.quit import QuitFrame
from spydertop.state import State
from spydertop.utils import log
from spydertop.constants import API_LOG_TYPES


def start_screen(
    config: Config,
    config_path: Path,
    state: State,
    input_file: Union[str, TextIO],
    output: Optional[TextIO] = None,
) -> None:
    """Initializes and manages the asciimatics screen"""
    log.debug("Initial config:\n", config)

    model = start_config_wizard(config_path, state, input_file, output)
    model.log_api(API_LOG_TYPES["startup"], {"term": environ.get("TERM", "unknown")})

    # set delay for escape key
    os.environ.setdefault("ESCDELAY", "10")

    run_screens(
        lambda screen: [
            Scene([LoadingFrame(screen, model)], -1, name="Loading"),
            Scene([MainFrame(screen, model)], -1, name="Main"),
            Scene([HelpFrame(screen, model)], -1, name="Help"),
            Scene([FailureFrame(screen, model)], -1, name="Failure"),
            Scene([FeedbackFrame(screen, model)], -1, name="Feedback"),
            Scene([QuitFrame(screen, model)], -1, name="Quit"),
        ]
    )

    # save settings which should persist across sessions
    config.save_to_directory(config_path)

    model.log_api(
        API_LOG_TYPES["shutdown"],
        {"failure_state": model.failure_reason if model.failed else "None"},
    )

    log.info("Gracefully exiting")


def start_config_wizard(
    config_dir: Path,
    state: State,
    input_file: Union[str, TextIO],
    output: Optional[TextIO] = None,
) -> AppModel:
    """
    Starts a new Asciimatics screen with the configuration wizard,
    returning the new config
    """
    config = Config.load_from_directory(config_dir)
    log.debug("Configuration wizard started with initial config:\n", config)
    if isinstance(input_file, str):
        model = None

        run_screens(
            lambda screen: [
                Scene(
                    [ConfigurationFrame(screen, config, state)],
                    -1,
                    name="Config",
                )
            ]
        )
        if config.active_context is None:
            log.err("No context selected, exiting")
            sys.exit(1)
        secret = config.contexts[config.active_context].get_secret()
        if secret is not None:
            model = AppModel(config.settings, state, RecordPool(secret, output))
    else:
        model = AppModel(config.settings, state, RecordPool(input_file, output))
    if model is None:
        log.err("Failed to create model, exiting")
        sys.exit(1)
    return model


# def show_context_screen(config: Config) -> Context:
#     """
#     Shows a series of screens that walk the user through
#     selecting or setting up a context
#     """

#     data = Context(secret_name="", org_uid=None, source=None)

#     run_screens(
#         lambda screen: [
#             Scene(
#                 [
#                     FormFrame(
#                         screen,
#                         data,
#                         "Enter the name of the secret to use",
#                     )
#                 ],
#                 -1,
#                 name="Config",
#             )
#         ]
#     )


def run_screens(build_screens: Callable[[Screen], List[Scene]]):
    """Runs the given screens in a managed screen"""
    last_scene = None

    # set delay for escape key
    os.environ.setdefault("ESCDELAY", "10")

    while True:
        try:
            with ManagedScreen() as screen:
                screen.play(
                    scenes=build_screens(screen),
                    stop_on_resize=True,
                    start_scene=last_scene,
                    allow_int=True,
                )
            # If we get here, we have exited the screen,
            # it is safe to print logs
            log.dump()
            return
        except ResizeScreenError as exc:
            log.info("Screen resized")
            log.dump()
            last_scene = exc.scene
