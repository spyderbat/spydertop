#
# config.py
#
# Author: Griffith Thomas
# Copyright 2023 Spyderbat, Inc. All rights reserved.
#

"""
This module handles the reading, updating, and writing of configurations to the disk
"""
import os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import asdict, dataclass, field

import yaml

from spydertop.config import DEFAULT_API_URL, DIRS
from spydertop.config.secrets import Secret
from spydertop.constants.columns import (
    CONNECTION_COLUMNS,
    CONTAINER_COLUMNS,
    FLAG_COLUMNS,
    LISTENING_SOCKET_COLUMNS,
    PROCESS_COLUMNS,
    SESSION_COLUMNS,
    Column,
)

DEFAULT_CONFIG_PATH = Path(DIRS.user_config_dir) / "config.yaml"


@dataclass
class Focus:
    """Defines a subset of a source to narrow the view"""

    type: str
    value: str

    TYPES = {"machine", "tab", "record"}
    TAB_MAP = {
        "cont": "containers",
        "proc": "processes",
        "conn": "containers",
        "sock": "listening",
        "flag": "flags",
    }

    @staticmethod
    def get_focuses(_source: str, focus_id: str):
        """Creates a list of focus objects from a focus id"""
        id_type = focus_id.split(":")[0]
        if id_type == "mach":
            return [Focus(type="machine", value=focus_id)]
        if id_type in Focus.TAB_MAP:
            return [
                Focus(type="tab", value=Focus.TAB_MAP[id_type]),
                Focus(type="record", value=focus_id),
            ]
        return []


@dataclass
class Context:
    """
    A context is a combination of a secret, organization, and focus. It describes
    the data that spydertop will fetch when it is in that context.
    """

    secret_name: str
    org_uid: Optional[str]
    source: Optional[str]
    focus: List[Focus] = field(default_factory=list)

    def as_dict(self):
        """Returns the config as a dictionary"""
        return {
            **asdict(self),
            "focus": [asdict(f) for f in self.focus],
        }

    def get_secret(self, config_dir: Path) -> Optional[Secret]:
        """Returns the secret that this context uses"""
        return Secret.get_secrets(config_dir).get(self.secret_name, None)


@dataclass
class Settings:  # pylint: disable=too-many-instance-attributes
    """
    The settings that spydertop uses, such as the theme,
    the default duration, whether to cache data, etc.
    """

    theme: str = "htop"
    hide_threads: bool = True
    hide_kthreads: bool = True
    play_speed: int = 1
    tree: bool = False
    collapse_tree: bool = False
    follow_record: bool = False
    utc_time: bool = False
    tab: str = "processes"
    default_duration_minutes: int = 15


class ConfigError(Exception):
    """Raised when there is an error with the config file"""


@dataclass
class Config:
    """
    The config includes the contexts, which describe the secret, organization,
    and focus (machine, container, filters, etc.) that spydertop will use when
    fetching data.

    Configurations also include the settings that spydertop uses, such as the theme,
    the default duration, whether to cache data, etc.
    """

    contexts: Dict[str, Context]
    active_context: Optional[str]
    settings: Settings

    directory: Path = field(default=Path(DIRS.user_config_dir), repr=False)

    @staticmethod
    def load_from_directory(config_dir: Path):
        """Loads a config instance from a file"""
        load_cached_columns(config_dir)
        file = config_dir / "config.yaml"
        if not file.exists():
            migrated_config = Config.migrate_config(config_dir)
            if migrated_config:
                return migrated_config
            return Config(
                contexts={},
                settings=Settings(),
                active_context=None,
                directory=config_dir,
            )
        data = yaml.safe_load(file.read_text())
        try:
            settings = Settings(**data["settings"])
            contexts = {}
            for name, context in data["contexts"].items():
                focuses = []
                for focus in context["focus"]:
                    focuses.append(Focus(**focus))
                context["focus"] = focuses
                contexts[name] = Context(**context)
            return Config(
                contexts=contexts,
                settings=settings,
                active_context=data["active_context"],
                directory=config_dir,
            )
        except KeyError as exc:
            raise ConfigError(f"Failed to load config, missing key: {exc}") from exc

    def save(self):
        """Saves the config to the default location"""
        save_cached_columns(self.directory)
        self.save_to_directory(self.directory)

    def save_to_directory(self, config_dir: Path):
        """Saves the default config"""
        config_path = config_dir / "config.yaml"
        config_path.write_text(yaml.dump(self.as_dict()))

    def as_dict(self) -> dict:
        """Returns the config as a dictionary"""
        data = {
            **asdict(self),
            "contexts": {name: ctx.as_dict() for name, ctx in self.contexts.items()},
        }
        del data["directory"]
        return data

    @staticmethod
    def migrate_config(new_config_path: Path) -> Optional["Config"]:
        """Migrates the config from the old location to the new location"""
        home = os.environ.get("HOME")
        if home is None:
            return None
        old_config_path = Path(home) / ".spyderbat-api"
        if not old_config_path.exists():
            return None
        old_config = yaml.safe_load((old_config_path / "config.yaml").read_text()).get(
            "default", None
        )
        if old_config is None:
            return None
        if "api_key" in old_config:
            new_default_secret = Secret(
                api_key=old_config.get("api_key"),
                api_url=old_config.get("api_url", DEFAULT_API_URL),
            )

            secrets = Secret.get_secrets(new_config_path)
            secrets["default"] = new_default_secret
            Secret.set_secrets(new_config_path, secrets)

        new_default_context = Context(
            secret_name="default", org_uid=old_config.get("org"), source=old_config.get("machine")
        )

        old_settings = yaml.safe_load(
            (old_config_path / ".spydertop-settings.yaml").read_text()
        )
        new_settings = Settings()
        for key in new_settings.__dict__:
            if key in old_settings:
                setattr(new_settings, key, old_settings[key])

        _load_enabled_columns(old_settings, "processes", PROCESS_COLUMNS)
        _load_enabled_columns(old_settings, "connections", CONNECTION_COLUMNS)
        _load_enabled_columns(old_settings, "listening_sockets", LISTENING_SOCKET_COLUMNS)
        _load_enabled_columns(old_settings, "sessions", SESSION_COLUMNS)
        _load_enabled_columns(old_settings, "flags", FLAG_COLUMNS)
        _load_enabled_columns(old_settings, "containers", CONTAINER_COLUMNS)

        return Config(
            contexts={"default": new_default_context},
            settings=new_settings,
            active_context="default",
            directory=new_config_path,
        )

def _load_enabled_columns(settings: Dict, name: str, columns: List[Column]):
    if name in settings:
        for key in settings[name]:
            names = [row.header_name for row in columns]
            if key in names:
                columns[names.index(key)].enabled = settings[name][key]


def load_cached_columns(config_dir: Path):
    """Loads the cached columns from the config directory, if possible"""
    file = config_dir / "columns.yaml"
    if not file.exists():
        return
    data = yaml.safe_load(file.read_text())

    _load_enabled_columns(data, "processes", PROCESS_COLUMNS)
    _load_enabled_columns(data, "connections", CONNECTION_COLUMNS)
    _load_enabled_columns(data, "listening_sockets", LISTENING_SOCKET_COLUMNS)
    _load_enabled_columns(data, "sessions", SESSION_COLUMNS)
    _load_enabled_columns(data, "flags", FLAG_COLUMNS)
    _load_enabled_columns(data, "containers", CONTAINER_COLUMNS)


def save_cached_columns(config_dir: Path):
    """Saves the columns enabled state to the config directory"""
    file = config_dir / "columns.yaml"
    data = {}
    for name, columns in [
        ("processes", PROCESS_COLUMNS),
        ("connections", CONNECTION_COLUMNS),
        ("listening_sockets", LISTENING_SOCKET_COLUMNS),
        ("sessions", SESSION_COLUMNS),
        ("flags", FLAG_COLUMNS),
        ("containers", CONTAINER_COLUMNS),
    ]:
        data[name] = {row.header_name: row.enabled for row in columns}
    file.write_text(yaml.dump(data))


