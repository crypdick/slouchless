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
    max_tokens: int = Field(default=10, ge=1)
    temperature: float = Field(default=0.0, ge=0.0)
    prompt: str = Field(
        default=(
            "USER: <image>\n"
            "Look at the person's posture. If they are slouching (rounded shoulders, "
            "forward head/neck, hunched/curved upper back), answer 'Yes'. If they are "
            "sitting/standing upright with a neutral spine, answer 'No'.\n"
            "If you cannot determine from the image, answer with 'Error: <short reason>'.\n"
            "Your response must start with exactly one of: Yes, No, or Error:.\n"
            "ASSISTANT:"
        )
    )

    # App
    check_interval_seconds: int = Field(default=30, ge=1)

    # Debug
    debug_save_frames: bool = Field(default=True)
    debug_clear_frames_on_start: bool = Field(default=True)
    debug_max_frames: int = Field(default=20, ge=1)
    debug_frames_dir: str = Field(default="debug_frames")

    # UI
    popup_thumbnail_size: tuple[int, int] = Field(default=(600, 600))
    popup_backend: Literal["notify", "tk"] = Field(default="notify")

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

    @field_validator("popup_backend", "distributed_executor_backend", mode="before")
    @classmethod
    def _lowercase_literals(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
