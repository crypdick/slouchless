from __future__ import annotations

import os
import shutil
import subprocess
import time

from PIL import Image

from src.popup.overlay import render_feedback_frame
from src.logging_setup import log


def open_feedback_window() -> None:
    """Open (or reuse) the ffplay feedback popup window."""
    global _ffplay_proc
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RuntimeError(
            "Popup backend 'ffplay' requires a GUI session (DISPLAY/WAYLAND_DISPLAY). "
            "Headless mode is not supported."
        )
    if not shutil.which("ffplay"):
        raise RuntimeError(
            "Popup backend requires `ffplay` (ffmpeg). Install it (ffmpeg/ffplay)."
        )

    if _ffplay_proc is not None and _ffplay_proc.poll() is None:
        return

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
        "-window_title",
        "Slouchless (live feedback)",
        "-f",
        "mjpeg",
        "-i",
        "pipe:0",
        "-alwaysontop",
    ]

    env = os.environ.copy()
    if env.get("DISPLAY") and not env.get("SDL_VIDEODRIVER"):
        env["SDL_VIDEODRIVER"] = "x11"
    env.setdefault("SDL_VIDEO_WINDOW_POS", "0,0")
    env.setdefault("SDL_VIDEO_CENTERED", "0")

    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=env,
    )
    if p.stdin is None:
        raise RuntimeError("Failed to open ffplay stdin")

    time.sleep(0.15)
    if p.poll() is not None:
        err = ""
        if p.stderr:
            raw = p.stderr.read() or b""
            if isinstance(raw, bytes):
                err = raw.decode("utf-8", errors="replace")
            else:
                err = str(raw)
        raise RuntimeError(f"ffplay exited immediately:\n{err}".rstrip())

    log.debug(f"ffplay feedback started (pid={p.pid})")
    _ffplay_proc = p


def close_feedback_window() -> None:
    global _ffplay_proc
    p = _ffplay_proc
    _ffplay_proc = None
    if p is None:
        return
    try:
        if p.stdin:
            p.stdin.close()
    except Exception:
        pass
    try:
        p.terminate()
    except Exception:
        pass


def send_feedback_frame(
    image: Image.Image,
    *,
    kind: str,
    message: str,
    raw_output: str | None = None,
    countdown_secs: float = 0.0,
    thumbnail_size: tuple[int, int],
) -> bool:
    """
    Pushes a rendered overlay frame into the already-open ffplay feedback window.
    Returns False if the window is closed / ffplay died.
    """
    p = _ffplay_proc
    if p is None or p.poll() is not None or p.stdin is None:
        return False

    payload = render_feedback_frame(
        image,
        kind=kind,
        message=message,
        raw_output=raw_output,
        countdown_secs=countdown_secs,
        thumbnail_size=thumbnail_size,
    )

    try:
        p.stdin.write(payload)
        p.stdin.flush()
        return p.poll() is None
    except (BrokenPipeError, OSError):
        close_feedback_window()
        return False


_ffplay_proc: subprocess.Popen | None = None
