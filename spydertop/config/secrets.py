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
from functools import lru_cache
from pathlib import Path
from typing import Dict

import yaml
from spydertop.config import DEFAULT_API_URL

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

    @staticmethod
    def _get_secrets_file(config_dir: Path) -> Path:
        secret_file = config_dir / ".secrets"

        return secret_file

    @staticmethod
    @lru_cache(maxsize=1)
    def get_secrets(config_dir: Path) -> Dict[str, "Secret"]:
        """
        Returns the secrets in the config directory.
        Secrets are lru_cached the first time they are read. This means that if the
        secrets file is updated, spydertop will need to be restarted.
        """
        secret_file = Secret._get_secrets_file(config_dir)

        if not secret_file.exists():
            return {}

        with open(secret_file, "r", encoding="utf-8") as file:
            secrets = yaml.safe_load(file)

        return {
            name: Secret(secret["api_key"], secret["api_url"])
            for name, secret in secrets.items()
        }

    @staticmethod
    def set_secrets(config_dir: Path, secrets: Dict[str, "Secret"]):
        """Sets the secrets in the config file"""
        secret_file = Secret._get_secrets_file(config_dir)

        secrets_as_json = {name: asdict(secret) for name, secret in secrets.items()}

        with open(secret_file, "w", encoding="utf-8") as file:
            yaml.dump(secrets_as_json, file)
