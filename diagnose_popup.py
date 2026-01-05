#!/usr/bin/env python3
"""
Lightweight diagnostics for Slouchless popups (no vLLM, no tray UI).

Usage:
  uv run --active python diagnose_popup.py
  uv run --active python diagnose_popup.py --auto-close 5

Camera selection via env vars (or .env file):
  SLOUCHLESS_CAMERA_DEVICE_ID=3 uv run --active python diagnose_popup.py
  SLOUCHLESS_CAMERA_NAME="Logi Webcam" uv run --active python diagnose_popup.py
"""

from __future__ import annotations

import time
from typing import Annotated

import typer
from rich.console import Console

console = Console()


def main(
    auto_close: Annotated[
        int,
        typer.Option("--auto-close", help="Auto-close after N seconds (0=never)"),
    ] = 8,
) -> None:
    """Slouchless popup diagnostics."""
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
        console.print(f"Camera: {cam.describe()}")

        show_slouch_popup()

        deadline = time.time() + auto_close if auto_close > 0 else None
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

        console.print("[green]OK[/green]")
    finally:
        close_feedback_window()
        if cam:
            cam.release()


if __name__ == "__main__":
    typer.run(main)
