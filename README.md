# macstrap

[![PyPI](https://img.shields.io/pypi/v/macstrap.svg)](https://pypi.org/project/macstrap/)
[![PyPI Downloads](https://static.pepy.tech/badge/macstrap)](https://pepy.tech/projects/macstrap)

A CLI tool for setting up and managing remote Macs via SSH — no Ansible knowledge required.

Define what you want installed in plain text files, register your target machines once, then run a single command to apply the full setup. Safe to re-run anytime; already-installed items are skipped.

# Installation

```
% pip install macstrap
```

# Usage

## 1. Initialise package files

```
% macstrap init
% macstrap init --examples
```

This creates template files you edit to declare what gets installed:

```
packages-macports.txt       # MacPorts packages
packages-brew.txt           # Homebrew formula
packages-brew-casks.txt     # Homebrew cask (GUI apps)
packages-npm-global.txt     # Global npm packages (installed via nvm default Node)
packages-pip-global.txt     # Global pip packages
```

Edit them like a shopping list — one package per line, `#` for comments:

```
# packages-brew.txt
git
gh
fzf
ripgrep
```

For example:

- Add `openjdk` to `packages-brew.txt` to install OpenJDK.
- Add `docker` to `packages-brew-casks.txt` to install Docker Desktop.

If you use `--examples`, macstrap also creates starter config directories under `examples/` (such as `examples/ai-cli`, `examples/openclaw`, `examples/utilities-dev`, `examples/php8.3-dev`).

---

## 2. Register a host

`ssh-auth` does two things in sequence:

1. **Copy your SSH public key** to the remote Mac (one-time, requires SSH password)
2. **Store the sudo password** in the system credential store

```
% macstrap ssh-auth mac-mini.local
% macstrap ssh-auth mac-mini.local --user remoteuser   # if remote username differs
% macstrap ssh-auth 192.168.1.100 --user remoteuser
```

If SSH key auth is already set up, skip the key copy step:

```
% macstrap ssh-auth mac-mini.local --skip-key-copy
```

The SSH username is saved alongside the password so you don't need to type it on every run.

You can register multiple machines — each gets its own credential entry.

---

## 3. Run setup

```
% macstrap run
% macstrap run mac-mini.local
% macstrap run 192.168.1.100
% macstrap run remoteuser@mac-mini.local   # override SSH user inline
% macstrap run --config examples/ai-cli --config examples/openclaw 192.168.1.100
```

macstrap connects over SSH, reads your package files, and installs everything that isn't already there. First run takes 30–60 minutes (MacPorts compiles from source). Subsequent runs take about 1 minute.

**SSH user resolution order** (highest priority first):

1. `--user` flag
2. `user@host` inline syntax
3. SSH user stored at `ssh-auth` time
4. Local OS username (fallback)

---

## 4. Verify installation

Check whether every package in your package files is actually installed on the remote Mac:

```
% macstrap verify
% macstrap verify mac-mini.local
% macstrap verify 192.168.1.100 --user remoteuser
```

Output example:

```
  Tools
  ✓  brew       Homebrew 4.4.12
  ✓  port       Version: 2.12.3
  ✓  nvm        0.40.1
  ✓  node       v22.14.0
  ✗  docker     not found
  ✓  java       openjdk version "21.0.7" 2025-04-15
  ✓  python3    Python 3.13.2

  Homebrew (2/3)
  ✓  git
  ✓  ripgrep
  ✗  htop  (missing)

  ⚠  2 installed, 1 missing
```

Exits with code `0` if everything is present, `1` if anything is missing — useful in CI or scripts.

---

## Example: install OpenJDK + Docker Desktop

```
% macstrap init
% echo "openjdk" >> packages-brew.txt
% echo "docker" >> packages-brew-casks.txt
% macstrap ssh-auth mac-mini.local
% macstrap run mac-mini.local --tag homebrew --tag openjdk --tag docker
% macstrap verify mac-mini.local
```

After Docker Desktop is installed, sign in to the target Mac desktop and launch Docker once to accept the licence and complete first-run setup.

---

## Manage registered hosts

```
% macstrap list

  macstrap credential store  (macOS Keychain)
  Default target: mac-mini.local

  Host              User          Password
  mac-mini.local    remoteuser    ✓ stored   ← default
  192.168.1.200     admin         ✓ stored
```

```
% macstrap delete mac-mini.local
% macstrap delete-all
```

---

## Run only part of the setup

Use `--tag` to apply a single role instead of the full playbook:

```
% macstrap run --tag homebrew
% macstrap run mac-mini.local --tag macports
% macstrap run --tag nvm
% macstrap run --tag shell
% macstrap run --tag pip
```

Available tags: `macports` `homebrew` `nvm` `npm` `docker` `openjdk` `shell` `pip`

---

## Dry run

Preview what would change without applying anything:

```
% macstrap run --check
% macstrap run mac-mini.local --check
```

---

## What gets installed

macstrap reads your package files and applies the following roles in order:

| Phase | Role | What it does |
|-------|------|-------------|
| Bootstrap | *(raw SSH)* | Installs Xcode Command Line Tools via `softwareupdate` if missing — required before Python is available on a fresh Mac |
| Main | `macports` | Installs MacPorts and packages from `packages-macports.txt` |
| Main | `homebrew` | Installs Homebrew formulae from `packages-brew.txt` and casks from `packages-brew-casks.txt` |
| Main | `nvm` | Installs nvm, Node.js (v22), and global npm packages from `packages-npm-global.txt` |
| Main | `docker` | Checks Docker Desktop status and first-launch readiness (install is driven by `packages-brew-casks.txt`, e.g. `docker`) |
| Main | `openjdk` | Configures Java symlink/PATH for Homebrew OpenJDK (install is driven by `packages-brew.txt`, e.g. `openjdk`) |
| Main | `shell` | Deploys a unified `~/.zshrc` with PATH entries for MacPorts, Homebrew, NVM, Java |
| Main | `pip_global` | Installs global pip packages from `packages-pip-global.txt` |

All roles are idempotent — re-running only installs what is missing.

### Fresh Mac note

On a brand-new Mac (or one that has never run Xcode tools), macOS intercepts `/usr/bin/python3` and shows an installation dialog instead of running Python. macstrap handles this automatically: the bootstrap phase uses raw SSH commands (no Python needed) to install Xcode CLT first, then hands off to the normal Ansible playbook.

---

## Credential storage

| Platform | Storage location |
|----------|-----------------|
| macOS | Keychain (`security` command) — visible in Keychain Access → Passwords → search `macstrap` |
| Linux | `~/.config/macstrap/` directory (each key is a separate file, chmod 600) |

Key naming convention:

```
macstrap-target          → current default host
macstrap-hosts           → comma-separated index of all registered hosts
macstrap-pass-{host}     → sudo password for a specific host
macstrap-user-{host}     → SSH username for a specific host
```

---

## Requirements

- Python 3.10+
- SSH access to the target Mac (key-based auth is set up automatically by `ssh-auth`)
- macOS 13+ on the target machine

Ansible is bundled as a dependency — `pip install macstrap` is all you need.

---

## License

MIT © [changyy](https://github.com/changyy)
