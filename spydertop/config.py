#
# config.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc.  All rights reserved.
#

import gzip
import logging
import os
import click
import yaml

from typing import Any, Dict, Optional, TextIO, Union
from datetime import datetime, timedelta

from spydertop.columns import (
    CONNECTION_COLUMNS,
    FLAG_COLUMNS,
    LISTENING_SOCKET_COLUMNS,
    PROCESS_COLUMNS,
    SESSION_COLUMNS,
)
from spydertop.utils import log


class Config:
    """
    A container for the various arguments passed in to spydertop
    """

    # inputs
    api_key: str
    org: str
    source: str
    input: Union[str, TextIO] = None
    output: TextIO
    start_time: datetime
    start_duration: timedelta

    # settings
    settings = {
        "hide_threads": True,
        "hide_kthreads": True,
        "sort_ascending": False,
        "sort_column": "CPU%",
        "play": False,
        "play_speed": 1,
        "filter": None,
        "tree": False,
        "collapse_tree": False,
        "theme": "htop",
    }
    settings_changed: bool = False

    def __init__(
        self,
        org: Optional[str],
        source: Optional[str],
        finput: Union[str, TextIO],
        output: TextIO,
        start_time: float,
        duration: int,
        log_level: str,
    ):
        # allow for logging from the underlying library if it is requested
        # FIXME: remove this to get rid of the logging dependency
        if log_level == "ASCIIMATICS":
            log_level = "INFO"
            logging.basicConfig(level=logging.DEBUG, filename="spydertop.log")

        log.log_level = log.LOG_LEVELS.index(log_level)

        try:
            config_default = self._load_config()
        except FileNotFoundError:
            raise click.ClickException(
                "Failed to parse config: $HOME/.sbapi/config.yaml does not exist"
            )
        except yaml.YAMLError as exc:
            raise click.ClickException("Failed to parse config: \n" + str(exc))
        except KeyError:
            raise click.ClickException(
                "Failed to parse config: \nSection default does not exist"
            )

        # open the cached settings file if it exists, but fail quietly
        # as the user does not need to know about this
        try:
            with open(
                os.path.join(os.environ.get("HOME"), ".sbapi/.spydertop-settings.yaml")
            ) as file:
                settings_file = yaml.safe_load(file)
            # load all the column enabled settings
            for key in settings_file["settings"]:
                if key in self.settings:
                    self.settings[key] = settings_file["settings"][key]

            def load_enabled(name, columns):
                if name in settings_file:
                    for key in settings_file[name]:
                        names = [row[0] for row in columns]
                        if key in names:
                            col = columns[names.index(key)]
                            columns[names.index(key)] = (
                                col[0],
                                col[1],
                                col[2],
                                col[3],
                                col[4],
                                settings_file[name][key],
                            )

            load_enabled("processes", PROCESS_COLUMNS)
            load_enabled("connections", CONNECTION_COLUMNS)
            load_enabled("listening_sockets", LISTENING_SOCKET_COLUMNS)
            load_enabled("sessions", SESSION_COLUMNS)
            load_enabled("flags", FLAG_COLUMNS)

        except Exception as e:
            log.info("Failed to load cached settings: " + str(e))

        try:
            self.api_key = config_default["api_key"]
            self.org = org or config_default["org"]
            self.source = source or config_default["source"]
            self.input = (
                finput
                or "https://" + config_default["api_url"]
                or "https://api.prod.spyderbat.com"
            )
            self.output = output
            self.start_time = datetime.fromtimestamp(start_time or 0.0)
            self.start_duration = timedelta(0, duration, 0)
        except KeyError as e:
            raise click.ClickException(
                f"Failed to parse config: \nSection default does not contain {e.args[0]}, and it was not specified as a command-line option"
            )
        except Exception as e:
            log.err("An unexpected error occurred while parsing config.")
            log.traceback(e)
            log.dump()
            raise click.ClickException(
                f"Failed to load configuration: \nAn unexpected exception occurred."
            )

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        """Loads the configuration file at $HOME/.sbapi/config.yaml"""
        home = os.environ.get("HOME")
        config_file_loc = os.path.join(home, ".sbapi/config.yaml")

        with open(config_file_loc) as file:
            file_config = yaml.safe_load(file)

        return file_config["default"]

    # allow for config to be accessed as a dictionary
    # this is just for convenient access to the settings
    def __getitem__(self, key: str) -> Any:
        if key not in self.settings:
            return None
        return self.settings[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.settings[key] = value
        self.settings_changed = True

    def __str__(self) -> str:
        return f"""\
config:
    api_key: {self.api_key[:3]}...{self.api_key[-3:]}
    org: {self.org}
    source: {self.source}
    input: {self.input}
    start_time: {self.start_time}
    start_duration: {self.start_duration}\
        """

    def cleanup(self):
        # input is not closed for us because it is opened manually
        # this means we need to close it manually
        if self.input and not isinstance(self.input, str):
            self.input.close()
        # if the output is a gzip file, we need to close it manually
        if hasattr(self.output, "close"):
            self.output.close()
