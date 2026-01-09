import subprocess
import threading
import sys
from pathlib import Path

from pyfiglet import figlet_format
from rich_pixels import Pixels

from src.settings import settings
from src.settings import format_settings_for_log
from src.debug_images import DebugFrameWriter, clear_debug_dir, resolve_debug_dir
from src.logging_setup import console, log, rainbow

ASSETS_DIR = Path(__file__).parent / "assets"

enabled_event = threading.Event()
enabled_event.set()
stop_event = threading.Event()


def monitor_loop(detector):
    from src.camera import Camera

    camera = Camera()
    log.info(f"Using Camera: {camera.describe()}")
    debug_writer = None
    if settings.debug_save_frames:
        debug_dir = resolve_debug_dir(settings.debug_frames_dir)
        debug_writer = DebugFrameWriter(debug_dir, max_frames=settings.debug_max_frames)

    while not stop_event.is_set():
        if enabled_event.is_set():
            # Capture frame
            try:
                log.debug("Capturing frame...")
                image = camera.capture_frame()
            except Exception as e:
                # Don't let transient camera issues kill the monitoring thread.
                log.exception(f"Error capturing frame: {e}")
                # Sleep for configured interval, but wake promptly on quit.
                if stop_event.wait(timeout=settings.check_interval_seconds):
                    break
                continue
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
            try:
                log.debug("Analyzing...")
                result = detector.analyze(
                    image,
                    frame_id=(saved.frame_id if saved else None),
                    frame_path=(str(saved.path) if saved else None),
                    debug_writer=debug_writer,
                )
            except Exception as e:
                # Safety net: never crash the whole app because a single frame failed.
                log.exception(f"Error analyzing frame: {e}")
                if stop_event.wait(timeout=settings.check_interval_seconds):
                    break
                continue
            if result.get("kind") == "error":
                # Avoid printing "Posture OK" when the model couldn't see the frame.
                log.warning(f"Skipping frame (detector error): {result.get('message')}")
                if stop_event.wait(timeout=settings.check_interval_seconds):
                    break
                continue

            is_slouching = result.get("slouching") is True

            if is_slouching:
                log.error("SLOUCH DETECTED!")
                from src.popup.feedback_manager import FeedbackManager

                manager = FeedbackManager(detector, debug_writer)

                def _should_continue():
                    return not stop_event.is_set()

                manager.run(camera, image, _should_continue)
            else:
                console.log(rainbow("✓ Posture OK!"))

        # Sleep for configured interval, but wake promptly on quit.
        if stop_event.wait(timeout=settings.check_interval_seconds):
            break

    log.info("Releasing camera...")
    camera.release()
    log.info("Monitor loop exited.")


def on_toggle(enabled):
    if enabled:
        enabled_event.set()
    else:
        enabled_event.clear()
    status = "Enabled" if enabled else "Disabled"
    log.info(f"Monitoring {status}")


def on_quit():
    log.info("Quitting application...")
    stop_event.set()


def main():
    log.set_level(settings.log_level)

    # Print the bonk doge and ASCII banner at startup
    bonk_path = ASSETS_DIR / "bonk.webp"
    if bonk_path.exists():
        pixels = Pixels.from_image_path(bonk_path, resize=(40, 20))
        console.print(pixels)

    banner = figlet_format("Slouchless", font="slant")
    subprocess.run(["lolcat"], input=banner, text=True)
    log.info(f"Settings:\n{format_settings_for_log(settings)}")

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
        log.debug(f"Cleared debug frames dir: {debug_dir}")

    # Initialize Detector in MAIN thread to avoid multiprocessing/GIL deadlocks with vLLM
    log.debug("Initializing Slouch Detector (Main Thread)...")
    from src.detector import SlouchDetector

    detector = SlouchDetector()
    log.debug("Detector initialized in Main Thread.")

    # Start the monitoring thread, passing the initialized detector
    monitor_thread = threading.Thread(
        target=monitor_loop, args=(detector,), daemon=True
    )
    monitor_thread.start()

    # Start the UI (Blocking)
    from src.tray import SlouchAppUI

    ui = SlouchAppUI(toggle_callback=on_toggle, quit_callback=on_quit)
    try:
        ui.run()
    except KeyboardInterrupt:
        on_quit()

    sys.exit(0)


if __name__ == "__main__":
    main()
