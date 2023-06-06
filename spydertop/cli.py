#
# cli.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
Contains the logic to process cli arguments and start the application
"""


import gzip
from typing import Optional

import click
from click.shell_completion import CompletionItem

from spydertop.config import DEFAULT_API_URL, Config
from spydertop.config.secrets import Secret, set_secrets, get_secrets
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
        # dateparser is a slow dependency to start up, so only import it if necessary
        import dateparser  # pylint: disable=import-outside-toplevel

        if not value:
            return None
        parsed_date = dateparser.parse(value)
        if parsed_date:
            return parsed_date.timestamp()
        return self.fail(
            f"{value} is not a valid timestamp. "
            "Please use a valid timestamp or a relative time.",
        )

    def get_missing_message(self, param):
        return "TIMESTAMP is required to fetch the correct records"

    def shell_complete(self, ctx, param, incomplete):
        options = ["5 minutes ago", "15 minutes ago", "an hour ago", "yesterday", "now"]
        return [
            CompletionItem(option)
            for option in options
            if option.startswith(incomplete)
        ]


class Duration(click.ParamType):
    """
    A duration in time, using simple units.
    Accepted units are s: seconds, m: minutes, h: hours, d: days, y: years.
    An absent unit is interpreted as seconds. For example:

    5.5d = 5.5 days
    5m = 5 minutes
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

    def shell_complete(self, ctx, param, incomplete):
        options = ["1m", "5m", "10m", "15m", "30m", "1h"]
        return [
            CompletionItem(option)
            for option in options
            if option.startswith(incomplete)
        ]


class SecretsParam(click.ParamType):
    """
    The name of a secret in the config directory.
    """

    name = "Secrets"

    def shell_complete(self, ctx, param, incomplete):
        secrets = get_secrets()
        secret_names = list(secrets.keys())
        secret_names.sort()
        return [
            CompletionItem(secret_name)
            for secret_name in secret_names
            if secret_name.startswith(incomplete)
        ]


SUB_EPILOG = """
Run 'spydertop COMMAND --help' for more information on a command.
"""
CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(context_settings={**CONTEXT_SETTINGS})
@click.version_option(param_decls=["--version", "-V"])
def cli():
    """
    Spydertop - Historical TOP Tool

    Run 'spydertop COMMAND --help' for more information on a command.
    """


# ignore unknown options is necessary to allow dashes in the
# timestamp argument, but is imperfect. This will work:
#   spydertop -300
# but this will not:
#   spydertop -2d
# because it detects it as the '-d' argument
@cli.command(context_settings={**CONTEXT_SETTINGS, "ignore_unknown_options": True})
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
    type=click.File("r"),
    help="If set, spydertop with use the specified input file instead of \
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
def load(  # pylint: disable=too-many-arguments
    organization, machine, input_file, output, timestamp, duration, confirm, log_level
):
    """
    Fetches data and starts the TUI.

    Fetches data from the specified org and machine, or the defaults specified
    in ~/.spyderbat-api/config, and presents an htop-like interface for the state of
    the machine at the specified time.

    TIMESTAMP: Fetch records after this time; use negative for relative to now.
    Note: due to argument parsing limitations, this value may need to be
    passed after a -- separator, like so:

    spydertop load [options] -- TIMESTAMP

    Durations, such as negative timestamps and the -d flag, can have an optional
    unit at the end. Accepted units are s: seconds, m: minutes, h: hours, d: days,
    y: years. Default is seconds. For example:

    spydertop load -- -5.5d
    """

    if input_file is not None and input_file.name.endswith(".gz"):
        input_file = gzip.open(input_file.name, "rt")

    config_obj = Config(
        organization,
        machine,
        input_file,
        output,
        timestamp,
        duration,
        confirm,
        log_level,
    )

    start_screen(config_obj)


@cli.group()
def secret():
    """
    Set or show API keys.

    Manages the API keys and URLs to use when accessing the spyderbat api.
    """


@secret.command("set")
@click.option(
    "--name",
    "-n",
    type=str,
    help="Name of the secret to create or update. Defaults to 'default'",
    default="default",
)
@click.option(
    "--apikey",
    "--api-key",
    "-k",
    type=str,
    help="API key generated via the Spyderbat UI",
    required=True,
)
@click.option(
    "--apiurl",
    "--api-url",
    "-u",
    type=str,
    help="URL target for api queries.",
    default=DEFAULT_API_URL,
)
def set_api_secret(api_key, api_url=None, name=None):
    """
    Create or update a secret for accessing the API.
    """
    assert api_key is not None  # click should enforce this
    if not name:
        name = "default"
    secrets = get_secrets()
    if name in secrets:
        click.confirm(
            f"Secret {name} already exists. Are you sure you want to overwrite it?",
            abort=True,
        )
        click.echo(f"Updating secret {name}...")
    else:
        click.echo(f"Creating secret {name}...")

    secrets[name] = Secret(name, api_key, api_url)

    set_secrets(secrets)


@secret.command("get")
@click.argument("name", required=False, type=SecretsParam())
def get_api_secret(name=None):
    """Describe one or many api secrets."""
    secrets = get_secrets()
    if name:
        secrets = {name: secrets[name]}

    for inner_secret in secrets.values():
        click.echo(inner_secret)


@secret.command("delete")
@click.argument("name", required=True, type=SecretsParam())
def delete_api_secret(name=None):
    """Delete an api secret"""
    assert name is not None
    secrets = get_secrets()
    if name not in secrets:
        click.echo(f"Secret {name} does not exist.")
        return
    click.confirm(f"Are you sure you want to delete secret {name}?", abort=True)

    del secrets[name]
    set_secrets(secrets)
