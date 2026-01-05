#!/usr/bin/env python3
"""
Lightweight diagnostics for Slouchless popups (no vLLM, no tray UI).

Usage examples:
  uv run --active python diagnose_popup.py --device-id 3
  uv run --active python diagnose_popup.py --camera-name "Logi Webcam" --auto-close 5

This script opens the ffplay feedback popup and streams frames briefly to validate
the full path end-to-end.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import time
import traceback


def _set_default_env(k: str, v: str) -> None:
    if os.environ.get(k) is None:
        os.environ[k] = v


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Slouchless popup diagnostics")
    p.add_argument(
        "--device-id", type=int, default=None, help="OpenCV camera device index"
    )
    p.add_argument(
        "--camera-name",
        type=str,
        default=None,
        help="Camera name substring (Linux /sys/class/video4linux/.../name)",
    )
    p.add_argument(
        "--blocking",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If true, keep streaming until you close the popup.",
    )
    p.add_argument(
        "--auto-close",
        type=int,
        default=8,
        help="Auto-close after N seconds (0 disables). Default: 8",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    # Force a fast test configuration unless the user overrides via env.
    _set_default_env("SLOUCHLESS_POPUP_PREVIEW_FPS", "15")

    if args.device_id is not None:
        _set_default_env("SLOUCHLESS_CAMERA_DEVICE_ID", str(int(args.device_id)))
    if args.camera_name:
        _set_default_env("SLOUCHLESS_CAMERA_NAME", args.camera_name)

    print("=== slouchless popup diagnostics ===")
    print(f"python: {sys.version.split()[0]}  ({sys.executable})")
    print(f"platform: {platform.platform()}")
    print(
        f"DISPLAY={os.environ.get('DISPLAY')!r} WAYLAND_DISPLAY={os.environ.get('WAYLAND_DISPLAY')!r}"
    )
    print(
        f"SLOUCHLESS_POPUP_PREVIEW_FPS={os.environ.get('SLOUCHLESS_POPUP_PREVIEW_FPS')!r}"
    )
    print(
        f"SLOUCHLESS_CAMERA_DEVICE_ID={os.environ.get('SLOUCHLESS_CAMERA_DEVICE_ID')!r}"
    )
    print(f"SLOUCHLESS_CAMERA_NAME={os.environ.get('SLOUCHLESS_CAMERA_NAME')!r}")
    print("===================================")

    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        print(
            "ERROR: no GUI session detected (DISPLAY/WAYLAND_DISPLAY are unset).",
            file=sys.stderr,
        )
        return 2

    # Import AFTER env vars are set so pydantic-settings picks them up.
    from src.camera import Camera
    from src.settings import settings
    from src.popup.ffplay_feedback import close_feedback_window
    from src.ui import send_ffplay_feedback_frame, show_slouch_popup

    cam = None
    try:
        cam = Camera()
        print(f"Camera resolved: {cam.describe()}")

        # Open popup window/path
        first = cam.capture_frame()
        show_slouch_popup(first)

        # Feedback mode: stream frames for N seconds (or until window closes).
        deadline = (
            None if int(args.auto_close) <= 0 else (time.time() + int(args.auto_close))
        )
        while True:
            if deadline is not None and time.time() >= deadline:
                break
            img = cam.capture_frame()
            ok = send_ffplay_feedback_frame(
                img,
                kind="bad",
                message="diagnostic overlay",
                raw_output="Yes",
                fps=int(settings.popup_preview_fps),
            )
            if not ok:
                break
            if not args.blocking and deadline is None:
                break
            time.sleep(1.0 / max(1.0, float(settings.popup_preview_fps)))

        close_feedback_window()
        print("OK: feedback path executed and cleaned up.")
        return 0
    except Exception:
        print("ERROR: popup diagnostics failed:", file=sys.stderr)
        traceback.print_exc()
        try:
            close_feedback_window()
        except Exception:
            pass
        return 1
    finally:
        try:
            if cam is not None:
                cam.release()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
