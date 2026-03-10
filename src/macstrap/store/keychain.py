"""macOS Keychain backend using the `security` CLI."""

from __future__ import annotations

import subprocess

from .base import BaseStore


class KeychainStore(BaseStore):
    """Store credentials in macOS Keychain via `security` command."""

    def get(self, key: str) -> str | None:
        result = subprocess.run(
            [
                "security", "find-generic-password",
                "-a", self.ACCOUNT,
                "-s", key,
                "-w",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
        return None

    def set(self, key: str, value: str, label: str = "") -> None:
        # Remove existing entry first (ignore errors)
        subprocess.run(
            [
                "security", "delete-generic-password",
                "-a", self.ACCOUNT,
                "-s", key,
            ],
            capture_output=True,
        )
        cmd = [
            "security", "add-generic-password",
            "-a", self.ACCOUNT,
            "-s", key,
            "-w", value,
        ]
        if label:
            cmd += ["-l", label]
        subprocess.run(cmd, capture_output=True, check=True)

    def delete(self, key: str) -> None:
        subprocess.run(
            [
                "security", "delete-generic-password",
                "-a", self.ACCOUNT,
                "-s", key,
            ],
            capture_output=True,
        )
