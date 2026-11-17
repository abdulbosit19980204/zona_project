"""Papka va fayl nomlari: shablonlar va xavfsizlantirish (kirill va o'zbek harflari saqlanadi)."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
_SPACES = re.compile(r"\s+")


def safe_name(name: str, limit: int = 150, fallback: str = "fayl") -> str:
    name = unicodedata.normalize("NFC", name or "")
    name = _SPACES.sub(" ", _BAD.sub("_", name)).strip(" .")
    if not name:
        return fallback
    if len(name) <= limit:
        return name
    stem, dot, ext = name.rpartition(".")
    if dot and 0 < len(ext) <= 10:
        return stem[: limit - len(ext) - 1].rstrip(" .") + "." + ext
    return name[:limit].rstrip(" .")


def slug(value: str, limit: int = 64) -> str:
    return safe_name(value, limit, fallback="xodim")


def _values(employee_name: str, department: str, original: str, at: datetime) -> dict[str, str]:
    return {
        "xodim": employee_name, "bo'lim": department or "Umumiy", "bolim": department or "Umumiy",
        "yyyy": f"{at:%Y}", "mm": f"{at:%m}", "dd": f"{at:%d}",
        "sana": f"{at:%Y-%m-%d}", "vaqt": f"{at:%H-%M-%S}", "asl_nom": original,
    }


def _render(template: str, values: dict[str, str]) -> str:
    return re.sub(r"\{([^{}]+)\}", lambda m: values.get(m.group(1).strip(), m.group(0)), template)


def render_folder(template: str, base: str, employee_folder: str, department: str, at: datetime) -> str:
    values = _values(employee_folder, department, "", at)
    parts = [safe_name(p, 80, fallback="") for p in _render(template or "{xodim}", values).split("/")]
    parts = [p for p in parts if p]
    base_parts = [p for p in (base or "/").split("/") if p]
    return "/" + "/".join(base_parts + parts)


def render_filename(template: str, original: str, employee_folder: str, at: datetime) -> str:
    """{asl_nom} — kengaytmasiz asl nom; kengaytma (.pdf) har doim nom oxiriga qo'yiladi."""
    original = safe_name(original)
    stem, dot, ext = original.rpartition(".")
    if not dot or not stem or len(ext) > 10 or " " in ext:
        stem, ext = original, ""
    name = _render(template or "{asl_nom}", _values(employee_folder, "", stem, at)).strip(" ._")
    return safe_name(f"{name or stem}.{ext}" if ext else (name or stem), 180)


def validate_template(template: str) -> bool:
    known = set(_values("", "", "", datetime.now()))
    return all(m.strip() in known for m in re.findall(r"\{([^{}]+)\}", template))
