from __future__ import annotations

import logging


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
    Idempotent-ish logging setup. Safe to call early in main().
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
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
