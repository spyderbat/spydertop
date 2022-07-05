#
# __init__.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc.  All rights reserved.
#

"""
The screens module contains all of the frames in the application and
the start_screen function, which initiates the main portion of the application
"""

import os
from typing import Dict
import yaml

from asciimatics.screen import ManagedScreen
from asciimatics.scene import Scene
from asciimatics.exceptions import ResizeScreenError
from spydertop.config import Config

from spydertop.model import AppModel
from spydertop.columns import (
    CONNECTION_COLUMNS,
    FLAG_COLUMNS,
    LISTENING_SOCKET_COLUMNS,
    PROCESS_COLUMNS,
    SESSION_COLUMNS,
)
from spydertop.screens.loading import LoadingFrame
from spydertop.screens.main import MainFrame
from spydertop.screens.help import HelpFrame
from spydertop.screens.failure import FailureFrame
from spydertop.utils import log


def dump_columns(columns) -> Dict[str, bool]:
    """
    Dumps the columns to a dictionary, where the key is the column
    name and the value is whether or not the column is enabled
    """
    return {column[0]: column[5] for column in columns}


def start_screen(config: Config) -> None:
    """Initializes and manages the asciimatics screen"""
    log.info(config)

    last_scene = None
    model = AppModel(config)
    model.init()

    while True:
        try:
            with ManagedScreen() as screen:
                screen.play(
                    [
                        Scene([LoadingFrame(screen, model)], -1, name="Loading"),
                        Scene([MainFrame(screen, model)], -1, name="Main"),
                        Scene([HelpFrame(screen, model)], -1, name="Help"),
                        Scene([FailureFrame(screen, model)], -1, name="Failure"),
                    ],
                    stop_on_resize=True,
                    start_scene=last_scene,
                    allow_int=True,
                )
            # If we get here, we have exited the screen,
            # it is safe to print logs
            log.dump()

            # save settings which should persist across sessions
            with open(
                os.path.join(os.environ.get("HOME"), ".sbapi/.spydertop-settings.yaml"),
                "w",
            ) as file:
                exclude_settings = ["filter", "sort_column", "sort_ascending", "play"]
                for key in exclude_settings:
                    if key in config.settings:
                        del config.settings[key]
                yaml.dump(
                    {
                        "settings": config.settings,
                        "processes": dump_columns(PROCESS_COLUMNS),
                        "sessions": dump_columns(SESSION_COLUMNS),
                        "flags": dump_columns(FLAG_COLUMNS),
                        "connections": dump_columns(CONNECTION_COLUMNS),
                        "listening": dump_columns(LISTENING_SOCKET_COLUMNS),
                    },
                    file,
                )
            config.cleanup()

            log.info("Gracefully exiting")
            log.dump()
            return
        except ResizeScreenError as e:
            log.info(f"Screen resized")
            log.dump()
            last_scene = e.scene
