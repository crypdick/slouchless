import time
import threading
import sys

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
    from src.camera import Camera

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
                from src.ui import show_slouch_popup, resolve_popup_backend

                # If the popup opens the webcam (ffplay or Tk live), release our capture
                # first to avoid device contention; then reopen afterwards.
                effective_backend = resolve_popup_backend()
                feedback_mode = (
                    settings.tk_popup_mode == "feedback"
                    and effective_backend == "ffplay"
                )
                will_use_webcam = (
                    effective_backend in ("ffplay",)
                    and not feedback_mode
                    or (effective_backend == "tk" and settings.tk_popup_mode == "live")
                )
                print(
                    "DEBUG: popup resolved "
                    f"backend={effective_backend!r} "
                    f"tk_popup_mode={settings.tk_popup_mode!r} "
                    f"feedback_mode={feedback_mode}"
                )

                try:
                    if will_use_webcam:
                        camera.release()

                    show_slouch_popup(
                        image,
                        camera_device_id=camera.device_id,
                        camera_name=camera.device_name,
                    )

                    # Feedback mode: while the popup is open, continuously run inference
                    # and stream frames + status into the popup.
                    if feedback_mode:
                        from src.ui import send_ffplay_feedback_frame
                        import threading

                        interval_s = max(
                            0.05, float(settings.tk_popup_feedback_interval_ms) / 1000.0
                        )

                        # Keep the window updating smoothly even if inference is slow:
                        # - video pump: captures frames ~15fps and streams to ffplay
                        # - inference worker: analyzes latest frame at interval_s and updates overlay text
                        pump_fps = 15.0
                        pump_dt = 1.0 / pump_fps

                        overlay_lock = threading.Lock()
                        latest_frame = {"img": image}
                        overlay = {
                            "kind": "error",
                            "message": "starting…",
                            "raw_output": "",
                        }

                        # Force ffplay to open immediately.
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

                                # For debug visibility, save + log each inference frame in feedback mode.
                                saved_fb = None
                                if debug_writer is not None:
                                    try:
                                        saved_fb = debug_writer.save_frame(frame)
                                        debug_writer.log(
                                            {
                                                "event": "feedback_frame_captured",
                                                "frame_id": saved_fb.frame_id,
                                                "frame_path": str(saved_fb.path),
                                                "camera_index": camera.device_id,
                                                "camera_name": camera.device_name,
                                            }
                                        )
                                    except Exception:
                                        saved_fb = None

                                try:
                                    result = detector.analyze(
                                        frame,
                                        frame_id=(
                                            saved_fb.frame_id if saved_fb else None
                                        ),
                                        frame_path=(
                                            str(saved_fb.path) if saved_fb else None
                                        ),
                                        debug_writer=debug_writer,
                                    )
                                    with overlay_lock:
                                        overlay["kind"] = str(
                                            result.get("kind") or "error"
                                        )
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

                        try:
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
                                    raise StopIteration

                                time.sleep(pump_dt)
                        finally:
                            stop.set()
                except StopIteration:
                    # Popup closed (feedback mode)
                    pass
                except Exception as e:
                    import traceback

                    print("CRITICAL: popup handling failed:\n" + traceback.format_exc())
                    print(f"CRITICAL: {e}", file=sys.stderr)
                finally:
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
    from src.ui import shutdown_popup_worker

    shutdown_popup_worker()


def main():
    print("DEBUG: Starting Slouchless...")
    print(
        "DEBUG: Camera config: "
        f"camera_name={settings.camera_name!r} "
        f"camera_device_id={settings.camera_device_id!r}"
    )

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
        print(f"DEBUG: Cleared debug frames dir: {debug_dir}")

    # Start popup worker EARLY (before any threads/UI) to avoid xcb/X11 crashes when
    # opening Tk windows from a threaded app.
    if settings.popup_backend in ("tk", "auto"):
        import os

        has_display = bool(
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        )
        if settings.popup_backend == "tk" or has_display:
            from src.ui import init_popup_worker

            init_popup_worker()

    # Initialize Detector in MAIN thread to avoid multiprocessing/GIL deadlocks with vLLM
    print("Initializing Slouch Detector (Main Thread)...")
    from src.detector import SlouchDetector

    detector = SlouchDetector()
    print("DEBUG: Detector initialized in Main Thread.")

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
