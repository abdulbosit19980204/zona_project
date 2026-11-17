"""QR kod: o'lcham, rang, markazda logo, pastida matn. PNG yoki PDF (chop etish uchun)."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import qrcode
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_M
from PIL import Image, ImageDraw, ImageFont

from ..core.config import config

LOGO_FILE = "logo.png"


def logo_path() -> Path:
    return config.assets_dir / LOGO_FILE


def _color(value: str, default: str) -> str:
    value = (value or "").strip()
    return value if value.startswith("#") and len(value) in (4, 7) else default


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int, max_lines: int = 2) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
            continue
        if line:
            lines.append(line)
        line = word
        while draw.textlength(line, font=font) > width and len(line) > 1:
            line = line[:-1]
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
    return lines


def render(url: str, style: dict[str, Any] | None = None, caption: str = "") -> Image.Image:
    style = style or {}
    size = max(200, min(int(style.get("size") or 600), 2000))
    fg, bg = _color(style.get("fg", ""), "#000000"), _color(style.get("bg", ""), "#FFFFFF")
    use_logo = bool(style.get("logo")) and logo_path().is_file()
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H if use_logo else ERROR_CORRECT_M, border=3, box_size=10)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fg, back_color=bg).convert("RGB").resize((size, size), Image.NEAREST)

    if use_logo:
        logo = Image.open(logo_path()).convert("RGBA")
        side = size // 5
        logo.thumbnail((side, side))
        pad = max(4, side // 10)
        box = Image.new("RGB", (logo.width + pad * 2, logo.height + pad * 2), bg)
        box.paste(logo, (pad, pad), logo)
        img.paste(box, ((size - box.width) // 2, (size - box.height) // 2))

    if caption:
        font = _font(max(14, size // 22))
        draw = ImageDraw.Draw(img)
        lines = _wrap(draw, caption, font, size - 40)
        line_h = int(font.size * 1.3) if hasattr(font, "size") else 20
        canvas = Image.new("RGB", (size, size + line_h * len(lines) + 16), bg)
        canvas.paste(img, (0, 0))
        d = ImageDraw.Draw(canvas)
        y = size
        for line in lines:
            w = d.textlength(line, font=font)
            d.text(((size - w) / 2, y), line, fill=fg, font=font)
            y += line_h
        img = canvas
    return img


def caption_for(style: dict[str, Any], filename: str, company: str) -> str:
    mode = (style or {}).get("caption", "filename")
    if mode == "filename":
        return filename
    if mode == "company":
        return company
    if mode == "custom":
        return str(style.get("caption_text") or "")
    return ""


def png(url: str, style: dict[str, Any] | None = None, caption: str = "") -> bytes:
    buf = io.BytesIO()
    render(url, style, caption).save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def pdf(url: str, style: dict[str, Any] | None = None, caption: str = "") -> bytes:
    """A4 sahifa markazida QR (chop etish uchun)."""
    img = render(url, {**(style or {}), "size": 1200}, caption)
    page = Image.new("RGB", (2480, 3508), "#FFFFFF")  # A4, 300 dpi
    page.paste(img, ((page.width - img.width) // 2, 500))
    buf = io.BytesIO()
    page.save(buf, format="PDF", resolution=300)
    return buf.getvalue()
