from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    # This file lives in <root>/src/; parent of src is the project root.
    return Path(__file__).resolve().parents[1]


def _parse_size_tuple(value: Any) -> tuple[int, int] | None:
    """
    Accepts:
      - (w, h) / [w, h]
      - JSON strings like "[640, 480]"
      - Strings like "640x480", "640,480", "640 480"
      - "" / None -> None
    """
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        if len(value) != 2:
            raise ValueError("Expected 2 items for size tuple")
        return (int(value[0]), int(value[1]))
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None

        # Fast path: common delimiter formats.
        for sep in ("x", ",", " "):
            if sep in s:
                parts = [p for p in s.replace("x", sep).split(sep) if p.strip()]
                if len(parts) == 2:
                    return (int(parts[0].strip()), int(parts[1].strip()))
        raise ValueError(
            "Invalid size tuple string. Use e.g. '640x480' or JSON like '[640, 480]'."
        )
    raise TypeError(f"Unsupported size tuple type: {type(value)}")


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables and optional `.env`.
    """

    model_config = SettingsConfigDict(
        env_prefix="SLOUCHLESS_",
        # Use an absolute path so `.env` is loaded even if the process CWD isn't the repo root.
        env_file=_project_root() / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Camera
    camera_name: str = Field(default="", description="Webcam name substring to match")
    camera_device_id: int | None = Field(
        default=None,
        ge=0,
        description="OpenCV device index (optional; auto-detect if unset)",
    )
    camera_resize_to: tuple[int, int] | None = Field(default=(640, 480))
    camera_grab_frames: int = Field(default=2, ge=0)

    # Detector / VLM
    model_name: str = Field(default="ybelkada/llava-1.5-7b-hf-awq")
    gpu_memory_utilization: float = Field(default=0.7, ge=0.0, le=1.0)
    quantization: str = Field(default="awq_marlin")
    max_num_seqs: int = Field(default=1, ge=1)
    enforce_eager: bool = Field(default=True)
    distributed_executor_backend: Literal["ray", "mp"] = Field(default="ray")
    max_tokens: int = Field(default=80, ge=1)
    temperature: float = Field(default=0.0, ge=0.0)
    prompt: str = Field(
        default=(
            "USER: <image>\n"
            "Check this person's posture. Say 'Yes' with advice if ANY of these are true:\n"
            "- Head/neck leaning forward (ear ahead of shoulder)\n"
            "- Shoulders rounded forward\n"
            "- Upper back curved/hunched\n"
            "- Spine not straight\n\n"
            "Say 'No' ONLY if spine is reasonably straight with head directly over shoulders. Posture doesn't have to be perfect, we are just alerting if the person has obviously bad posture.\n\n"
            "FORMAT: Start with Yes/No/Error\n"
            "- Yes, <what to fix>\n"
            "- No\n"
            "- Error: <reason>\n\n"
            "EXAMPLES (you don't need to use these exact reasons):\n"
            "- Yes, pull shoulders back under your ears\n"
            "- Yes, tuck chin - head is forward\n"
            "- Yes, straighten upper back\n"
            "- No\n"
            "- Error: person not in frame\n"
            "- Error: image is completely black\n\n"
            "ASSISTANT:"
        )
    )

    # App
    check_interval_seconds: int = Field(default=15, ge=1)

    # Debug
    debug_save_frames: bool = Field(default=True)
    debug_clear_frames_on_start: bool = Field(default=True)
    debug_max_frames: int = Field(default=20, ge=1)
    debug_frames_dir: str = Field(default="debug_frames")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Python logging level (e.g. INFO, DEBUG).",
    )

    # UI
    popup_thumbnail_size: tuple[int, int] = Field(default=(600, 600))
    popup_feedback_interval_ms: int = Field(
        default=3000,
        ge=50,
        le=10_000,
        description="Inference cadence while the feedback popup is open (ms).",
    )
    popup_preview_fps: int = Field(
        default=15,
        ge=1,
        le=60,
        description="Preview framerate pushed to the ffplay window.",
    )

    @field_validator("camera_resize_to", mode="before")
    @classmethod
    def _validate_camera_resize_to(cls, v: Any) -> tuple[int, int] | None:
        return _parse_size_tuple(v)

    @field_validator("popup_thumbnail_size", mode="before")
    @classmethod
    def _validate_popup_thumbnail_size(cls, v: Any) -> tuple[int, int]:
        parsed = _parse_size_tuple(v)
        if parsed is None:
            raise ValueError("popup_thumbnail_size cannot be empty")
        return parsed

    @field_validator("distributed_executor_backend", mode="before")
    @classmethod
    def _lowercase_literals(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v


def format_settings_for_log(
    s: Settings,
    *,
    max_str: int = 220,
) -> str:
    """
    Stable, readable Settings dump for logs.

    - Sorts keys for deterministic output
    - Truncates very long strings (e.g. prompt)
    """
    data = s.model_dump()
    lines: list[str] = []
    for k in sorted(data.keys()):
        v = data[k]
        if isinstance(v, str) and len(v) > max_str:
            preview = v[: max_str - 3].rstrip() + "..."
            v = f"{preview} (len={len(data[k])})"
        lines.append(f"{k}={v!r}")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
