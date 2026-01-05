from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass

from PIL import Image

from src.popup.overlay import render_feedback_frame
from src.logging_setup import log


def show_slouch_popup() -> None:
    """Opens the ffplay feedback popup window."""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RuntimeError(
            "Popup backend 'ffplay' requires a GUI session (DISPLAY/WAYLAND_DISPLAY). "
            "Headless mode is not supported."
        )
    if not shutil.which("ffplay"):
        raise RuntimeError(
            "Popup backend requires `ffplay` (ffmpeg). Install it (ffmpeg/ffplay)."
        )

    open_feedback_window()


@dataclass
class _FFplayFeedback:
    proc: subprocess.Popen


_ffplay_feedback: _FFplayFeedback | None = None
_ffplay_feedback_closed: bool = False


def open_feedback_window() -> None:
    global _ffplay_feedback, _ffplay_feedback_closed
    if _ffplay_feedback is not None and _ffplay_feedback.proc.poll() is None:
        return

    _ffplay_feedback_closed = False

    if not shutil.which("ffplay"):
        raise RuntimeError("ffplay not found (install ffmpeg/ffplay)")

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
        try:
            if p.stderr:
                raw = p.stderr.read() or b""
                if isinstance(raw, bytes):
                    err = raw.decode("utf-8", errors="replace")
                else:
                    err = str(raw)
        except Exception:
            pass
        raise RuntimeError(f"ffplay exited immediately:\n{err}".rstrip())

    log.debug(f"ffplay feedback started (pid={p.pid})")
    _ffplay_feedback = _FFplayFeedback(proc=p)


def close_feedback_window() -> None:
    global _ffplay_feedback, _ffplay_feedback_closed
    ff = _ffplay_feedback
    _ffplay_feedback = None
    _ffplay_feedback_closed = True
    if ff is None:
        return
    try:
        if ff.proc.stdin:
            ff.proc.stdin.close()
    except Exception:
        pass
    try:
        ff.proc.terminate()
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
    if _ffplay_feedback_closed:
        return False
    ff = _ffplay_feedback
    if ff is None or ff.proc.poll() is not None or ff.proc.stdin is None:
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
        ff.proc.stdin.write(payload)
        ff.proc.stdin.flush()
        return ff.proc.poll() is None
    except (BrokenPipeError, OSError):
        close_feedback_window()
        return False
