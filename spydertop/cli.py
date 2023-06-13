#
# cli.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
Contains the logic to process cli arguments and start the application
"""


from datetime import datetime, timedelta
import gzip
import logging
from pathlib import Path
from typing import Optional

import click
from click.shell_completion import CompletionItem
import yaml

from spydertop.config import DEFAULT_API_URL, DIRS
from spydertop.config.secrets import Secret
from spydertop.config.config import (
    DEFAULT_CONFIG_PATH,
    Config,
    ConfigError,
    Context,
    Focus,
)
from spydertop.screens import start_screen
from spydertop.state import State

# from spydertop.screens import start_screen
from spydertop.utils import convert_to_seconds, log


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
        secrets = Secret.get_secrets()
        secret_names = list(secrets.keys())
        secret_names.sort()
        return [
            CompletionItem(secret_name)
            for secret_name in secret_names
            if secret_name.startswith(incomplete)
        ]


class ContextParam(click.ParamType):
    """
    The name of a context in the configuration.
    """

    name = "Contexts"

    def shell_complete(self, ctx, param, incomplete):
        try:
            config_obj = Config.load_from_directory(Path(DIRS.user_config_dir))
            context_names = list(config_obj.contexts.keys())
            context_names.sort()
            return [
                CompletionItem(context_name)
                for context_name in context_names
                if context_name.startswith(incomplete)
            ]
        except ConfigError:
            return []


SUB_EPILOG = """
Run 'spydertop COMMAND --help' for more information on a command.
"""
CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(context_settings={**CONTEXT_SETTINGS})
@click.version_option(None, "--version", "-V")
@click.option(
    "--config-dir",
    "-c",
    type=click.Path(exists=True, path_type=Path, dir_okay=True, file_okay=False),
    default=Path(DIRS.user_config_dir),
    help=f"The configuration file to use. Defaults to {DEFAULT_CONFIG_PATH}",
)
@click.pass_context
def cli(ctx: click.Context, config_dir: Path):
    """
    Spydertop - Historical TOP Tool

    Run 'spydertop COMMAND --help' for more information on a command.
    """

    # Load the config file
    if not config_dir.exists() and config_dir != Path(DIRS.user_config_dir):
        click.echo(f"Error loading config file: {config_dir} does not exist")
        ctx.exit(1)
    config_obj = Config.load_from_directory(config_dir)
    ctx.obj = {
        "config": config_obj,
        "config_dir": config_dir,
    }


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
    "--log-level",
    type=str,
    default="WARN",
    help="What level of verbosity in logs, one of TRACEBACK, DEBUG, INFO, WARN, ERROR. If a + is \
appended to the log level, extended logging and saving to a file will be enabled. \
Defaults to WARN",
    envvar="SPYDERTOP_LOG_LEVEL",
)
@click.argument("timestamp", type=Timestamp(), required=False)
@click.pass_context
def load(  # pylint: disable=too-many-arguments
    ctx,
    organization,
    machine,
    input_file,
    output,
    timestamp,
    duration,
    log_level,
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
        if isinstance(input_file, gzip.GzipFile):
            raise click.BadParameter(
                "Input file must be a text gzip file, not a binary gzip file"
            )
    if input_file is None:
        input_file = DEFAULT_API_URL

    state = State(
        time=datetime.fromtimestamp(timestamp) if timestamp else None,
        start_duration=timedelta(seconds=duration),
        org_uid=organization,
        source_uid=machine,
    )

    # allow for logging from the underlying library
    # and saving to a file if it is requested
    if log_level.endswith("+"):
        log_level = log_level[:-1]
        log.log_level = logging.getLevelName(log_level)
        log.initialize_development_logging()
    else:
        log.log_level = logging.getLevelName(log_level)

    if isinstance(log.log_level, str):
        log.log_level = logging.WARN
        log.warn(
            "Invalid log level specified, defaulting to WARN. \
See --help for a list of valid log levels."
        )

    start_screen(ctx.obj["config"], ctx.obj["config_dir"], state, input_file, output)


@cli.group()
def config():
    """
    Set or show the current configuration values.

    Allows setting the default values for the organization, machine ids,
    and more, and displaying the current values for configurations.
    """


def get_config_from_ctx(ctx: click.Context) -> Config:
    """
    Gets the configuration object from the context, or exits if it is not set
    """
    ctx.ensure_object(dict)
    inner_config: Config = ctx.obj.get("config", None)
    if inner_config is None:
        click.echo("No config loaded")
        ctx.exit(1)
    return inner_config


@config.command("get")
@click.pass_context
def get_config(ctx: click.Context):
    """
    Gets the currently loaded configuration
    """
    inner_config = get_config_from_ctx(ctx)

    click.echo(yaml.dump(inner_config.as_dict()))


@config.command()
@click.argument("name", required=False, type=ContextParam())
@click.pass_context
def get_context(ctx: click.Context, name: Optional[str] = None):
    """
    Gets the currently loaded configuration
    """
    inner_config = get_config_from_ctx(ctx)
    if name is not None:
        contexts = {name: inner_config.contexts[name].as_dict()}
    else:
        contexts = {
            name: context.as_dict() for name, context in inner_config.contexts.items()
        }
    click.echo(yaml.dump(contexts))


@config.command()
@click.option(
    "--name",
    "-n",
    type=str,
    help="Name of the context to create or update.",
    required=True,
)
@click.option(
    "--secret",
    "-s",
    type=SecretsParam(),
    help="Name of the secret to use in this context. Defaults to 'default'",
    default="default",
)
@click.option(
    "--organization",
    "--org",
    "-g",
    type=str,
    help="Name or ID of the organization to pull data from",
    required=True,
)
@click.option(
    "--focus",
    "-f",
    type=str,
    help="ID of the record to focus on",
)
@click.option(
    "--source",
    type=str,
    help="ID of the machine or cluster to load",
    # required=True,  # TODO: add automatic source determining
)
@click.pass_context
def set_context(  # pylint: disable=too-many-arguments
    ctx: click.Context,
    secret: str,
    name: str,
    organization: str,
    focus: Optional[str],
    source: Optional[str],
):
    """
    Create or update a context for loading data.
    """
    inner_config = get_config_from_ctx(ctx)
    if source is not None and focus is not None:
        focuses = Focus.get_focuses(source, focus)
    else:
        focuses = []
    inner_config.contexts[name] = Context(secret, organization, source, focuses)
    inner_config.save_to_directory(ctx.obj["config_dir"])


@config.command()
@click.argument("name", type=ContextParam(), required=True)
@click.pass_context
def use_context(ctx: click.Context, name: str):
    """
    Set the current context to use.
    """
    inner_config = get_config_from_ctx(ctx)
    if name not in inner_config.contexts:
        click.echo(f"Context {name} does not exist.")
        return
    inner_config.active_context = name
    inner_config.save_to_directory(ctx.obj["config_dir"])


@config.command()
@click.argument("name", type=ContextParam(), required=True)
@click.pass_context
def delete_context(ctx: click.Context, name: str):
    """
    Delete a context from the configuration.
    """
    inner_config = get_config_from_ctx(ctx)
    if name not in inner_config.contexts:
        click.echo(f"Context {name} does not exist.")
        return
    click.confirm(f"Are you sure you want to delete context {name}?", abort=True)
    del inner_config.contexts[name]
    inner_config.save_to_directory(ctx.obj["config_dir"])


@config.command("set-secret")
@click.option(
    "--name",
    "-n",
    type=str,
    help="Name of the secret to create or update. Defaults to 'default'",
    default="default",
)
@click.option(
    "--api-key",
    "--apikey",
    "-k",
    type=str,
    help="API key generated via the Spyderbat UI",
    required=True,
)
@click.option(
    "--api-url",
    "--apiurl",
    "-u",
    type=str,
    help="URL target for api queries.",
    default=DEFAULT_API_URL,
)
def set_api_secret(
    api_key: str, api_url: Optional[str] = None, name: Optional[str] = None
):
    """
    Create or update a secret for accessing the API.
    """
    if not name:
        name = "default"
    secrets = Secret.get_secrets()
    if name in secrets:
        click.confirm(
            f"Secret {name} already exists. Are you sure you want to overwrite it?",
            abort=True,
        )
        click.echo(f"Updating secret {name}...")
    else:
        click.echo(f"Creating secret {name}...")

    secrets[name] = Secret(api_key) if api_url is None else Secret(api_key, api_url)

    Secret.set_secrets(secrets)


@config.command("get-secret")
@click.argument("name", required=False, type=SecretsParam())
def get_api_secret(name=None):
    """Describe one or many api secrets."""
    secrets = Secret.get_secrets()
    if name:
        secrets = {name: secrets[name].as_dict()}
    else:
        secrets = {name: secret.as_dict() for name, secret in secrets.items()}

    click.echo(yaml.dump(secrets))


@config.command("delete-secret")
@click.argument("name", required=True, type=SecretsParam())
def delete_api_secret(name=None):
    """Delete an api secret"""
    assert name is not None
    secrets = Secret.get_secrets()
    if name not in secrets:
        click.echo(f"Secret {name} does not exist.")
        return
    click.confirm(f"Are you sure you want to delete secret {name}?", abort=True)

    del secrets[name]
    Secret.set_secrets(secrets)
