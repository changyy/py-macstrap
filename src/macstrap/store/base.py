"""Abstract storage interface for macstrap credentials.

macOS  → Keychain (security command)
Linux  → ~/.config/macstrap/ (files, chmod 600)

Key naming convention:
  macstrap-target        → current default host
  macstrap-hosts         → comma-separated index of registered hosts
  macstrap-pass-{host}   → sudo/vault password for a specific host
  macstrap-user-{host}   → SSH username for a specific host
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseStore(ABC):
    SERVICE_PREFIX = "macstrap"
    ACCOUNT = "ansible-vault"

    # ── Low-level primitives ──────────────────────────────

    @abstractmethod
    def get(self, key: str) -> str | None:
        """Return stored value for key, or None if not found."""

    @abstractmethod
    def set(self, key: str, value: str, label: str = "") -> None:
        """Store value under key."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove key (no-op if not found)."""

    # ── Target host ───────────────────────────────────────

    def get_target(self) -> str | None:
        return self.get(f"{self.SERVICE_PREFIX}-target")

    def set_target(self, host: str) -> None:
        self.set(f"{self.SERVICE_PREFIX}-target", host, "macstrap target host")

    def delete_target(self) -> None:
        self.delete(f"{self.SERVICE_PREFIX}-target")

    # ── Per-host password ─────────────────────────────────

    def _pass_key(self, host: str) -> str:
        return f"{self.SERVICE_PREFIX}-pass-{host}"

    def get_pass(self, host: str) -> str | None:
        return self.get(self._pass_key(host))

    def set_pass(self, host: str, password: str) -> None:
        self.set(
            self._pass_key(host),
            password,
            f"macstrap sudo password for {host}",
        )

    def delete_pass(self, host: str) -> None:
        self.delete(self._pass_key(host))

    # ── Host index ────────────────────────────────────────

    def _hosts_key(self) -> str:
        return f"{self.SERVICE_PREFIX}-hosts"

    def get_hosts(self) -> list[str]:
        raw = self.get(self._hosts_key())
        if not raw:
            return []
        return [h for h in raw.split(",") if h]

    def add_host(self, host: str) -> None:
        hosts = self.get_hosts()
        if host not in hosts:
            hosts.append(host)
            self.set(self._hosts_key(), ",".join(hosts), "macstrap registered hosts")

    def remove_host(self, host: str) -> None:
        hosts = [h for h in self.get_hosts() if h != host]
        if hosts:
            self.set(self._hosts_key(), ",".join(hosts), "macstrap registered hosts")
        else:
            self.delete(self._hosts_key())

    # ── Per-host SSH user ─────────────────────────────────

    def _user_key(self, host: str) -> str:
        return f"{self.SERVICE_PREFIX}-user-{host}"

    def get_user(self, host: str) -> str | None:
        return self.get(self._user_key(host))

    def set_user(self, host: str, user: str) -> None:
        self.set(self._user_key(host), user, f"macstrap SSH user for {host}")

    def delete_user(self, host: str) -> None:
        self.delete(self._user_key(host))

    # ── Composite helpers ─────────────────────────────────

    def register(self, host: str, password: str, user: str | None = None) -> None:
        """Store password (and optional SSH user) and update host index + target."""
        self.set_pass(host, password)
        if user:
            self.set_user(host, user)
        self.add_host(host)
        self.set_target(host)

    def unregister(self, host: str) -> None:
        """Remove password, SSH user, and host from index."""
        self.delete_pass(host)
        self.delete_user(host)
        self.remove_host(host)
        if self.get_target() == host:
            self.delete_target()
