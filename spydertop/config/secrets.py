from pathlib import Path
from typing import Dict, Optional

import yaml
from spydertop.config import DIRS, DEFAULT_API_URL

from spydertop.utils import obscure_key


class Secret:
    api_key: str
    api_url: str
    name: str

    def __init__(self, name: str, api_key: str, api_url: Optional[str]):
        self.name = name
        self.api_key = api_key
        self.api_url = api_url or DEFAULT_API_URL

    def __str__(self):
        data = {
            self.name: self.json(),
        }
        # obscure the api key
        data[self.name]["api_key"] = obscure_key(data[self.name]["api_key"])
        return yaml.dump(data)

    def json(self):
        """Returns the secret as a json object"""
        return {"api_key": self.api_key, "api_url": self.api_url}


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
        name: Secret(name, secret["api_key"], secret["api_url"])
        for name, secret in secrets.items()
    }


def set_secrets(secrets: Dict[str, Secret]):
    """Sets the secrets in the config file"""
    secret_file = _get_secrets_file()

    secrets_as_json = {name: secret.json() for name, secret in secrets.items()}

    with open(secret_file, "w", encoding="utf-8") as file:
        yaml.dump(secrets_as_json, file)
