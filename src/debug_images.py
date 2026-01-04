from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image


def _project_root() -> Path:
    # This file lives in <root>/src/; parent of src is the project root.
    return Path(__file__).resolve().parents[1]


def resolve_debug_dir(dir_setting: str) -> Path:
    p = Path(dir_setting)
    if not p.is_absolute():
        p = _project_root() / p
    return p


def clear_debug_dir(dir_path: Path) -> None:
    if not dir_path.exists():
        return
    for child in dir_path.iterdir():
        if child.is_file():
            try:
                child.unlink()
            except OSError:
                raise RuntimeError(f"Failed to delete debug file: {child}") from None


@dataclass(frozen=True)
class SavedFrame:
    frame_id: str
    path: Path


class DebugFrameWriter:
    def __init__(self, dir_path: Path, max_frames: int = 20) -> None:
        self.dir_path = dir_path
        self.max_frames = max_frames
        self.dir_path.mkdir(parents=True, exist_ok=True)
        self._log_path = self.dir_path / "log.jsonl"

    def _prune(self) -> None:
        frames = sorted(
            [p for p in self.dir_path.glob("*.jpg") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
        )
        extra = len(frames) - self.max_frames
        if extra <= 0:
            return
        for p in frames[:extra]:
            try:
                p.unlink()
            except OSError:
                raise RuntimeError(f"Failed pruning debug frame: {p}") from None

    def save_frame(self, image: Image.Image) -> SavedFrame:
        frame_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{frame_id}.jpg"
        path = self.dir_path / filename
        image.save(path, format="JPEG", quality=90, optimize=True)
        self._prune()
        return SavedFrame(frame_id=frame_id, path=path)

    def log(self, record: dict[str, Any]) -> None:
        # Ensure basic fields so it's easy to grep/parse.
        record = {"ts": datetime.now().isoformat(timespec="seconds"), **record}
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
