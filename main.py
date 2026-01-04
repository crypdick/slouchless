import time
import threading
import sys

from src.camera import Camera
from src.detector import SlouchDetector
from src.ui import SlouchAppUI, show_slouch_popup
from src.settings import settings


# Global state
class AppState:
    def __init__(self):
        self.enabled = True
        self.running = True
        self.lock = threading.Lock()


state = AppState()


def monitor_loop():
    print("Initializing Camera...")
    # Let exceptions propagate (fail fast)
    camera = Camera()

    print("Initializing Slouch Detector (this may take a while)...")
    # Let exceptions propagate (fail fast)
    detector = SlouchDetector()
    print("Detector initialized.")

    while True:
        with state.lock:
            if not state.running:
                break
            is_enabled = state.enabled

        if is_enabled:
            # Capture frame
            print("Capturing frame...")
            # Resize handled inside camera based on settings
            image = camera.capture_frame()

            # Detect
            print("Analyzing...")
            is_slouching = detector.is_slouching(image)

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
    # Start the monitoring thread
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
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
