from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image


def notify_slouch(image: Image.Image) -> None:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        image.save(f, format="JPEG")
        temp_path = f.name

    try:
        subprocess.run(
            [
                "notify-send",
                "Slouchless",
                "You are slouching! Sit up straight!",
                "-i",
                temp_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    finally:
        try:
            Path(temp_path).unlink(missing_ok=True)
        except OSError:
            pass
