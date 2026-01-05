from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _assets_font(name: str) -> Path:
    # This file lives in <root>/src/popup/; parents[2] is the repo root.
    return Path(__file__).resolve().parents[2] / "assets" / name


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


def render_feedback_frame(
    image: Image.Image,
    *,
    kind: str,
    message: str,
    raw_output: str | None,
    thumbnail_size: tuple[int, int],
) -> bytes:
    """
    Renders a framed/overlaid JPEG for the ffplay feedback window and returns bytes.
    """
    w, h = thumbnail_size
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

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=80)
    return buf.getvalue()
