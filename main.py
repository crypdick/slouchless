import time
import threading
import sys

from src.camera import Camera
from src.detector import SlouchDetector
from src.ui import (
    SlouchAppUI,
    show_slouch_popup,
    init_popup_worker,
    shutdown_popup_worker,
)
from src.settings import settings
from src.debug_images import DebugFrameWriter, clear_debug_dir, resolve_debug_dir


# Global state
class AppState:
    def __init__(self):
        self.enabled = True
        self.running = True
        self.lock = threading.Lock()


state = AppState()


def monitor_loop(detector):
    print("DEBUG: monitor_loop started")

    # Initialize Camera
    camera = Camera()
    print(f"DEBUG: Using Camera: {camera.describe()}")
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
            print("Capturing frame...")
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
            print("Analyzing...")
            is_slouching = detector.is_slouching(
                image,
                frame_id=(saved.frame_id if saved else None),
                frame_path=(str(saved.path) if saved else None),
                debug_writer=debug_writer,
            )

            if is_slouching:
                print("SLOUCH DETECTED!")
                # If the popup opens the webcam (ffplay or Tk live), release our capture
                # first to avoid device contention; then reopen afterwards.
                will_use_webcam = settings.popup_backend in ("tk", "ffplay", "auto")
                if will_use_webcam:
                    camera.release()

                show_slouch_popup(
                    image,
                    camera_device_id=camera.device_id,
                    camera_name=camera.device_name,
                )

                if will_use_webcam:
                    camera = Camera()
            else:
                print("Posture OK.")

        # Sleep for configured interval
        for _ in range(settings.check_interval_seconds):
            with state.lock:
                if not state.running:
                    break
            time.sleep(1)

    print("Releasing camera...")
    camera.release()
    print("Monitor loop exited.")


def on_toggle(enabled):
    with state.lock:
        state.enabled = enabled
    status = "Enabled" if enabled else "Disabled"
    print(f"Monitoring {status}")


def on_quit():
    print("Quitting application...")
    with state.lock:
        state.running = False
    shutdown_popup_worker()


def main():
    print("DEBUG: Starting Slouchless...")
    print(
        "DEBUG: Camera config: "
        f"camera_name={settings.camera_name!r} "
        f"camera_device_id={settings.camera_device_id!r}"
    )

    if settings.debug_clear_frames_on_start:
        debug_dir = resolve_debug_dir(settings.debug_frames_dir)
        clear_debug_dir(debug_dir)
        print(f"DEBUG: Cleared debug frames dir: {debug_dir}")

    # Start popup worker EARLY (before any threads/UI) to avoid xcb/X11 crashes when
    # opening Tk windows from a threaded app.
    if settings.popup_backend in ("tk", "auto"):
        import os

        has_display = bool(
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        )
        if settings.popup_backend == "tk" or has_display:
            init_popup_worker()

    # Initialize Detector in MAIN thread to avoid multiprocessing/GIL deadlocks with vLLM
    print("Initializing Slouch Detector (Main Thread)...")
    detector = SlouchDetector()
    print("DEBUG: Detector initialized in Main Thread.")

    # Start the monitoring thread, passing the initialized detector
    monitor_thread = threading.Thread(
        target=monitor_loop, args=(detector,), daemon=True
    )
    monitor_thread.start()

    # Start the UI (Blocking)
    ui = SlouchAppUI(toggle_callback=on_toggle, quit_callback=on_quit)
    try:
        ui.run()
    except KeyboardInterrupt:
        on_quit()

    sys.exit(0)


if __name__ == "__main__":
    main()
