"""Tests for FilesystemStore."""

import stat
import tempfile
from pathlib import Path

import pytest

from macstrap.store.filesystem import FilesystemStore


@pytest.fixture
def store(tmp_path: Path) -> FilesystemStore:
    return FilesystemStore(config_dir=tmp_path)


def test_get_missing(store: FilesystemStore) -> None:
    assert store.get("nonexistent") is None


def test_set_and_get(store: FilesystemStore) -> None:
    store.set("test-key", "hello")
    assert store.get("test-key") == "hello"


def test_file_permissions(store: FilesystemStore, tmp_path: Path) -> None:
    store.set("secret", "password")
    p = tmp_path / "secret"
    mode = stat.S_IMODE(p.stat().st_mode)
    assert mode == 0o600


def test_delete(store: FilesystemStore) -> None:
    store.set("del-key", "value")
    store.delete("del-key")
    assert store.get("del-key") is None


def test_delete_nonexistent(store: FilesystemStore) -> None:
    store.delete("ghost")  # should not raise


def test_register_and_get_pass(store: FilesystemStore) -> None:
    store.register("my-mac.local", "s3cr3t")
    assert store.get_pass("my-mac.local") == "s3cr3t"
    assert store.get_target() == "my-mac.local"
    assert "my-mac.local" in store.get_hosts()


def test_unregister(store: FilesystemStore) -> None:
    store.register("my-mac.local", "s3cr3t")
    store.unregister("my-mac.local")
    assert store.get_pass("my-mac.local") is None
    assert "my-mac.local" not in store.get_hosts()
    assert store.get_target() is None


def test_host_index_multiple(store: FilesystemStore) -> None:
    store.register("mac1.local", "pass1")
    store.register("mac2.local", "pass2")
    hosts = store.get_hosts()
    assert "mac1.local" in hosts
    assert "mac2.local" in hosts
    assert store.get_target() == "mac2.local"  # last registered becomes target


def test_remove_host_updates_index(store: FilesystemStore) -> None:
    store.register("mac1.local", "pass1")
    store.register("mac2.local", "pass2")
    store.remove_host("mac1.local")
    hosts = store.get_hosts()
    assert "mac1.local" not in hosts
    assert "mac2.local" in hosts
