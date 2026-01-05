from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.settings import settings

logger = logging.getLogger(__name__)


def create_icon_image(
    color: str = "green", size: tuple[int, int] = (64, 64)
) -> Image.Image:
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


def resolve_popup_backend() -> str:
    """
    Returns effective backend: "ffplay" or "notify".
    """
    backend = settings.popup_backend
    if backend != "auto":
        return backend

    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if has_display and shutil.which("ffplay"):
        return "ffplay"
    return "notify"


@dataclass
class _FFplayFeedback:
    proc: subprocess.Popen


_ffplay_feedback: _FFplayFeedback | None = None
_ffplay_feedback_closed: bool = False


def _ffplay_feedback_open(*, fps: int) -> None:
    global _ffplay_feedback, _ffplay_feedback_closed
    if _ffplay_feedback is not None and _ffplay_feedback.proc.poll() is None:
        return

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
    if env.get("DISPLAY") and not env.get("SDL_VIDEODRIVER"):
        env["SDL_VIDEODRIVER"] = "x11"
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

    logger.debug("ffplay feedback started (pid=%s)", p.pid)
    _ffplay_feedback = _FFplayFeedback(proc=p)


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
    image: Image.Image,
    *,
    kind: str,
    message: str,
    raw_output: str | None = None,
    fps: int = 15,
) -> bool:
    """
    Draw overlay onto `image` and push it into the already-open ffplay feedback window.
    Returns False if the window is closed / ffplay died.
    """

    def _assets_font(name: str) -> Path:
        return Path(__file__).resolve().parents[1] / "assets" / name

    def _load_font(path: Path, px: int) -> ImageFont.ImageFont:
        px = int(max(12, px))
        try:
            return ImageFont.truetype(str(path), px)
        except Exception:
            return ImageFont.load_default()

    def _draw_icon(
        draw: ImageDraw.ImageDraw, *, kind: str, x: int, y: int, size: int
    ) -> None:
        size = int(size)
        x2, y2 = x + size, y + size
        if kind == "good":
            draw.ellipse(
                [x, y, x2, y2], fill=(16, 163, 74), outline=(255, 255, 255), width=3
            )
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
            stroke = max(6, size // 6)
            inset = max(6, size // 8)
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
        # error: warning triangle
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
        if not text:
            return ""
        bad_chars = {"✅", "🚨", "⏰", "📢", "❗", "⚠", "⚠️", "\ufe0f"}
        cleaned = "".join(ch for ch in text if ch not in bad_chars)
        return " ".join(cleaned.split()).strip()

    if _ffplay_feedback_closed:
        return False
    ff = _ffplay_feedback
    if ff is None or ff.proc.poll() is not None or ff.proc.stdin is None:
        return False

    w, h = settings.popup_thumbnail_size
    canvas = Image.new("RGB", (int(w), int(h)), (0, 0, 0))
    img = image.convert("RGB")
    img.thumbnail((int(w), int(h)))
    canvas.paste(img, ((int(w) - img.width) // 2, (int(h) - img.height) // 2))

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
    for dx, dy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (2, 2)]:
        draw.text((text_x + dx, text_y + dy), headline, font=main_font, fill=(0, 0, 0))
    draw.text((text_x, text_y), headline, font=main_font, fill=color)

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


def show_slouch_popup(
    image: Image.Image,
    *,
    camera_device_id: int | None = None,
    camera_name: str = "",
) -> None:
    backend = resolve_popup_backend()

    if backend == "notify":
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            image.save(f, format="JPEG")
            temp_path = f.name

        try:
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
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass
        return

    if backend != "ffplay":
        raise ValueError(f"Unknown SLOUCHLESS_POPUP_BACKEND={backend!r}")

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

    if settings.popup_mode == "feedback":
        _ffplay_feedback_open(fps=int(settings.popup_preview_fps))
        return

    if settings.popup_mode == "live":
        if camera_device_id is None:
            raise RuntimeError(
                "Popup mode 'live' requires a concrete camera device id. "
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
            "-i",
            dev,
            "-window_title",
            f"Slouchless ({camera_name or dev})",
            "-alwaysontop",
        ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return

    raise ValueError(f"Unknown SLOUCHLESS_POPUP_MODE={settings.popup_mode!r}")
