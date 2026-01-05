from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

"""
This module intentionally stays thin and orchestration-focused.

UI rendering (tray icon drawing, overlay rendering, backend implementations) lives in
dedicated modules under `src.tray` and `src.popup`.
"""

from src.popup import (  # noqa: E402
    init_popup_worker,
    resolve_popup_backend,
    send_ffplay_feedback_frame,
    show_slouch_popup,
    shutdown_popup_worker,
)
from src.tray import SlouchAppUI, create_icon_image  # noqa: E402


__all__ = [
    "SlouchAppUI",
    "create_icon_image",
    "resolve_popup_backend",
    "show_slouch_popup",
    "send_ffplay_feedback_frame",
    "init_popup_worker",
    "shutdown_popup_worker",
]
