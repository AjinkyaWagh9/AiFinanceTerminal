"""REPL entrypoint for FINTERMINAL."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from rich.console import Console

from .commands import dispatch
from .ui.panels import banner

load_dotenv()
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
console = Console()


def run() -> None:
    console.print(banner())
    while True:
        try:
            line = console.input("[bold green]>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye.[/]")
            return
        if not line:
            continue
        if line in ("/quit", "/exit"):
            console.print("[dim]bye.[/]")
            return
        dispatch(line, console)


if __name__ == "__main__":
    run()
