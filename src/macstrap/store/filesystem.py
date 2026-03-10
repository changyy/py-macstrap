"""Linux filesystem backend using ~/.config/macstrap/."""

from __future__ import annotations

import stat
from pathlib import Path

from .base import BaseStore

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "macstrap"


class FilesystemStore(BaseStore):
    """Store credentials as files under ~/.config/macstrap/ (chmod 600)."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or DEFAULT_CONFIG_DIR
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Sanitise key to be a safe filename (replace '/' with '-')
        safe = key.replace("/", "-")
        return self.config_dir / safe

    def get(self, key: str) -> str | None:
        p = self._path(key)
        if p.exists():
            return p.read_text().strip() or None
        return None

    def set(self, key: str, value: str, label: str = "") -> None:
        p = self._path(key)
        p.write_text(value)
        p.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()
