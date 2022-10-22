#
# cli.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
Contains the logic to process cli arguments and start the application
"""

import time
import gzip
from datetime import datetime
from typing import Optional
from os.path import exists

import click
from spydertop.config import Config
from spydertop.screens import start_screen

from spydertop.utils import convert_to_seconds


class Timestamp(click.ParamType):
    """
    An absolute time or relative time, using simple units at the end,
    or a datetime string. Negative times are considered relative to now.
    Accepted units are s: seconds, m: minutes, h: hours, d: days, y: years.
    No unit is interpreted as seconds. For example:

    -5.5d = 5.5 days ago
    -5m = 5 minutes ago
    1654221985.1162226 = June 2, 2022 21:06:25.1162226
    2022-06-02T21:06:25.116223 = June 2, 2022 21:06:25.116223
    """

    name = "Timestamp"

    def convert(
        self, value, param: Optional[click.Parameter], ctx: Optional[click.Context]
    ):
        if not value:
            return None
        # try converting to datetime with iso first
        try:
            timestamp = datetime.fromisoformat(value)
            return timestamp.timestamp()
        except ValueError:
            try:
                timestamp = convert_to_seconds(value)

                if timestamp < 0:
                    timestamp = time.time() + timestamp
                return timestamp
            except ValueError:
                return self.fail(
                    f"{value} is not a valid timestamp. "
                    "Please use a valid timestamp or a relative time "
                    "using the following units: s, m, h, d, y",
                )

    def get_missing_message(self, param):
        return "TIMESTAMP is required to fetch the correct records"


class Duration(click.ParamType):
    """
    A duration in time, using simple units.
    Accepted units are s: seconds, m: minutes, h: hours, d: days, y: years.
    No unit is interpreted as seconds. For example:

    -5.5d = 5.5 days ago
    -5m = 5 minutes ago
    """

    name = "Duration"

    def convert(
        self, value, param: Optional[click.Parameter], ctx: Optional[click.Context]
    ):
        if not value:
            return None
        try:
            timestamp = convert_to_seconds(value)
            return timestamp
        except ValueError as exc:
            return self.fail(f"Unable to convert input into duration: {value} {exc}")


class FileOrUrl(click.ParamType):
    """
    A text or gzipped file input, or a string url.
    Files will automatically be opened by the proper reader,
    and urls will be converted to a proper base url (with https, etc.)
    """

    name = "File or Url"

    def convert(
        self, value: str, param: Optional[click.Parameter], ctx: Optional[click.Context]
    ):
        if not value:
            return None
        if exists(value):
            try:
                # first, determine if it is JSON or GZIP
                tmp = open(value, "rb")  # pylint: disable=consider-using-with
                magic_bytes = tmp.read(2)
                tmp.close()
                if magic_bytes == b"\x1f\x8b":
                    # GZIP file detected
                    return gzip.open(value, "rt")
                # other file detected, assuming JSON
                return open(value, "r", encoding="utf-8")

            except FileNotFoundError as exc:
                return self.fail(f"Unable to open file {value}: {exc}")
        else:
            # first see if it is a file, but a non-existent one
            if value.endswith(".json") or value.endswith(".json.gz"):
                return self.fail(f"File {value} does not exist")
            # convert base domains into a full url base
            return f"https://{value}" if "http" not in value else value


# ignore unknown options is necessary to allow dashes in the
# timestamp argument, but is imperfect. This will work:
#   spydertop -300
# but this will not:
#   spydertop -2d
# because it detects it as the '-d' argument
@click.command(context_settings={"ignore_unknown_options": True})
@click.option(
    "--organization",
    "-g",
    type=str,
    help="The organization ID to pull data from. \
Defaults to the values set in your spyderbat_api config",
)
@click.option(
    "--machine",
    "-m",
    type=str,
    help="The machine ID to pull data from. This should be in the format 'mach:aEdYih-4bia'. \
Defaults to the values set in your spyderbat_api config",
)
@click.option(
    "--duration",
    "-d",
    default=900,
    type=Duration(),
    help="What period of time records should be pre-fetched for playback in seconds. \
Defaults to 15 minutes",
)
@click.option(
    "--input",
    "-i",
    "input_file",
    type=FileOrUrl(),
    help="If set, spydertop with use the specified input file or domain instead of \
fetching records from the production Spyderbat API",
)
@click.option(
    "--output",
    "-o",
    type=click.File("w"),
    help="If set, spydertop with use the specified output file to save the loaded records",
)
@click.option(
    "--confirm/--no-confirm",
    "-c/-C",
    default=True,
    help="Ask for confirmation of values saved in the config file",
)
@click.option(
    "--log-level",
    type=str,
    default="WARN",
    help="What level of verbosity in logs, one of TRACEBACK, DEBUG, INFO, WARN, ERROR. If a + is \
appended to the log level, extended logging and saving to a file will be enabled. \
Defaults to WARN",
    envvar="SPYDERTOP_LOG_LEVEL",
)
@click.argument("timestamp", type=Timestamp(), required=False)
@click.version_option()
def cli(  # pylint: disable=too-many-arguments
    organization, machine, input_file, output, timestamp, duration, confirm, log_level
):
    """
    Fetches data from the specified org and machine, or the defaults specified
    in ~/.spyderbat-api/config, and presents an htop-like interface for the state of
    the machine at the specified time.

    TIMESTAMP: Fetch records after this time; use negative for relative to now.
    Note: due to argument parsing limitations, this value may need to be
    passed after a -- separator, like so:

    spydertop [options] -- TIMESTAMP

    Durations, such as negative timestamps and the -d flag, can have an optional
    unit at the end. Accepted units are s: seconds, m: minutes, h: hours, d: days,
    y: years. Default is seconds. For example:

    spydertop -- -5.5d
    """

    config = Config(
        organization,
        machine,
        input_file,
        output,
        timestamp,
        duration,
        confirm,
        log_level,
    )

    start_screen(config)
