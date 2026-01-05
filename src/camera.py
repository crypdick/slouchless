import cv2
import sys
from pathlib import Path
from PIL import Image
from src.settings import settings


class Camera:
    def __init__(self):
        # Ensure this always exists, even if device resolution raises.
        self.cap = None
        self.device_id, self.device_name = self._resolve_device(
            settings.camera_name, settings.camera_device_id
        )

    @staticmethod
    def _device_name_from_sys(index: int) -> str | None:
        # Linux: /sys/class/video4linux/video{index}/name
        p = Path(f"/sys/class/video4linux/video{index}/name")
        if not p.exists():
            return None
        try:
            return p.read_text(encoding="utf-8").strip()
        except OSError:
            return None

    @classmethod
    def _list_linux_video_devices(cls) -> list[tuple[int, str]]:
        devices: list[tuple[int, str]] = []
        for idx in range(0, 32):
            name = cls._device_name_from_sys(idx)
            if name:
                devices.append((idx, name))
        return devices

    @classmethod
    def _resolve_device(
        cls, preferred_name: str, fallback_index: int | None
    ) -> tuple[int, str]:
        preferred_name = (preferred_name or "").strip()

        if preferred_name:
            return cls._resolve_by_name(preferred_name, fallback_index)

        if fallback_index is not None:
            return cls._resolve_by_index(fallback_index)

        return cls._auto_detect()

    @classmethod
    def _resolve_by_name(
        cls, preferred_name: str, fallback_index: int | None
    ) -> tuple[int, str]:
        matches: list[tuple[int, str]] = []
        devices = cls._list_linux_video_devices()
        for idx, name in devices:
            if preferred_name.lower() in name.lower():
                matches.append((idx, name))

        if not matches:
            available_str = (
                ", ".join([f"{i}:{n}" for i, n in devices]) or "(none found)"
            )
            raise RuntimeError(
                f"Could not find a webcam matching SLOUCHLESS_CAMERA_NAME={preferred_name!r}. "
                f"Available cameras: {available_str}"
            )

        if len(matches) > 1:
            return cls._disambiguate_matches(matches, preferred_name, fallback_index)

        return matches[0]

    @classmethod
    def _disambiguate_matches(
        cls,
        matches: list[tuple[int, str]],
        preferred_name: str,
        fallback_index: int | None,
    ) -> tuple[int, str]:
        # If we have multiple matches but exactly one is an exact match, prefer it.
        exact_matches = [
            (idx, name)
            for idx, name in matches
            if name.strip().lower() == preferred_name.lower()
        ]

        # Allow disambiguation via explicit device id if provided.
        if fallback_index is not None:
            for idx, name in matches:
                if idx == fallback_index:
                    return (idx, name)
            raise RuntimeError(
                f"SLOUCHLESS_CAMERA_DEVICE_ID={fallback_index} did not match any camera "
                f"that matched SLOUCHLESS_CAMERA_NAME={preferred_name!r}: {matches}."
            )

        # If the name is an exact match for multiple devices, deterministically pick the
        # FIRST exact match (in the discovered order) but warn loudly.
        if len(exact_matches) > 1:
            chosen = exact_matches[0]
            print(
                f"WARNING: Multiple webcams exactly matched SLOUCHLESS_CAMERA_NAME="
                f"{preferred_name!r}: {exact_matches}. "
                f"Auto-selecting first match: {chosen[0]}. "
                "Set SLOUCHLESS_CAMERA_DEVICE_ID to silence this warning.",
                file=sys.stderr,
            )
            return chosen

        ids = [idx for idx, _ in matches]
        raise RuntimeError(
            f"Multiple webcams matched SLOUCHLESS_CAMERA_NAME={preferred_name!r}: {matches}. "
            f"Set SLOUCHLESS_CAMERA_DEVICE_ID to one of {ids}, or use a more specific substring."
        )

    @classmethod
    def _resolve_by_index(cls, index: int) -> tuple[int, str]:
        resolved_name = cls._device_name_from_sys(index) or f"video{index}"
        return index, resolved_name

    @classmethod
    def _auto_detect(cls) -> tuple[int, str]:
        available = cls._list_linux_video_devices()
        if len(available) == 1:
            return available[0]

        available_str = ", ".join([f"{i}:{n}" for i, n in available]) or "(none found)"
        raise RuntimeError(
            "No camera configured. Set SLOUCHLESS_CAMERA_NAME (recommended) or "
            "SLOUCHLESS_CAMERA_DEVICE_ID. "
            f"Available cameras: {available_str}"
        )

    def describe(self) -> str:
        return f"{self.device_name} (index={self.device_id})"

    def _ensure_open(self):
        if self.cap is None or not self.cap.isOpened():
            self._open_cap()

    def _open_cap(self):
        if self.cap is not None:
            self.cap.release()

        self.cap = cv2.VideoCapture(self.device_id)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open camera {self.describe()}")

        # Best-effort: reduce internal buffering so we don't analyze stale frames.
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception as e:
            # Not all backends support this property; warn loudly but continue.
            print(f"WARNING: Failed to set CAP_PROP_BUFFERSIZE: {e}", file=sys.stderr)

    def capture_frame(self):
        """
        Captures a frame from the webcam.

        Returns:
            PIL.Image: The captured image.
        """
        self._ensure_open()

        # Some webcams buffer frames; grabbing a couple frames helps ensure the read is "fresh".
        for _ in range(max(0, settings.camera_grab_frames)):
            try:
                self.cap.grab()
            except Exception as e:
                raise RuntimeError(f"Camera grab failed: {e}") from e

        ret, frame = self.cap.read()
        if not ret:
            # Try to reopen once
            self._open_cap()
            ret, frame = self.cap.read()
            if not ret:
                raise RuntimeError("Failed to capture frame from camera")

        # Convert from BGR (OpenCV) to RGB (PIL)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame_rgb)

        # Resize based on settings
        if settings.camera_resize_to:
            image = image.resize(settings.camera_resize_to, Image.Resampling.LANCZOS)

        return image

    def release(self):
        cap = getattr(self, "cap", None)
        if cap is not None:
            cap.release()
            self.cap = None

    def __del__(self):
        self.release()
