from PIL import Image, ImageDraw, ImageTk
import tkinter as tk
from src.settings import settings
import subprocess
import os
from pathlib import Path
from typing import Optional, Tuple, Any
import threading
import multiprocessing
import traceback
import shutil


def create_icon_image(color="green", size=(64, 64)):
    """Generates a simple colored circle icon."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, size[0] - 8, size[1] - 8), fill=color)
    return image


class SlouchAppUI:
    def __init__(self, toggle_callback, quit_callback):
        self.toggle_callback = toggle_callback
        self.quit_callback = quit_callback
        self.icon = None
        self.enabled = True

    def _on_toggle(self, icon, item):
        self.enabled = not self.enabled
        self.toggle_callback(self.enabled)
        self.update_icon()

    def _on_quit(self, icon, item):
        self.quit_callback()
        icon.stop()

    def update_icon(self):
        color = "green" if self.enabled else "red"
        if self.icon:
            self.icon.icon = create_icon_image(color)

    def run(self):
        """Starts the system tray icon. Blocks until quit."""
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem(
                "Enable/Disable", self._on_toggle, checked=lambda item: self.enabled
            ),
            pystray.MenuItem("Quit", self._on_quit),
        )

        self.icon = pystray.Icon(
            "Slouchless", create_icon_image("green"), "Slouch Detector", menu
        )
        self.icon.run()


class _PopupWorkerClient:
    def __init__(self, proc: multiprocessing.Process, conn: Any) -> None:
        self._proc = proc
        self._conn = conn
        self._lock = threading.Lock()

    def is_alive(self) -> bool:
        return self._proc.is_alive()

    def request(self, msg: dict[str, Any], *, wait: bool) -> None:
        with self._lock:
            try:
                self._conn.send(msg)
                if not wait:
                    return
                resp = self._conn.recv()
            except EOFError as e:
                raise RuntimeError(
                    "Popup worker process exited unexpectedly (EOF on Pipe). "
                    "This is often an X11/Tk crash; check logs above for xcb errors."
                ) from e

        if not isinstance(resp, dict) or not resp.get("ok", False):
            err = (resp or {}).get("error", "unknown error")
            tb = (resp or {}).get("traceback")
            raise RuntimeError(f"Popup worker failed: {err}\n{tb or ''}".rstrip())

    def shutdown(self, *, timeout_s: float = 2.0) -> None:
        try:
            self.request({"cmd": "shutdown"}, wait=True)
        except Exception:
            pass
        try:
            self._proc.join(timeout=timeout_s)
        except Exception:
            pass


_popup_worker: _PopupWorkerClient | None = None


def _popup_worker_main(conn: Any) -> None:
    """
    Dedicated popup worker process. We keep a single process alive to avoid forking
    GUI/X11 clients (Tk) at the moment slouch is detected (which can crash with xcb
    when threads are already running in the main process).
    """
    while True:
        msg = conn.recv()
        cmd = (msg or {}).get("cmd")
        if cmd == "shutdown":
            conn.send({"ok": True})
            return

        try:
            if cmd == "live":
                show_live_popup_process(
                    device_id=int(msg["device_id"]),
                    device_name=str(msg.get("device_name") or ""),
                    message=str(
                        msg.get("message") or "You are slouching! Sit up straight!"
                    ),
                    preview_size=tuple(
                        msg.get("preview_size") or settings.popup_thumbnail_size
                    ),
                    update_ms=int(msg.get("update_ms") or settings.tk_popup_update_ms),
                    initial_image_path=msg.get("initial_image_path"),
                    auto_close_seconds=int(msg.get("auto_close_seconds") or 0),
                )
                conn.send({"ok": True})
                continue

            if cmd == "static":
                show_popup_process(str(msg["image_path"]))
                conn.send({"ok": True})
                continue

            raise ValueError(f"Unknown popup cmd={cmd!r}")
        except Exception as e:
            conn.send(
                {
                    "ok": False,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )


def init_popup_worker() -> None:
    """
    Start popup worker early (before threads/UI start) to avoid xcb/X11 crashes.
    Safe to call multiple times.
    """
    global _popup_worker
    if _popup_worker is not None and _popup_worker.is_alive():
        return

    # Use spawn to avoid forking GUI/X11 state (which can trigger xcb aborts).
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=True)
    p = ctx.Process(target=_popup_worker_main, args=(child_conn,), daemon=True)
    p.start()
    _popup_worker = _PopupWorkerClient(proc=p, conn=parent_conn)


def shutdown_popup_worker() -> None:
    global _popup_worker
    if _popup_worker is None:
        return
    _popup_worker.shutdown()
    _popup_worker = None


def show_popup_process(image_path):
    """
    Helper to run tkinter in a separate process/script context if needed.
    """
    root = tk.Tk()
    root.title("SLOUCH DETECTED!")

    # Load image (best-effort). On some Linux setups, ImageTk can fail when a process is
    # created via fork (or when Tk/Pillow extensions are mismatched). We'll fall back
    # to a text-only popup if we can't render the image.
    tk_img = None
    try:
        pil_img = Image.open(image_path)
        pil_img.thumbnail(settings.popup_thumbnail_size)
        tk_img = ImageTk.PhotoImage(pil_img)
        label = tk.Label(root, image=tk_img)
        label.pack()
    except Exception as e:
        fallback = tk.Label(
            root,
            text=f"(Image preview unavailable)\n{e}",
            font=("Helvetica", 10),
            fg="gray",
            justify="left",
        )
        fallback.pack(padx=10, pady=10)

    text_label = tk.Label(
        root,
        text="You are slouching! Sit up straight!",
        font=("Helvetica", 16),
        fg="red",
    )
    text_label.pack()

    # Auto focus
    root.attributes("-topmost", True)
    root.update()
    root.attributes("-topmost", False)

    root.mainloop()
    try:
        Path(image_path).unlink(missing_ok=True)
    except OSError:
        # Best-effort cleanup; not fatal.
        pass


def show_live_popup_process(
    *,
    device_id: int,
    device_name: str,
    message: str,
    preview_size: Tuple[int, int],
    update_ms: int,
    initial_image_path: Optional[str] = None,
    auto_close_seconds: int = 0,
) -> None:
    """
    Tk popup that shows a live webcam preview until closed.
    Runs in a separate process (spawn) to avoid Tk/Pillow issues with fork.
    """
    import cv2

    root = tk.Tk()
    root.title("SLOUCH DETECTED!")

    header = tk.Label(
        root,
        text=message,
        font=("Helvetica", 16),
        fg="red",
    )
    header.pack(padx=10, pady=(10, 6))

    sub = tk.Label(
        root,
        text=f"Camera: {device_name} (index={device_id})",
        font=("Helvetica", 10),
        fg="gray",
    )
    sub.pack(padx=10, pady=(0, 8))

    img_label = tk.Label(root)
    img_label.pack(padx=10, pady=10)

    # Best-effort initial snapshot while the camera warms up.
    if initial_image_path:
        try:
            pil_img = Image.open(initial_image_path)
            pil_img.thumbnail(preview_size)
            tk_img = ImageTk.PhotoImage(pil_img)
            img_label.configure(image=tk_img)
            img_label.image = tk_img
        except Exception:
            pass

    cap = cv2.VideoCapture(device_id)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"Could not open camera index={device_id} for live popup")

    # Reduce buffering if supported.
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    alive = {"running": True}

    def _cleanup() -> None:
        alive["running"] = False
        try:
            cap.release()
        except Exception:
            pass
        if initial_image_path:
            try:
                Path(initial_image_path).unlink(missing_ok=True)
            except OSError:
                pass

    def _on_close() -> None:
        _cleanup()
        try:
            root.destroy()
        except Exception:
            pass

    root.protocol("WM_DELETE_WINDOW", _on_close)

    if auto_close_seconds and auto_close_seconds > 0:
        root.after(int(auto_close_seconds * 1000), _on_close)

    def _tick() -> None:
        if not alive["running"]:
            return

        ok, frame = cap.read()
        if ok and frame is not None:
            # OpenCV BGR -> PIL RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(frame_rgb)
            pil_img.thumbnail(preview_size)
            tk_img = ImageTk.PhotoImage(pil_img)
            img_label.configure(image=tk_img)
            img_label.image = tk_img  # prevent GC

        root.after(update_ms, _tick)

    btn = tk.Button(root, text="Close", command=_on_close)
    btn.pack(pady=(0, 12))

    # Auto focus
    root.attributes("-topmost", True)
    root.update()
    root.attributes("-topmost", False)

    _tick()
    root.mainloop()
    _cleanup()


def show_slouch_popup(
    image, *, camera_device_id: int | None = None, camera_name: str = ""
):
    """
    Spawns a popup to show the user they are slouching.
    We use a temporary file to pass the image to a fresh process/thread safe method
    or just display it if we can.
    """
    backend = settings.popup_backend
    if backend == "auto":
        has_display = bool(
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        )
        # Prefer ffplay for a real live window on Linux; Tk image rendering is unreliable
        # on some setups (and Pillow's ImageTk extension can be broken).
        if has_display and shutil.which("ffplay"):
            backend = "ffplay"
        else:
            backend = "notify"

    if backend == "notify":
        # Save image to temp file to pass to notification daemon.
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            image.save(f, format="JPEG")
            temp_path = f.name

        # Linux: best-effort desktop notification. Most daemons will show the icon image.
        # If this fails, raise loudly (user asked to fail fast).
        try:
            # Try to attach the selfie as an actual image when supported (e.g. dunst).
            # Fallback: icon-only.
            try:
                subprocess.run(
                    [
                        "notify-send",
                        "Slouchless",
                        "You are slouching! Sit up straight!",
                        "-i",
                        temp_path,
                        "-h",
                        f"string:image-path:{temp_path}",
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except subprocess.CalledProcessError:
                subprocess.run(
                    [
                        "notify-send",
                        "Slouchless",
                        "You are slouching! Sit up straight!",
                        "-i",
                        temp_path,
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass
            return
        except FileNotFoundError as e:
            raise RuntimeError(
                "Popup backend 'notify' requires `notify-send` (libnotify). "
                "Install it or set SLOUCHLESS_POPUP_BACKEND=tk."
            ) from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"notify-send failed: {e.stderr}") from e

    if backend == "tk":
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise RuntimeError(
                "Popup backend 'tk' requires a GUI session (DISPLAY/WAYLAND_DISPLAY). "
                "Set SLOUCHLESS_POPUP_BACKEND=notify if you're running headless."
            )

        if _popup_worker is None or not _popup_worker.is_alive():
            raise RuntimeError(
                "Tk popup worker is not running. This is required to avoid xcb/X11 crashes "
                "in threaded apps. Initialize it early in `main()` via `init_popup_worker()`."
            )

        # Save a snapshot for immediate display while live preview starts up.
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            image.save(f, format="JPEG")
            temp_path = f.name

        # If camera id wasn't provided, fall back to the configured device id; if that's
        # unset too, we can't reliably open the same device for the live preview.
        device_id = (
            int(camera_device_id)
            if camera_device_id is not None
            else (
                settings.camera_device_id
                if settings.camera_device_id is not None
                else None
            )
        )

        mode = settings.tk_popup_mode
        if mode == "live":
            if device_id is None:
                raise RuntimeError(
                    "Tk popup mode 'live' requires a concrete camera device id. "
                    "Set SLOUCHLESS_CAMERA_DEVICE_ID or pass camera_device_id from the caller."
                )

            _popup_worker.request(
                {
                    "cmd": "live",
                    "device_id": int(device_id),
                    "device_name": (camera_name or f"video{device_id}"),
                    "message": "You are slouching! Sit up straight!",
                    "preview_size": settings.popup_thumbnail_size,
                    "update_ms": settings.tk_popup_update_ms,
                    "initial_image_path": temp_path,
                    "auto_close_seconds": settings.tk_popup_auto_close_seconds,
                },
                wait=bool(settings.tk_popup_blocking),
            )
            return

        if mode == "static":
            _popup_worker.request(
                {"cmd": "static", "image_path": temp_path},
                wait=bool(settings.tk_popup_blocking),
            )
            return

        raise ValueError(f"Unknown SLOUCHLESS_TK_POPUP_MODE={mode!r}")

    if backend == "ffplay":
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise RuntimeError(
                "Popup backend 'ffplay' requires a GUI session (DISPLAY/WAYLAND_DISPLAY). "
                "Set SLOUCHLESS_POPUP_BACKEND=notify if you're running headless."
            )
        if not shutil.which("ffplay"):
            raise RuntimeError(
                "Popup backend 'ffplay' requires `ffplay` (ffmpeg). "
                "Install it or set SLOUCHLESS_POPUP_BACKEND=notify."
            )
        if camera_device_id is None:
            raise RuntimeError(
                "Popup backend 'ffplay' requires a concrete camera device id. "
                "Set SLOUCHLESS_CAMERA_DEVICE_ID or pass camera_device_id from the caller."
            )

        dev = f"/dev/video{int(camera_device_id)}"
        if not Path(dev).exists():
            raise RuntimeError(f"Camera device path not found: {dev}")

        cmd: list[str] = [
            "ffplay",
            "-hide_banner",
            "-loglevel",
            "error",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-framedrop",
            "-f",
            "video4linux2",
        ]
        if settings.camera_resize_to:
            w, h = settings.camera_resize_to
            cmd += ["-video_size", f"{int(w)}x{int(h)}"]

        cmd += [
            "-i",
            dev,
            "-window_title",
            "Slouchless (fix posture, then close)",
            "-alwaysontop",
        ]

        # Blocking mode: wait until the user closes the window.
        # Non-blocking: return immediately.
        if settings.tk_popup_blocking:
            subprocess.run(cmd, check=True)
        else:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return

    raise ValueError(f"Unknown SLOUCHLESS_POPUP_BACKEND={backend!r}")
