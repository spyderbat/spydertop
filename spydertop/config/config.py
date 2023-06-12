#
# config.py
#
# Author: Griffith Thomas
# Copyright 2023 Spyderbat, Inc. All rights reserved.
#

"""
This module handles the reading, updating, and writing of configurations to the disk
"""
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import asdict, dataclass, field

import yaml

from spydertop.config import DIRS


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
    org_uid: str
    source: Optional[str] = None
    focus: List[Focus] = field(default_factory=list)

    def as_dict(self):
        """Returns the config as a dictionary"""
        return {
            **asdict(self),
            "focus": [asdict(f) for f in self.focus],
        }


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
    active_context: str
    settings: Settings

    @staticmethod
    def load_from_file(file: Path):
        """Loads a config instance from a file"""
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
            )
        except KeyError as exc:
            raise ConfigError(f"Failed to load config, missing key: {exc}") from exc

    @staticmethod
    def load_default():
        """Loads the default config"""
        default_path = Path(DIRS.user_config_dir) / "config.yaml"
        if default_path.exists():
            return Config.load_from_file(default_path)
        return Config(
            contexts={},
            settings=Settings(),
            active_context="default",
        )

    def save_default(self):
        """Saves the default config"""
        default_path = Path(DIRS.user_config_dir) / "config.yaml"
        default_path.write_text(yaml.dump(self.as_dict()))

    def as_dict(self):
        """Returns the config as a dictionary"""
        return {
            **asdict(self),
            "contexts": {name: ctx.as_dict() for name, ctx in self.contexts.items()},
        }