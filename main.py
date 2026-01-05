import time
import threading
import sys
import logging

from src.settings import settings
from src.settings import format_settings_for_log
from src.debug_images import DebugFrameWriter, clear_debug_dir, resolve_debug_dir
from src.logging_setup import configure_logging


logger = logging.getLogger(__name__)


# Global state
class AppState:
    def __init__(self):
        self.enabled = True
        self.running = True
        self.lock = threading.Lock()


state = AppState()


def monitor_loop(detector):
    logger.debug("monitor_loop started")

    # Initialize Camera
    from src.camera import Camera

    camera = Camera()
    logger.debug("Using Camera: %s", camera.describe())
    debug_writer = None
    if settings.debug_save_frames:
        debug_dir = resolve_debug_dir(settings.debug_frames_dir)
        debug_writer = DebugFrameWriter(debug_dir, max_frames=settings.debug_max_frames)

    while True:
        with state.lock:
            if not state.running:
                break
            is_enabled = state.enabled

        if is_enabled:
            # Capture frame
            logger.debug("Capturing frame...")
            image = camera.capture_frame()
            saved = None
            if debug_writer is not None:
                saved = debug_writer.save_frame(image)
                debug_writer.log(
                    {
                        "event": "frame_captured",
                        "frame_id": saved.frame_id,
                        "frame_path": str(saved.path),
                        "camera_index": camera.device_id,
                        "camera_name": camera.device_name,
                    }
                )

            # Detect
            logger.debug("Analyzing...")
            is_slouching = detector.is_slouching(
                image,
                frame_id=(saved.frame_id if saved else None),
                frame_path=(str(saved.path) if saved else None),
                debug_writer=debug_writer,
            )

            if is_slouching:
                logger.info("SLOUCH DETECTED!")
                from src.ui import show_slouch_popup, send_ffplay_feedback_frame

                try:
                    # Open ffplay feedback window.
                    show_slouch_popup(image)

                    interval_s = max(
                        0.05, float(settings.popup_feedback_interval_ms) / 1000.0
                    )
                    pump_fps = float(settings.popup_preview_fps)
                    pump_dt = 1.0 / pump_fps

                    overlay_lock = threading.Lock()
                    latest_frame = {"img": image}
                    overlay = {
                        "kind": "error",
                        "message": "starting…",
                        "raw_output": "",
                    }

                    # Force ffplay to open immediately with an initial frame.
                    send_ffplay_feedback_frame(
                        image,
                        kind=str(overlay["kind"]),
                        message=str(overlay["message"]),
                        raw_output=str(overlay["raw_output"]),
                        fps=int(pump_fps),
                    )

                    stop = threading.Event()

                    def _infer_worker() -> None:
                        last = 0.0
                        while not stop.is_set():
                            now = time.time()
                            if now - last < interval_s:
                                time.sleep(min(0.05, interval_s))
                                continue
                            last = now

                            with overlay_lock:
                                frame = latest_frame["img"]
                            if frame is None:
                                continue

                            try:
                                result = detector.analyze(
                                    frame,
                                    debug_writer=debug_writer,
                                )
                                with overlay_lock:
                                    overlay["kind"] = str(result.get("kind") or "error")
                                    overlay["message"] = str(
                                        result.get("message") or "error"
                                    )
                                    overlay["raw_output"] = str(
                                        result.get("raw_output") or ""
                                    )
                            except Exception as e:
                                with overlay_lock:
                                    overlay["kind"] = "error"
                                    overlay["message"] = f"{type(e).__name__}: {e}"
                                    overlay["raw_output"] = ""

                    t = threading.Thread(target=_infer_worker, daemon=True)
                    t.start()

                    while True:
                        with state.lock:
                            if not state.running:
                                break

                        img = camera.capture_frame()
                        with overlay_lock:
                            latest_frame["img"] = img
                            k = str(overlay["kind"])
                            m = str(overlay["message"])
                            r = str(overlay["raw_output"])

                        ok = send_ffplay_feedback_frame(
                            img,
                            kind=k,
                            message=m,
                            raw_output=r,
                            fps=int(pump_fps),
                        )
                        if not ok:
                            # Popup closed / ffplay died.
                            break

                        time.sleep(pump_dt)

                    stop.set()
                except Exception as e:
                    logger.exception("Popup handling failed: %s", e)
            else:
                logger.debug("Posture OK.")

        # Sleep for configured interval
        for _ in range(settings.check_interval_seconds):
            with state.lock:
                if not state.running:
                    break
            time.sleep(1)

    logger.info("Releasing camera...")
    camera.release()
    logger.info("Monitor loop exited.")


def on_toggle(enabled):
    with state.lock:
        state.enabled = enabled
    status = "Enabled" if enabled else "Disabled"
    logger.info("Monitoring %s", status)


def on_quit():
    logger.info("Quitting application...")
    with state.lock:
        state.running = False


def main():
    configure_logging(settings.log_level)
    logger.info("Starting Slouchless...")
    logger.debug("Settings:\n%s", format_settings_for_log(settings))

    # Ray can emit noisy (and typically harmless) errors if its internal OpenTelemetry
    # metrics exporter agent can't start/connect. We don't use Ray metrics in Slouchless,
    # so disable metrics collection by default to silence these logs.
    #
    # Users who *do* want Ray metrics can override by exporting:
    #   RAY_enable_metrics_collection=1
    import os

    os.environ.setdefault("RAY_enable_metrics_collection", "0")

    if settings.debug_clear_frames_on_start:
        debug_dir = resolve_debug_dir(settings.debug_frames_dir)
        clear_debug_dir(debug_dir)
        logger.debug("Cleared debug frames dir: %s", debug_dir)

    # Initialize Detector in MAIN thread to avoid multiprocessing/GIL deadlocks with vLLM
    logger.info("Initializing Slouch Detector (Main Thread)...")
    from src.detector import SlouchDetector

    detector = SlouchDetector()
    logger.info("Detector initialized in Main Thread.")

    # Start the monitoring thread, passing the initialized detector
    monitor_thread = threading.Thread(
        target=monitor_loop, args=(detector,), daemon=True
    )
    monitor_thread.start()

    # Start the UI (Blocking)
    from src.ui import SlouchAppUI

    ui = SlouchAppUI(toggle_callback=on_toggle, quit_callback=on_quit)
    try:
        ui.run()
    except KeyboardInterrupt:
        on_quit()

    sys.exit(0)


if __name__ == "__main__":
    main()
