from PIL import Image, ImageDraw, ImageTk, ImageFont
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
import io
from dataclasses import dataclass
import time


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

    def try_recv(self) -> dict[str, Any] | None:
        with self._lock:
            try:
                if not self._conn.poll(0):
                    return None
                msg = self._conn.recv()
            except (EOFError, ConnectionResetError, BrokenPipeError, OSError):
                return None
        return msg if isinstance(msg, dict) else None

    def drain(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        while True:
            msg = self.try_recv()
            if msg is None:
                return out
            out.append(msg)

    def request(self, msg: dict[str, Any], *, wait: bool) -> None:
        with self._lock:
            try:
                self._conn.send(msg)
                if not wait:
                    return
                resp = self._conn.recv()
            except (EOFError, ConnectionResetError, BrokenPipeError, OSError) as e:
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

#
# NOTE: We intentionally do NOT use Tk for feedback streaming (xcb instability on some setups)
# and do NOT use OpenCV HighGUI (often unavailable in headless OpenCV builds). For feedback,
# we render an overlay in Python and stream MJPEG into an ffplay window over stdin.
#


@dataclass
class _FFplayFeedback:
    proc: Any
    fps: int


_ffplay_feedback: _FFplayFeedback | None = None
_ffplay_feedback_closed: bool = False


def _ffplay_feedback_open(*, fps: int) -> None:
    """
    Starts an ffplay window that reads an MJPEG stream from stdin.
    """
    global _ffplay_feedback, _ffplay_feedback_closed
    if _ffplay_feedback is not None and _ffplay_feedback.proc.poll() is None:
        return
    # Reset the "closed" latch when we explicitly open a new popup.
    _ffplay_feedback_closed = False

    if not shutil.which("ffplay"):
        raise RuntimeError("ffplay not found (install ffmpeg/ffplay)")

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
        "-window_title",
        "Slouchless (live feedback)",
        "-f",
        "mjpeg",
        "-i",
        "pipe:0",
        "-alwaysontop",
    ]

    env = os.environ.copy()
    # If the user is on X11, prefer x11; otherwise let SDL decide.
    if env.get("DISPLAY") and not env.get("SDL_VIDEODRIVER"):
        env["SDL_VIDEODRIVER"] = "x11"
    # Force the window to appear in a sane, visible place (SDL can otherwise reuse stale
    # coordinates and spawn off-screen).
    env.setdefault("SDL_VIDEO_WINDOW_POS", "0,0")
    env.setdefault("SDL_VIDEO_CENTERED", "0")

    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=env,
    )
    if p.stdin is None:
        raise RuntimeError("Failed to open ffplay stdin")
    # If ffplay dies immediately, surface stderr (common when DISPLAY/SDL is misconfigured).
    time.sleep(0.15)
    if p.poll() is not None:
        err = ""
        try:
            if p.stderr:
                raw = p.stderr.read() or b""
                if isinstance(raw, bytes):
                    err = raw.decode("utf-8", errors="replace")
                else:
                    err = str(raw)
        except Exception:
            pass
        raise RuntimeError(f"ffplay exited immediately:\n{err}".rstrip())
    print(f"DEBUG: ffplay feedback started (pid={p.pid})")
    _ffplay_feedback = _FFplayFeedback(proc=p, fps=int(fps))


def _ffplay_feedback_close() -> None:
    global _ffplay_feedback, _ffplay_feedback_closed
    ff = _ffplay_feedback
    _ffplay_feedback = None
    _ffplay_feedback_closed = True
    if ff is None:
        return
    try:
        if ff.proc.stdin:
            ff.proc.stdin.close()
    except Exception:
        pass
    try:
        ff.proc.terminate()
    except Exception:
        pass


def send_ffplay_feedback_frame(
    image,
    *,
    kind: str,
    message: str,
    raw_output: str | None = None,
    fps: int = 15,
) -> bool:
    """
    Draw overlay onto the frame and push it into the ffplay feedback window.
    Returns False if the window is closed / ffplay died.
    """

    def _assets_font(name: str) -> Path:
        # src/ui.py lives in <root>/src; assets lives in <root>/assets
        return Path(__file__).resolve().parents[1] / "assets" / name

    def _load_font(path: Path, px: int) -> ImageFont.ImageFont:
        px = int(max(12, px))
        try:
            return ImageFont.truetype(str(path), px)
        except Exception:
            # Built-in bitmap font (no emoji); we draw icons ourselves.
            return ImageFont.load_default()

    def _draw_icon(
        draw: ImageDraw.ImageDraw, *, kind: str, x: int, y: int, size: int
    ) -> None:
        # Simple, high-contrast icons that don't depend on emoji fonts.
        size = int(size)
        x2, y2 = x + size, y + size
        if kind == "good":
            # green circle + check
            draw.ellipse(
                [x, y, x2, y2], fill=(16, 163, 74), outline=(255, 255, 255), width=3
            )
            # checkmark
            draw.line(
                [
                    (x + size * 0.25, y + size * 0.55),
                    (x + size * 0.43, y + size * 0.72),
                ],
                fill=(255, 255, 255),
                width=max(3, size // 10),
            )
            draw.line(
                [
                    (x + size * 0.42, y + size * 0.72),
                    (x + size * 0.78, y + size * 0.30),
                ],
                fill=(255, 255, 255),
                width=max(3, size // 10),
            )
            return
        if kind == "bad":
            # Big red X (comic-book style)
            stroke = max(6, size // 6)
            inset = max(6, size // 8)
            # black outline for contrast
            draw.line(
                [(x + inset, y + inset), (x2 - inset, y2 - inset)],
                fill=(0, 0, 0),
                width=stroke + 4,
            )
            draw.line(
                [(x2 - inset, y + inset), (x + inset, y2 - inset)],
                fill=(0, 0, 0),
                width=stroke + 4,
            )
            # red fill
            draw.line(
                [(x + inset, y + inset), (x2 - inset, y2 - inset)],
                fill=(239, 68, 68),
                width=stroke,
            )
            draw.line(
                [(x2 - inset, y + inset), (x + inset, y2 - inset)],
                fill=(239, 68, 68),
                width=stroke,
            )
            return
        # error: warning triangle + exclamation
        draw.polygon(
            [(x + size * 0.5, y), (x2, y2), (x, y2)],
            fill=(245, 158, 11),
            outline=(255, 255, 255),
        )
        draw.line(
            [(x + size * 0.5, y + size * 0.30), (x + size * 0.5, y + size * 0.72)],
            fill=(0, 0, 0),
            width=max(3, size // 10),
        )
        draw.ellipse(
            [x + size * 0.45, y + size * 0.78, x + size * 0.55, y + size * 0.88],
            fill=(0, 0, 0),
        )

    def _strip_known_emoji_tofu(text: str) -> str:
        """
        Remove specific emoji codepoints we used earlier that can render as tofu boxes
        on many Linux font stacks.
        """
        if not text:
            return ""
        bad_chars = {
            "✅",
            "🚨",
            "⏰",
            "📢",
            "❗",
            "⚠",
            "⚠️",
            "\ufe0f",  # variation selector-16
        }
        cleaned = "".join(ch for ch in text if ch not in bad_chars)
        # collapse whitespace
        cleaned = " ".join(cleaned.split())
        return cleaned.strip()

    # ffplay reads an MJPEG stream, so frame sizes can vary. We still render to a
    # consistent canvas size for stable UX.
    w, h = settings.popup_thumbnail_size
    ff = _ffplay_feedback
    # Important: do NOT auto-reopen ffplay if the user closed the window.
    # `show_slouch_popup(... backend=ffplay, mode=feedback)` is responsible for opening.
    if _ffplay_feedback_closed:
        return False
    if ff is None or ff.proc.poll() is not None or ff.proc.stdin is None:
        return False

    # Prepare fixed-size RGB image (letterboxed).
    canvas = Image.new("RGB", (int(w), int(h)), (0, 0, 0))
    img = image.convert("RGB")
    img.thumbnail((int(w), int(h)))
    ox = (int(w) - img.width) // 2
    oy = (int(h) - img.height) // 2
    canvas.paste(img, (ox, oy))

    # Overlay banner (big, comic-y, high-contrast).
    draw = ImageDraw.Draw(canvas)
    if kind == "good":
        color = (34, 197, 94)
        headline = "GOOD POSTURE"
    elif kind == "bad":
        color = (239, 68, 68)
        headline = "BAD POSTURE!!!"
    else:
        color = (245, 158, 11)
        headline = "MODEL ERROR"

    banner_h = max(120, int(h * 0.20))
    draw.rectangle([0, 0, int(w), banner_h], fill=(0, 0, 0))

    icon_size = int(min(banner_h * 0.72, w * 0.14))
    icon_x = 16
    icon_y = int((banner_h - icon_size) // 2)
    _draw_icon(draw, kind=kind, x=icon_x, y=icon_y, size=icon_size)

    # Font selection: bundled fonts in assets/
    honk = _assets_font("Honk-Regular-VariableFont_MORF,SHLN.ttf")
    glitch = _assets_font("RubikGlitch-Regular.ttf")

    if kind == "good":
        main_font = _load_font(honk, int(banner_h * 0.52))
        sub_font = _load_font(honk, int(banner_h * 0.26))
    else:
        main_font = _load_font(glitch, int(banner_h * 0.50))
        sub_font = _load_font(glitch, int(banner_h * 0.24))

    text_x = icon_x + icon_size + 16
    text_y = int(banner_h * 0.10)

    # Comic-book outline + shadow for the headline.
    for dx, dy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (2, 2)]:
        draw.text((text_x + dx, text_y + dy), headline, font=main_font, fill=(0, 0, 0))
    draw.text((text_x, text_y), headline, font=main_font, fill=color)

    # Secondary line uses the caller's message (can include emojis, but doesn't rely on them).
    msg_clean = _strip_known_emoji_tofu((message or "").strip())
    if msg_clean:
        draw.text(
            (text_x, int(banner_h * 0.58)),
            msg_clean,
            font=sub_font,
            fill=(255, 255, 255),
        )
    if raw_output:
        draw.text(
            (text_x, int(banner_h * 0.78)),
            f"raw: {raw_output[:140]}",
            font=sub_font,
            fill=(200, 200, 200),
        )

    try:
        buf = io.BytesIO()
        canvas.save(buf, format="JPEG", quality=80)
        ff.proc.stdin.write(buf.getvalue())
        ff.proc.stdin.flush()
        return ff.proc.poll() is None
    except (BrokenPipeError, OSError):
        _ffplay_feedback_close()
        return False


def resolve_popup_backend() -> str:
    """
    Resolves the effective popup backend when settings.popup_backend="auto".
    """
    backend = settings.popup_backend
    if backend != "auto":
        return backend

    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if not has_display:
        return "notify"

    # Feedback overlays: we render in Python and stream to an ffplay window.
    if settings.tk_popup_mode == "feedback":
        try:
            if shutil.which("ffplay"):
                return "ffplay"
            return "tk"
        except Exception:
            return "tk"

    if shutil.which("ffplay"):
        return "ffplay"
    return "notify"


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
    backend = resolve_popup_backend()

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
            # Best-effort: (re)start the worker. Starting it in the threaded monitor loop
            # is not ideal, but it's better than crashing outright.
            init_popup_worker()
        if _popup_worker is None or not _popup_worker.is_alive():
            raise RuntimeError(
                "Tk popup worker is not running (failed to start). "
                "If you see xcb/X11 errors above, set SLOUCHLESS_POPUP_BACKEND=notify "
                "or SLOUCHLESS_POPUP_BACKEND=ffplay."
            )

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
        if mode == "feedback":
            raise RuntimeError(
                "Feedback overlay mode does not use Tk. "
                "Use SLOUCHLESS_POPUP_BACKEND=ffplay with SLOUCHLESS_TK_POPUP_MODE=feedback."
            )

        if mode == "live":
            # Save a snapshot for immediate display while live preview starts up.
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                image.save(f, format="JPEG")
                temp_path = f.name

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
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                image.save(f, format="JPEG")
                temp_path = f.name

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
        if settings.tk_popup_mode == "feedback":
            # Feedback overlay is rendered in Python; ffplay only provides the window.
            _ffplay_feedback_open(fps=15)
            return
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


#
# (Removed) Tk feedback streaming and OpenCV HighGUI feedback window.
# Feedback overlays are supported via `send_ffplay_feedback_frame()` only.
#
