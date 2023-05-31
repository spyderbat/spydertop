"""
A module for handling caching of data from expensive operations
"""

from datetime import timedelta, datetime
import hashlib
from typing import Callable, Optional, Union
import gzip

from spydertop.config import get_config_dir
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


def _cache_get(key: str, timeout: timedelta):
    """Get the cached value for a key, or None if it doesn't exist"""
    return _disk_cache_get(key, timeout)


def _cache_set(key: str, value):
    """Set the cached value for a key"""
    _disk_cache_set(key, value)


def _disk_cache_get(key: str, timeout: timedelta) -> Optional[bytes]:
    """Get the cached value for a key from the cache directory"""
    cache_dir = _get_cache_dir()

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
    cache_dir = _get_cache_dir()
    cache_file = cache_dir / key

    with gzip.open(cache_file, "wb") as open_file:
        open_file.write(value)


def _get_cache_dir():
    """Get the cache directory"""
    config_dir = get_config_dir()
    cache_dir = config_dir / "cache"
    if not cache_dir.exists():
        cache_dir.mkdir()
    return cache_dir
