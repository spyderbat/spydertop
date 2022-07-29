#
# config.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
Configuration object and associated functions
"""

import logging
import os
from typing import Any, Dict, Optional, TextIO, Union
from datetime import datetime, timedelta

import yaml
import click

from spydertop.columns import (
    CONNECTION_COLUMNS,
    FLAG_COLUMNS,
    LISTENING_SOCKET_COLUMNS,
    PROCESS_COLUMNS,
    SESSION_COLUMNS,
)
from spydertop.utils import log


def dump_columns(columns) -> Dict[str, bool]:
    """
    Dumps the columns to a dictionary, where the key is the column
    name and the value is whether or not the column is enabled
    """
    return {column[0]: column[5] for column in columns}


class Config:
    """
    A container for the various arguments passed in to spydertop
    """

    # inputs
    api_key: Optional[str]
    org: Optional[str]
    machine: Optional[str]
    input: Union[str, TextIO]
    output: Optional[TextIO]
    start_time: Optional[datetime]
    start_duration: timedelta

    # user confirmation
    org_confirmed: bool = False
    source_confirmed: bool = False
    has_config_file: bool = False

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
        "follow_record": False,
        "utc_time": False,
        "tab": "processes",
        "theme": "htop",
        "has_submitted_feedback": False,
    }
    settings_changed: bool = False

    def __init__(
        self,
        org: Optional[str],
        source: Optional[str],
        f_input: Union[str, TextIO],
        output: TextIO,
        start_time: float,
        duration: int,
        confirm: bool,
        log_level: str,
    ):
        # allow for logging from the underlying library if it is requested
        if log_level == "ASCIIMATICS":
            log_level = "DEBUG"
            logging.basicConfig(level=logging.DEBUG, filename="spydertop.log")

        log.log_level = log.LOG_LEVELS.index(log_level)

        try:
            config_default = self._load_config()
            self.has_config_file = True
        except FileNotFoundError:
            config_default = {}
        except yaml.YAMLError as exc:
            raise click.ClickException("Failed to parse config: \n" + str(exc)) from exc
        except KeyError as exc:
            raise click.ClickException(
                "Failed to parse config: \nSection default does not exist"
            ) from exc
        except Exception as exc:  # pylint: disable=broad-except
            config_default = {}

        # open the cached settings file if it exists, but fail quietly
        # as the user does not need to know about this
        try:
            with open(
                os.path.join(
                    os.environ.get("HOME"), ".spyderbat-api/.spydertop-settings.yaml"
                ),
                encoding="utf-8",
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
        except Exception as exc:  # pylint: disable=broad-except
            log.info("Failed to load cached settings: " + str(exc))

        try:
            self.api_key = config_default.get("api_key", None)
            self.org = org or config_default.get("org", None)
            self.machine = source or config_default.get("machine", None)
            # command-line arguments are from the user, so are considered confirmed
            self.org_confirmed = (org is not None) or not confirm
            self.source_confirmed = (source is not None) or not confirm
            self.input = (
                f_input
                or (
                    "https://" + config_default["api_url"]
                    if "api_url" in config_default
                    else None
                )
                or "https://api.spyderbat.com"
            )
            self.output = output
            self.start_time = datetime.fromtimestamp(start_time) if start_time else None
            self.start_duration = timedelta(0, duration, 0)
        except KeyError as exc:
            raise click.ClickException(
                f"""Failed to parse config:
Section default does not contain {exc.args[0]}, and it was not specified as a command-line option"""
            ) from exc
        except Exception as exc:
            log.err("An unexpected error occurred while parsing config.")
            log.traceback(exc)
            log.dump()
            raise click.ClickException(
                "Failed to load configuration: \nAn unexpected exception occurred."
            ) from exc

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        """Loads the configuration file at $HOME/.spyderbat-api/config.yaml"""
        home = os.environ.get("HOME")
        config_file_loc = os.path.join(home, ".spyderbat-api/config.yaml")

        with open(config_file_loc, encoding="utf-8") as file:
            file_config = yaml.safe_load(file)

        return file_config["default"]

    def dump(self) -> None:
        """Saves the settings in a persistent configuration file"""
        config_dir = os.path.join(os.environ.get("HOME"), ".spyderbat-api/")

        # ensure that the config directory exists
        if not os.path.exists(config_dir):
            os.mkdir(config_dir)

        # save the config file
        with open(
            os.path.join(config_dir, ".spydertop-settings.yaml"), "w", encoding="utf-8"
        ) as file:
            exclude_settings = ["filter", "sort_column", "sort_ascending", "play"]
            for key in exclude_settings:
                if key in self.settings:
                    del self.settings[key]
            yaml.dump(
                {
                    "settings": self.settings,
                    "processes": dump_columns(PROCESS_COLUMNS),
                    "sessions": dump_columns(SESSION_COLUMNS),
                    "flags": dump_columns(FLAG_COLUMNS),
                    "connections": dump_columns(CONNECTION_COLUMNS),
                    "listening": dump_columns(LISTENING_SOCKET_COLUMNS),
                },
                file,
            )

    # allow for config to be accessed as a dictionary
    # this is just for convenient access to the settings
    # and to track settings changes
    def __getitem__(self, key: str) -> Any:
        if key not in self.settings:
            return None
        return self.settings[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.settings[key] = value
        self.settings_changed = True

    def __str__(self) -> str:
        api_key = (
            f"{self.api_key[:3]}...{self.api_key[-3:]}" if self.api_key else "None"
        )
        return f"""\
config:
    api_key: {api_key}
    org: {self.org}
    machine: {self.machine}
    input: {self.input}
    start_time: {self.start_time}
    start_duration: {self.start_duration}\
        """

    def cleanup(self):
        """Perform cleanup of the associated data in the config"""
        # input is not closed for us because it is opened manually
        # this means we need to close it manually
        if self.input and not isinstance(self.input, str):
            self.input.close()
        # if the output is a gzip file, we need to close it manually
        if hasattr(self.output, "close"):
            self.output.close()

    @property
    def is_complete(self):
        """Whether or not the config is ready to be used to fetch from an API"""
        return (
            self.api_key is not None
            and self.org_confirmed
            and self.source_confirmed
            and self.org is not None
            and self.machine is not None
            and "*" not in self.machine  # * is a wildcard for the source
            and self.start_time is not None
        ) or not isinstance(self.input, str)
