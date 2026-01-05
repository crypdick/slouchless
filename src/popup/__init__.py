from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from src.popup.ffplay_feedback import (
    close_feedback_window,
    open_feedback_window,
    send_feedback_frame,
)
from src.popup.notify_backend import notify_slouch
from src.settings import settings

logger = logging.getLogger(__name__)


def resolve_popup_backend() -> str:
    """
    Returns effective backend: "ffplay" or "notify".
    """
    backend = settings.popup_backend
    if backend != "auto":
        return backend

    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if has_display and shutil.which("ffplay"):
        return "ffplay"
    return "notify"


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


def show_slouch_popup(
    image: Image.Image,
    *,
    camera_device_id: int | None = None,
    camera_name: str = "",
) -> None:
    backend = resolve_popup_backend()

    if backend == "notify":
        notify_slouch(image)
        return

    if backend != "ffplay":
        raise ValueError(f"Unknown SLOUCHLESS_POPUP_BACKEND={backend!r}")

    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RuntimeError(
            "Popup backend 'ffplay' requires a GUI session (DISPLAY/WAYLAND_DISPLAY). "
            "Set SLOUCHLESS_POPUP_BACKEND=notify if you're running headless."
        )
    if not shutil.which("ffplay"):
        raise RuntimeError(
            "Popup backend 'ffplay' requires `ffplay` (ffmpeg). "
            "Install it or set SLOUCHLESS_POPUP_BACKEND=notify."
        )

    if settings.popup_mode == "feedback":
        open_feedback_window(fps=int(settings.popup_preview_fps))
        return

    if settings.popup_mode == "live":
        if camera_device_id is None:
            raise RuntimeError(
                "Popup mode 'live' requires a concrete camera device id. "
                "Set SLOUCHLESS_CAMERA_DEVICE_ID or pass camera_device_id from the caller."
            )
        dev = f"/dev/video{int(camera_device_id)}"
        if not Path(dev).exists():
            raise RuntimeError(f"Camera device path not found: {dev}")

        cmd: list[str] = [
            "ffplay",
            "-hide_banner",
            "-loglevel",
            "error",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-framedrop",
            "-f",
            "video4linux2",
            "-i",
            dev,
            "-window_title",
            f"Slouchless ({camera_name or dev})",
            "-alwaysontop",
        ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return

    raise ValueError(f"Unknown SLOUCHLESS_POPUP_MODE={settings.popup_mode!r}")


def init_popup_worker() -> None:
    """
    Backwards-compatible no-op (older versions used a background popup worker).
    """


def shutdown_popup_worker() -> None:
    """
    Best-effort cleanup for popup resources (notably the ffplay feedback process).
    """
    close_feedback_window()
