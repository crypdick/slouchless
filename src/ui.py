from __future__ import annotations

"""
Thin module to orchestrate the UI.

UI rendering (tray icon drawing, overlay rendering, backend implementations) lives in
dedicated modules under `src.tray` and `src.popup`.
"""

from src.popup.ffplay_feedback import send_feedback_frame, show_slouch_popup  # noqa: E402
from src.tray import SlouchAppUI, create_icon_image  # noqa: E402


__all__ = [
    "SlouchAppUI",
    "create_icon_image",
    "show_slouch_popup",
    "send_feedback_frame",
]
