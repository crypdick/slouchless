from __future__ import annotations

import logging
import os
import shutil

from PIL import Image

from src.popup.ffplay_feedback import (
    open_feedback_window,
    send_feedback_frame,
)
from src.settings import settings

logger = logging.getLogger(__name__)


def send_ffplay_feedback_frame(
    image: Image.Image,
    *,
    kind: str,
    message: str,
    raw_output: str | None = None,
    fps: int = 15,
) -> bool:
    return send_feedback_frame(
        image,
        kind=kind,
        message=message,
        raw_output=raw_output,
        fps=fps,
        thumbnail_size=settings.popup_thumbnail_size,
    )


def show_slouch_popup(image: Image.Image) -> None:
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RuntimeError(
            "Popup backend 'ffplay' requires a GUI session (DISPLAY/WAYLAND_DISPLAY). "
            "Headless mode is not supported."
        )
    if not shutil.which("ffplay"):
        raise RuntimeError(
            "Popup backend requires `ffplay` (ffmpeg). Install it (ffmpeg/ffplay)."
        )

    # Only supported mode: ffplay "feedback" window.
    open_feedback_window(fps=int(settings.popup_preview_fps))
