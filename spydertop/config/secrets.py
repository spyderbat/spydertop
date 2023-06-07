#
# secret.py
#
# Author: Griffith Thomas
# Copyright 2023 Spyderbat, Inc. All rights reserved.
#

"""
A collection of functionality for handling secrets
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict

import yaml
from spydertop.config import DIRS, DEFAULT_API_URL

from spydertop.utils import obscure_key


@dataclass
class Secret:
    """
    A collection of data necessary to fetch data from the API
    """

    api_key: str
    api_url: str = DEFAULT_API_URL

    def as_dict(self):
        """Returns this as a dict object suitable for printing"""
        # obscure the api key
        data = asdict(self)
        data["api_key"] = obscure_key(data["api_key"])
        return data


def _get_secrets_file() -> Path:
    config_dir = Path(DIRS.user_config_dir)
    secret_file = config_dir / ".secrets"

    return secret_file


def get_secrets() -> Dict[str, Secret]:
    """Returns the secrets in the config directory"""
    secret_file = _get_secrets_file()

    if not secret_file.exists():
        return {}

    with open(secret_file, "r", encoding="utf-8") as file:
        secrets = yaml.safe_load(file)

    return {
        name: Secret(secret["api_key"], secret["api_url"])
        for name, secret in secrets.items()
    }


def set_secrets(secrets: Dict[str, Secret]):
    """Sets the secrets in the config file"""
    secret_file = _get_secrets_file()

    secrets_as_json = {name: asdict(secret) for name, secret in secrets.items()}

    with open(secret_file, "w", encoding="utf-8") as file:
        yaml.dump(secrets_as_json, file)
