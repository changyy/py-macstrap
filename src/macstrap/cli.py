"""macstrap – main CLI entry point."""

from __future__ import annotations

import click
from rich.console import Console

from macstrap import __version__
from macstrap.commands.hosts import cmd_delete, cmd_delete_all, cmd_list
from macstrap.commands.init import cmd_init
from macstrap.commands.run import cmd_run
from macstrap.commands.ssh_auth import cmd_ssh_auth
from macstrap.commands.verify import cmd_verify

console = Console()

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__, "-V", "--version")
def main() -> None:
    """macstrap – Remote Mac setup via SSH.

    \b
    Manage one or more Macs from your terminal:

      macstrap init                        generate package list files
      macstrap ssh-auth <host>             store sudo password
      macstrap run [host]                  apply setup to a Mac
      macstrap verify [host]               check packages are installed
      macstrap list                        show registered hosts
      macstrap delete <host>               remove credentials for a host
      macstrap delete-all                  remove all credentials

    \b
    Package files (edit to customise what gets installed):

      packages-macports.txt
      packages-brew.txt
      packages-brew-casks.txt
      packages-npm-global.txt
      packages-pip-global.txt
    """


main.add_command(cmd_init,       name="init")
main.add_command(cmd_ssh_auth,   name="ssh-auth")
main.add_command(cmd_run,        name="run")
main.add_command(cmd_verify,     name="verify")
main.add_command(cmd_list,       name="list")
main.add_command(cmd_delete,     name="delete")
main.add_command(cmd_delete_all, name="delete-all")
