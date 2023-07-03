#
# cache.py
#
# Author: Griffith Thomas
# Copyright 2023 Spyderbat, Inc. All rights reserved.
#

"""
A module for handling caching of data from expensive operations
"""

from datetime import timedelta, datetime
import hashlib
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union
import gzip

import yaml

from spydertop.config import DIRS
from spydertop.utils import log

DEFAULT_TIMEOUT = timedelta(minutes=5)


def cache_block(
    key: Union[str, bytes],
    func: Callable[[], bytes],
    timeout: timedelta = DEFAULT_TIMEOUT,
) -> bytes:
    """A context manager for caching the result of a block of code"""
    if isinstance(key, str):
        key = key.encode("utf-8")
    # the api key may be included, so don't set usedforsecurity=False for some extra protection
    # usedforsecurity is also not available in python <3.9
    numeric_hash = hashlib.md5(key).hexdigest()
    hashed_key = f"block:{numeric_hash}"

    result = _cache_get(hashed_key, timeout)
    if result is None:
        result = func()
        _cache_set(hashed_key, result)
    return result


def get_user_cache() -> Dict[str, Any]:
    """Get the user cache"""
    cache_file = Path(DIRS.user_cache_dir) / "user_cache.yaml"
    if cache_file.exists():
        cache = yaml.safe_load(cache_file.read_text(encoding="utf-8"))
    else:
        cache = {}
    return cache


def set_user_cache(key: str, value: Any):
    """Set a value in the user cache"""
    # this is used infrequently for now, so we are not going to worry about
    # the performance of this
    cache = get_user_cache()
    cache[key] = value
    cache_file = Path(DIRS.user_cache_dir) / "user_cache.yaml"
    cache_file.write_text(yaml.safe_dump(cache), encoding="utf-8")


def _cache_get(key: str, timeout: timedelta):
    """Get the cached value for a key, or None if it doesn't exist"""
    return _disk_cache_get(key, timeout)


def _cache_set(key: str, value):
    """Set the cached value for a key"""
    _disk_cache_set(key, value)


def _disk_cache_get(key: str, timeout: timedelta) -> Optional[bytes]:
    """Get the cached value for a key from the cache directory"""
    cache_dir = Path(DIRS.user_cache_dir)
    cache_file = cache_dir / key

    if not cache_file.exists():
        log.debug("cache miss;reason=nonexistent", key)
        return None

    if cache_file.stat().st_mtime < (datetime.now() - timeout).timestamp():
        log.debug("cache miss;reason=expired", key)
        return None

    with gzip.open(cache_file, "rb") as open_file:
        return open_file.read()


def _disk_cache_set(key: str, value: bytes):
    """Set the cached value for a key in the cache directory"""
    cache_dir = Path(DIRS.user_cache_dir)
    cache_file = cache_dir / key

    with gzip.open(cache_file, "wb") as open_file:
        open_file.write(value)
