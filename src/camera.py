import cv2
from PIL import Image
from src.settings import settings


class Camera:
    def __init__(self):
        self.device_id = settings.CAMERA_DEVICE_ID
        self.cap = None

    def _ensure_open(self):
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(self.device_id)
            if not self.cap.isOpened():
                raise RuntimeError(
                    f"Could not open camera with device id {self.device_id}"
                )

    def capture_frame(self):
        """
        Captures a frame from the webcam.

        Returns:
            PIL.Image: The captured image.
        """
        self._ensure_open()

        ret, frame = self.cap.read()
        if not ret:
            # Try to reopen once
            self.cap.release()
            self.cap = cv2.VideoCapture(self.device_id)
            ret, frame = self.cap.read()
            if not ret:
                raise RuntimeError("Failed to capture frame from camera")

        # Convert from BGR (OpenCV) to RGB (PIL)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame_rgb)

        # Resize based on settings
        if settings.CAMERA_RESIZE_TO:
            image = image.resize(settings.CAMERA_RESIZE_TO, Image.Resampling.LANCZOS)

        return image

    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def __del__(self):
        self.release()
