import cv2
import sys
from pathlib import Path
from PIL import Image
from src.settings import settings


class Camera:
    def __init__(self):
        self.device_id, self.device_name = self._resolve_device(
            settings.camera_name, settings.camera_device_id
        )
        self.cap = None

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
        cls, preferred_name: str, fallback_index: int
    ) -> tuple[int, str]:
        preferred_name = (preferred_name or "").strip()
        if preferred_name:
            matches: list[tuple[int, str]] = []
            devices = cls._list_linux_video_devices()
            for idx, name in devices:
                if preferred_name.lower() in name.lower():
                    matches.append((idx, name))
            if not matches:
                available = cls._list_linux_video_devices()
                available_str = (
                    ", ".join([f"{i}:{n}" for i, n in available]) or "(none found)"
                )
                raise RuntimeError(
                    f"Could not find a webcam matching SLOUCHLESS_CAMERA_NAME={preferred_name!r}. "
                    f"Available cameras: {available_str}"
                )
            if len(matches) > 1:
                raise RuntimeError(
                    f"Multiple webcams matched SLOUCHLESS_CAMERA_NAME={preferred_name!r}: {matches}. "
                    "Use a more specific substring."
                )
            return matches[0]

        # Fallback to numeric index
        resolved_name = (
            cls._device_name_from_sys(fallback_index) or f"video{fallback_index}"
        )
        return fallback_index, resolved_name

    def describe(self) -> str:
        return f"{self.device_name} (index={self.device_id})"

    def _ensure_open(self):
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(self.device_id)
            if not self.cap.isOpened():
                raise RuntimeError(f"Could not open camera {self.describe()}")
            # Best-effort: reduce internal buffering so we don't analyze stale frames.
            try:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception as e:
                # Not all backends support this property; warn loudly but continue.
                print(
                    f"WARNING: Failed to set CAP_PROP_BUFFERSIZE: {e}", file=sys.stderr
                )

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
            self.cap.release()
            self.cap = cv2.VideoCapture(self.device_id)
            try:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception as e:
                print(
                    f"WARNING: Failed to set CAP_PROP_BUFFERSIZE: {e}", file=sys.stderr
                )
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
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def __del__(self):
        self.release()
