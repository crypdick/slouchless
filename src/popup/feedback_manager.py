import logging
import threading
import time
from typing import Callable

from PIL import Image

from src.settings import settings
from src.popup import show_slouch_popup
from src.popup.ffplay_feedback import send_feedback_frame

logger = logging.getLogger(__name__)


class FeedbackManager:
    def __init__(self, detector, debug_writer=None):
        self.detector = detector
        self.debug_writer = debug_writer
        self.interval_s = max(0.05, float(settings.popup_feedback_interval_ms) / 1000.0)
        self.pump_fps = float(settings.popup_preview_fps)
        self.pump_dt = 1.0 / self.pump_fps

    def run(
        self,
        camera,
        initial_image: Image.Image,
        should_continue_callback: Callable[[], bool],
    ) -> None:
        """
        Runs the feedback loop, showing the ffplay popup and running inference
        continuously until closed or stopped.
        """
        # Open ffplay feedback window.
        # Note: show_slouch_popup just initializes the window if needed (via open_feedback_window)
        # We might want to rename/refactor that in the future, but using existing generic name.
        show_slouch_popup(initial_image)

        overlay_lock = threading.Lock()
        latest_frame = {"img": initial_image}
        overlay = {
            "kind": "bad",
            "message": "analyzing...",
            "raw_output": "",
            "next_inference_at": time.time(),  # Will be updated after first inference
        }

        # Force ffplay to open immediately with an initial frame.
        send_feedback_frame(
            initial_image,
            kind=str(overlay["kind"]),
            message=str(overlay["message"]),
            raw_output=str(overlay["raw_output"]),
            countdown_secs=0.0,
            fps=int(self.pump_fps),
            thumbnail_size=settings.popup_thumbnail_size,
        )

        stop_inference = threading.Event()

        def _infer_worker() -> None:
            last = 0.0
            while not stop_inference.is_set():
                now = time.time()
                if now - last < self.interval_s:
                    time.sleep(min(0.05, self.interval_s))
                    continue
                last = now

                with overlay_lock:
                    frame = latest_frame["img"]
                if frame is None:
                    continue

                try:
                    result = self.detector.analyze(
                        frame,
                        debug_writer=self.debug_writer,
                    )
                    with overlay_lock:
                        overlay["kind"] = str(result.get("kind") or "error")
                        overlay["message"] = str(result.get("message") or "error")
                        overlay["raw_output"] = str(result.get("raw_output") or "")
                        overlay["next_inference_at"] = time.time() + self.interval_s
                except Exception as e:
                    with overlay_lock:
                        overlay["kind"] = "error"
                        overlay["message"] = f"{type(e).__name__}: {e}"
                        overlay["raw_output"] = ""
                        overlay["next_inference_at"] = time.time() + self.interval_s

        inference_thread = threading.Thread(target=_infer_worker, daemon=True)
        inference_thread.start()

        try:
            while True:
                if not should_continue_callback():
                    break

                img = camera.capture_frame()
                with overlay_lock:
                    latest_frame["img"] = img
                    k = str(overlay["kind"])
                    m = str(overlay["message"])
                    r = str(overlay["raw_output"])
                    next_at = float(overlay["next_inference_at"])

                # Calculate countdown
                countdown = max(0.0, next_at - time.time())

                ok = send_feedback_frame(
                    img,
                    kind=k,
                    message=m,
                    raw_output=r,
                    countdown_secs=countdown,
                    fps=int(self.pump_fps),
                    thumbnail_size=settings.popup_thumbnail_size,
                )
                if not ok:
                    # Popup closed / ffplay died.
                    break

                time.sleep(self.pump_dt)

        except Exception as e:
            logger.exception("Popup handling failed: %s", e)
        finally:
            stop_inference.set()
