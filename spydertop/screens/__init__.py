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

from datetime import timedelta
from os import environ
import os
import sys
from typing import Callable, List
from asciimatics.screen import ManagedScreen, Screen
from asciimatics.scene import Scene
from asciimatics.exceptions import ResizeScreenError
import yaml

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
from spydertop.state import ExitReason, State
from spydertop.utils import log
from spydertop.constants import API_LOG_TYPES
from spydertop.utils.types import LoadArgs


def start_screen(
    config: Config,
    args: LoadArgs,
) -> None:
    """Initializes and manages the asciimatics screen"""
    while True:
        model = start_config_wizard(config, args)
        model.log_api(
            API_LOG_TYPES["startup"], {"term": environ.get("TERM", "unknown")}
        )
        model.init(args.duration or timedelta(minutes=config.settings.default_duration_minutes))

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

        if model.state.exit_reason == ExitReason.QUIT:
            break
        if args.input is not None:
            log.warn(
                "Cannot return to configuration wizard when"
                " reading from a file. Exiting instead"
            )
            break
        log.info("Returning to configuration wizard")

    # save settings which should persist across sessions
    config.save()

    model.log_api(
        API_LOG_TYPES["shutdown"],
        {"failure_state": model.failure_reason if model.failed else "None"},
    )

    log.info("Gracefully exiting")


def start_config_wizard(
    config: Config,
    args: LoadArgs,
) -> AppModel:
    """
    Starts a new Asciimatics screen with the configuration wizard,
    returning the new config
    """
    log.debug(
        "Configuration wizard started with initial config:\n",
        yaml.dump(config.as_dict()),
    )
    state = State()
    if args.input is None:
        model = None

        run_screens(
            lambda screen: [
                Scene(
                    [ConfigurationFrame(screen, config, state, args)],
                    -1,
                    name="Config",
                )
            ]
        )
        if state.exit_reason == ExitReason.QUIT:
            sys.exit(0)

        if config.active_context is None:
            log.err("No context selected, exiting")
            sys.exit(1)
        secret = config.contexts[config.active_context].get_secret(config.directory)
        if secret is None:
            log.err(
                "Failed to get secret "
                f"'{config.contexts[config.active_context].secret_name}', exiting"
            )
            sys.exit(1)
        model = AppModel(config.settings, state, RecordPool(secret, args.output))
    else:
        model = AppModel(config.settings, state, RecordPool(args.input, args.output))

    return model


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
