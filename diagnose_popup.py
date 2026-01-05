#!/usr/bin/env python3
"""
Lightweight diagnostics for Slouchless popups (no vLLM, no tray UI).

Usage:
  uv run --active python diagnose_popup.py --device-id 3
  uv run --active python diagnose_popup.py --camera-name "Logi Webcam" --auto-close 5
"""

from __future__ import annotations

import argparse
import os
import time


def main() -> int:
    p = argparse.ArgumentParser(description="Slouchless popup diagnostics")
    p.add_argument("--device-id", type=int, help="OpenCV camera device index")
    p.add_argument("--camera-name", type=str, help="Camera name substring to match")
    p.add_argument(
        "--auto-close", type=int, default=8, help="Auto-close after N seconds (0=never)"
    )
    args = p.parse_args()

    # Set env vars before importing settings (pydantic-settings reads env on import)
    if args.device_id is not None:
        os.environ.setdefault("SLOUCHLESS_CAMERA_DEVICE_ID", str(args.device_id))
    if args.camera_name:
        os.environ.setdefault("SLOUCHLESS_CAMERA_NAME", args.camera_name)

    from src.camera import Camera
    from src.settings import settings
    from src.popup.ffplay_feedback import (
        close_feedback_window,
        send_feedback_frame,
        show_slouch_popup,
    )

    cam = None
    try:
        cam = Camera()
        print(f"Camera: {cam.describe()}")

        show_slouch_popup()

        deadline = time.time() + args.auto_close if args.auto_close > 0 else None
        frame_dt = 1.0 / settings.popup_preview_fps

        while deadline is None or time.time() < deadline:
            img = cam.capture_frame()
            ok = send_feedback_frame(
                img,
                kind="bad",
                message="diagnostic overlay",
                raw_output="Yes",
                thumbnail_size=settings.popup_thumbnail_size,
            )
            if not ok:
                break
            time.sleep(frame_dt)

        print("OK")
        return 0
    finally:
        close_feedback_window()
        if cam:
            cam.release()


if __name__ == "__main__":
    raise SystemExit(main())
