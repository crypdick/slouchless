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
    countdown_secs: float = 0.0,
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
        headline = "BAD POSTURE"
    else:
        color = (245, 158, 11)
        headline = "MODEL ERROR"

    banner_h = max(140, int(h * 0.24))
    draw.rectangle([0, 0, int(w), banner_h], fill=(0, 0, 0))

    icon_size = int(min(banner_h * 0.50, w * 0.12))
    icon_x = 16
    icon_y = int(banner_h * 0.08)
    _draw_icon(draw, kind=kind, x=icon_x, y=icon_y, size=icon_size)

    honk = _assets_font("Honk-Regular-VariableFont_MORF,SHLN.ttf")
    glitch = _assets_font("RubikGlitch-Regular.ttf")
    if kind == "good":
        main_font = _load_font(honk, int(banner_h * 0.36))
        sub_font = _load_font(honk, int(banner_h * 0.18))
    else:
        main_font = _load_font(glitch, int(banner_h * 0.34))
        sub_font = _load_font(glitch, int(banner_h * 0.16))

    text_x = icon_x + icon_size + 16
    text_y = int(banner_h * 0.02)
    for dx, dy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (2, 2)]:
        draw.text((text_x + dx, text_y + dy), headline, font=main_font, fill=(0, 0, 0))
    draw.text((text_x, text_y), headline, font=main_font, fill=color)

    # Draw countdown timer below headline
    countdown_font = _load_font(glitch, int(banner_h * 0.18))
    countdown_text = f"Next: {countdown_secs:.1f}s"
    countdown_y = int(banner_h * 0.36)

    # Draw countdown background pill
    pill_padding = 8
    bbox = draw.textbbox((text_x, countdown_y), countdown_text, font=countdown_font)
    pill_rect = [
        bbox[0] - pill_padding,
        bbox[1] - pill_padding // 2,
        bbox[2] + pill_padding,
        bbox[3] + pill_padding // 2,
    ]
    draw.rounded_rectangle(pill_rect, radius=8, fill=(40, 40, 40))
    draw.text(
        (text_x, countdown_y), countdown_text, font=countdown_font, fill=(180, 180, 180)
    )

    # Show the model's feedback message below countdown
    msg_clean = _strip_known_emoji_tofu((message or "").strip())
    if msg_clean:
        # Wrap long messages
        max_chars = 45
        if len(msg_clean) > max_chars:
            # Simple word-wrap
            words = msg_clean.split()
            lines = []
            current_line = ""
            for word in words:
                if len(current_line) + len(word) + 1 <= max_chars:
                    current_line = f"{current_line} {word}".strip()
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
            msg_clean = "\n".join(lines[:2])  # Max 2 lines

        draw.text(
            (text_x, int(banner_h * 0.58)),
            msg_clean,
            font=sub_font,
            fill=(255, 255, 255),
        )

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=80)
    return buf.getvalue()
