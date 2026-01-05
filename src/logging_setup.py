from __future__ import annotations

import logging
from random import randint

from rich.console import Console
from rich.highlighter import Highlighter
from rich.logging import RichHandler

console = Console()


class RainbowHighlighter(Highlighter):
    def highlight(self, text):
        for index in range(len(text)):
            text.stylize(f"color({randint(16, 255)})", index, index + 1)


rainbow = RainbowHighlighter()

_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


def configure_logging(level: str | int = "info") -> None:
    """
    Idempotent-ish logging setup using Rich for console output.
    Safe to call early in main().
    """
    if isinstance(level, int):
        resolved = level
    else:
        resolved = _LEVELS.get(str(level).strip().lower(), logging.INFO)

    # If someone already configured handlers, don't clobber formatting; just set levels.
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(resolved)
        return

    logging.basicConfig(
        level=resolved,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                tracebacks_show_locals=True,
                show_time=True,
                show_path=True,
            )
        ],
    )
