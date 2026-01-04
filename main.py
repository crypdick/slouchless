import time
import threading
import sys

from src.camera import Camera
from src.detector import SlouchDetector
from src.ui import SlouchAppUI, show_slouch_popup
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
    if settings.DEBUG_SAVE_FRAMES:
        debug_dir = resolve_debug_dir(settings.DEBUG_FRAMES_DIR)
        debug_writer = DebugFrameWriter(debug_dir, max_frames=settings.DEBUG_MAX_FRAMES)

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
                # Show popup
                show_slouch_popup(image)
            else:
                print("Posture OK.")

        # Sleep for configured interval
        for _ in range(settings.CHECK_INTERVAL):
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


def main():
    print("DEBUG: Starting Slouchless...")
    print(f"DEBUG: Webcam ID setting: {settings.CAMERA_DEVICE_ID}")

    if settings.DEBUG_CLEAR_FRAMES_ON_START:
        debug_dir = resolve_debug_dir(settings.DEBUG_FRAMES_DIR)
        clear_debug_dir(debug_dir)
        print(f"DEBUG: Cleared debug frames dir: {debug_dir}")

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
