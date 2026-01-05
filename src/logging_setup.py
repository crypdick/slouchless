from __future__ import annotations

from random import randint
from typing import TYPE_CHECKING

from rich.console import Console
from rich.highlighter import Highlighter

if TYPE_CHECKING:
    from rich.console import RenderableType

console = Console()


class RainbowHighlighter(Highlighter):
    def highlight(self, text):
        for index in range(len(text)):
            text.stylize(f"color({randint(16, 255)})", index, index + 1)


rainbow = RainbowHighlighter()

# Log level ordering
_LEVEL_ORDER = {
    "DEBUG": 0,
    "INFO": 1,
    "WARNING": 2,
    "ERROR": 3,
    "CRITICAL": 4,
}


class Logger:
    """Simple level-aware logger using rich console."""

    def __init__(self, console: Console):
        self._console = console
        self._level = "INFO"

    def set_level(self, level: str) -> None:
        self._level = level.upper()

    def _should_log(self, level: str) -> bool:
        return _LEVEL_ORDER.get(level, 1) >= _LEVEL_ORDER.get(self._level, 1)

    def debug(self, message: RenderableType, **kwargs) -> None:
        if self._should_log("DEBUG"):
            self._console.log(f"[dim]{message}[/dim]", **kwargs)

    def info(self, message: RenderableType, **kwargs) -> None:
        if self._should_log("INFO"):
            self._console.log(message, **kwargs)

    def warning(self, message: RenderableType, **kwargs) -> None:
        if self._should_log("WARNING"):
            self._console.log(f"[yellow]{message}[/yellow]", **kwargs)

    def error(self, message: RenderableType, **kwargs) -> None:
        if self._should_log("ERROR"):
            self._console.log(f"[bold red]{message}[/bold red]", **kwargs)

    def critical(self, message: RenderableType, **kwargs) -> None:
        if self._should_log("CRITICAL"):
            self._console.log(
                f"[bold white on red]{message}[/bold white on red]", **kwargs
            )

    def exception(self, message: RenderableType = "", **kwargs) -> None:
        """Log an error message and print the current exception traceback."""
        if message:
            self.error(message, **kwargs)
        self._console.print_exception(show_locals=True)


log = Logger(console)
