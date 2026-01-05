"""
Fast popup debugging harness (NO vLLM).

Goal: iterate on popup/video overlay issues without waiting for model init.

Examples:
  # ffplay feedback window (recommended; draws overlay in Python, ffplay provides the window):
  SLOUCHLESS_POPUP_BACKEND=ffplay SLOUCHLESS_POPUP_MODE=feedback uv run --active debug_popup.py --mode ffplay

  # Auto backend selection (will pick what is available):
  SLOUCHLESS_POPUP_BACKEND=auto SLOUCHLESS_POPUP_MODE=feedback uv run --active debug_popup.py --mode auto
"""

from __future__ import annotations

import argparse
import logging
import sys
import time


def _dummy_feedback() -> tuple[str, str, str]:
    """
    Alternates feedback every ~2 seconds so you can see UI updates without vLLM.
    """
    t = time.time()
    phase = int(t // 2) % 3
    if phase == 0:
        return ("good", "good posture", "No")
    if phase == 1:
        return ("bad", "bad posture!", "Yes")
    return ("error", "dummy error (for UI testing)", "Error: dummy")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mode",
        choices=["auto", "ffplay"],
        default="auto",
        help="Which popup backend path to test (no vLLM).",
    )
    ap.add_argument(
        "--fps",
        type=float,
        default=8.0,
        help="UI/update FPS for streaming frames (independent of any model cadence).",
    )
    args = ap.parse_args()

    from src.camera import Camera
    from src.settings import settings
    from src.logging_setup import configure_logging
    from src.ui import (
        show_slouch_popup,
        resolve_popup_backend,
        send_ffplay_feedback_frame,
    )

    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    # Sanity: make sure the user actually enabled feedback mode, since this script is
    # specifically about the overlay window.
    if settings.popup_mode != "feedback":
        raise RuntimeError(
            "debug_popup.py expects SLOUCHLESS_POPUP_MODE=feedback "
            f"(got {settings.popup_mode!r})."
        )

    cam = Camera()
    logger.info("camera = %s", cam.describe())
    try:
        # Open window
        first = cam.capture_frame()
        show_slouch_popup(
            first, camera_device_id=cam.device_id, camera_name=cam.device_name
        )
        backend = resolve_popup_backend() if args.mode == "auto" else args.mode
        logger.info("effective backend = %s", backend)

        dt = 1.0 / max(0.5, float(args.fps))
        while True:
            img = cam.capture_frame()
            kind, msg, raw = _dummy_feedback()

            if backend == "ffplay":
                ok = send_ffplay_feedback_frame(
                    img, kind=kind, message=msg, raw_output=raw, fps=int(args.fps)
                )
                if not ok:
                    logger.info("ffplay window closed")
                    return 0
            else:
                raise RuntimeError(
                    f"debug_popup.py only supports ffplay for feedback (got backend={backend!r})."
                )

            time.sleep(dt)
    finally:
        try:
            cam.release()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
