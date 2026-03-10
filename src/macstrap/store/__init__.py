"""Storage backend factory."""

from __future__ import annotations

import sys

from .base import BaseStore
from .filesystem import FilesystemStore
from .keychain import KeychainStore

__all__ = ["BaseStore", "FilesystemStore", "KeychainStore", "get_store"]


def get_store() -> BaseStore:
    """Return the appropriate store for the current OS."""
    if sys.platform == "darwin":
        return KeychainStore()
    return FilesystemStore()
