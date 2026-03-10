"""macstrap init – generate package list template files."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

console = Console()

TEMPLATES: dict[str, str] = {
    "packages-macports.txt": """\
# MacPorts packages
# One package per line. Lines starting with # are ignored.
# Example:
#   cmake
#   tmux
#   jq
#   htop
#   wget
#   curl
#   go
#   ffmpeg
#   tree
#   autossh
#   websocat
""",
    "packages-brew.txt": """\
# Homebrew formula packages
# One package per line. Lines starting with # are ignored.
# Example:
#   git
#   gh
#   fzf
#   ripgrep
""",
    "packages-brew-casks.txt": """\
# Homebrew cask packages (GUI applications)
# One package per line. Lines starting with # are ignored.
# Example:
#   docker
#   visual-studio-code
#   raycast
#   iterm2
""",
    "packages-npm-global.txt": """\
# Global npm packages (installed via nvm's default Node)
# One package per line. Lines starting with # are ignored.
# Example:
#   yarn
#   pnpm
#   typescript
#   ts-node
""",
    "packages-pip-global.txt": """\
# Global pip packages
# One package per line. Lines starting with # are ignored.
# Example:
#   httpie
#   rich
#   ruff
""",
}


def _create_files(
    base: Path,
    files: dict[str, str],
    force: bool,
) -> tuple[list[str], list[str]]:
    created, skipped = [], []
    for filename, content in files.items():
        dest = base / filename
        if dest.exists() and not force:
            skipped.append(str(dest))
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        created.append(str(dest))
    return created, skipped


def _example_templates_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "example_configs"


def _create_files_from_dir(src_dir: Path, dest_dir: Path, force: bool) -> tuple[list[str], list[str]]:
    created, skipped = [], []
    for src in sorted(src_dir.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(src_dir)
        dest = dest_dir / rel
        if dest.exists() and not force:
            skipped.append(str(dest))
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text())
        created.append(str(dest))
    return created, skipped


@click.command("init")
@click.option(
    "--dir",
    "target_dir",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, writable=True),
    help="Directory to create package files in.",
)
@click.option("--force", is_flag=True, help="Overwrite existing files.")
@click.option(
    "--examples",
    "--exmaples",
    is_flag=True,
    help="Also create starter config directories under ./examples/.",
)
def cmd_init(target_dir: str, force: bool, examples: bool) -> None:
    """Generate package list template files in the current directory.

    Creates packages-macports.txt, packages-brew.txt,
    packages-brew-casks.txt, packages-npm-global.txt,
    and packages-pip-global.txt.
    """
    base = Path(target_dir).resolve()
    base.mkdir(parents=True, exist_ok=True)

    created_abs, skipped_abs = _create_files(base, TEMPLATES, force)
    created = [str(Path(p).relative_to(base)) for p in created_abs]
    skipped = [str(Path(p).relative_to(base)) for p in skipped_abs]

    console.print()
    if created:
        console.print(Panel(
            "\n".join(f"  [green]✓[/] {f}" for f in created),
            title="[bold]Files created[/]",
            border_style="green",
        ))
    if skipped:
        console.print(Panel(
            "\n".join(f"  [yellow]–[/] {f}  (already exists, use --force to overwrite)" for f in skipped),
            title="[bold]Skipped[/]",
            border_style="yellow",
        ))

    if examples:
        ex_created: list[str] = []
        ex_skipped: list[str] = []
        templates_root = _example_templates_dir()
        if templates_root.exists():
            for src_dir in sorted(p for p in templates_root.iterdir() if p.is_dir()):
                dest_dir = base / "examples" / src_dir.name
                c, s = _create_files_from_dir(src_dir, dest_dir, force)
                ex_created.extend(str(Path(p).relative_to(base)) for p in c)
                ex_skipped.extend(str(Path(p).relative_to(base)) for p in s)
        else:
            console.print(
                "[yellow]⚠[/]  Example templates not found in package data; skipping examples."
            )

        if ex_created:
            console.print(Panel(
                "\n".join(f"  [green]✓[/] {p}" for p in ex_created),
                title="[bold]Example configs created[/]",
                border_style="green",
            ))
        if ex_skipped:
            console.print(Panel(
                "\n".join(
                    f"  [yellow]–[/] {p}  (already exists, use --force to overwrite)"
                    for p in ex_skipped
                ),
                title="[bold]Example configs skipped[/]",
                border_style="yellow",
            ))

    console.print()
    console.print("[bold]Next steps:[/]")
    console.print("  1. Edit the package files to add the software you want installed")
    console.print("  2. [cyan]macstrap ssh-auth <host>[/]   – store sudo password")
    if examples:
        console.print(
            "  3. [cyan]macstrap run --config examples/ai-cli <host>[/]  – try an example config"
        )
    else:
        console.print("  3. [cyan]macstrap run <host>[/]        – run setup on the remote Mac")
    console.print()
