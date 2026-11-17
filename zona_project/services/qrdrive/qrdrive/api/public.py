"""Tizim havolasi: /qrdrive/s/<token> — muddat, parol, yuklab olishlar soni, bekor qilish."""
from __future__ import annotations

import hashlib
import hmac
import html
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import config
from ..core.crypto import verify_password
from ..db.models import FileRecord, SystemLink
from ..db.session import get_session
from ..services.files import guess_mime
from .admin.files import stream_remote

router = APIRouter(tags=["public"])

PAGE = """<!doctype html><html lang="uz"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
:root{{color-scheme:light dark;--bg:#f6f7f9;--card:#fff;--fg:#14161a;--mut:#667085;--acc:#2563eb}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d0f12;--card:#16191e;--fg:#e8eaed;--mut:#98a2b3;--acc:#60a5fa}}}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;padding:16px}}
.c{{background:var(--card);border-radius:14px;padding:28px;max-width:380px;width:100%;box-shadow:0 1px 3px #0002}}
h1{{font-size:18px;margin:0 0 6px}}p{{color:var(--mut);margin:0 0 16px}}
input{{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #8884;border-radius:8px;background:transparent;color:inherit;font:inherit}}
button{{margin-top:12px;width:100%;padding:10px;border:0;border-radius:8px;background:var(--acc);color:#fff;font:inherit;cursor:pointer}}
.e{{color:#dc2626;margin-top:10px}}</style></head><body><div class="c">{body}</div></body></html>"""


def page(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(PAGE.format(title=html.escape(title), body=body), status_code=status)


def message(title: str, text: str, status: int) -> HTMLResponse:
    return page(title, f"<h1>{html.escape(title)}</h1><p>{html.escape(text)}</p>", status)


def password_form(name: str, error: str = "") -> HTMLResponse:
    err = f'<div class="e">{html.escape(error)}</div>' if error else ""
    return page("Parol", f"""<h1>{html.escape(name)}</h1><p>Faylni ochish uchun parolni kiriting.</p>
<form method="post"><input type="password" name="password" autofocus required placeholder="Parol">{err}
<button type="submit">Ochish</button></form>""", 401 if error else 200)


async def _serve(token: str, session: AsyncSession, password: str | None):
    link = await session.get(SystemLink, token)
    if link is None or link.revoked:
        return message("Havola yaroqsiz", "Bu havola bekor qilingan yoki mavjud emas.", 404)
    if link.expires_at and link.expires_at < datetime.now(timezone.utc):
        return message("Havola muddati tugagan", "Fayl egasidan yangi havola so'rang.", 410)
    rec = await session.get(FileRecord, link.file_id)
    if rec is None or rec.deleted_at is not None or not rec.storage:
        return message("Fayl topilmadi", "Fayl o'chirilgan bo'lishi mumkin.", 404)
    if link.password_hash:
        if password is None:
            return password_form(rec.original_name)
        if not verify_password(link.password_hash, password):
            return password_form(rec.original_name, "Parol noto'g'ri")
    if rec.kind == "folder":
        return folder_page(token, rec, set_cookie=bool(link.password_hash))
    link.downloads += 1
    rec.downloads = (rec.downloads or 0) + 1
    await session.commit()
    try:
        return await stream_remote(rec.storage, rec.remote_path, rec.stored_name or rec.original_name, rec.mime, download=False)
    except Exception:  # noqa: BLE001
        return message("Fayl vaqtincha mavjud emas", "Saqlash joyi javob bermayapti. Birozdan keyin qayta urinib ko'ring.", 503)


def _cookie_value(token: str) -> str:
    exp = str(int(time.time()) + 3600)
    sig = hmac.new(config.master_key.encode(), f"{token}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{exp}.{sig}"


def _cookie_ok(token: str, value: str) -> bool:
    try:
        exp, sig = value.split(".")
    except ValueError:
        return False
    good = hmac.new(config.master_key.encode(), f"{token}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(sig, good) and int(exp) > time.time()


def _size(n: int | None) -> str:
    n = n or 0
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def folder_page(token: str, rec: FileRecord, set_cookie: bool) -> HTMLResponse:
    """Papka (ochilgan arxiv): ichidagi fayllar ro'yxati, har biri alohida ochiladi."""
    rows = "".join(
        f'<a class="r" href="{token}/{i}"><span>{html.escape(it["name"])}</span><small>{_size(it.get("size"))}</small></a>'
        for i, it in enumerate(rec.items or []))
    body = (f"<h1>📂 {html.escape(rec.stored_name or rec.original_name)}</h1>"
            f"<p>{len(rec.items or [])} ta fayl · {_size(rec.size)}</p><div class='l'>{rows}</div>")
    css = (".l{display:grid;gap:4px}.r{display:flex;justify-content:space-between;gap:12px;padding:9px 10px;border-radius:8px;"
           "color:inherit;text-decoration:none;border:1px solid #8883}.r:hover{border-color:var(--acc)}.r small{color:var(--mut);"
           "white-space:nowrap}.r span{word-break:break-all}</style>")
    page_html = PAGE.format(title=html.escape(rec.original_name), body=body)
    resp = HTMLResponse(page_html.replace("max-width:380px", "max-width:640px").replace("</style>", css, 1))
    if set_cookie:
        resp.set_cookie(f"qrs_{token[:16]}", _cookie_value(token), max_age=3600, httponly=True, samesite="lax")
    return resp


@router.get("/s/{token}/{index}", include_in_schema=False)
async def open_folder_item(token: str, index: int, request: Request, session: AsyncSession = Depends(get_session)):
    link = await session.get(SystemLink, token)
    if link is None or link.revoked or (link.expires_at and link.expires_at < datetime.now(timezone.utc)):
        return message("Havola yaroqsiz", "Bu havola bekor qilingan yoki muddati tugagan.", 404)
    rec = await session.get(FileRecord, link.file_id)
    if rec is None or rec.deleted_at is not None or rec.kind != "folder" or not rec.storage or not 0 <= index < len(rec.items or []):
        return message("Fayl topilmadi", "Fayl o'chirilgan bo'lishi mumkin.", 404)
    if link.password_hash and not _cookie_ok(token, request.cookies.get(f"qrs_{token[:16]}", "")):
        return password_form(rec.original_name)
    name = rec.items[index]["name"]
    link.downloads += 1
    rec.downloads = (rec.downloads or 0) + 1
    await session.commit()
    try:
        return await stream_remote(rec.storage, f"{rec.remote_path.rstrip('/')}/{name}", name.rsplit("/", 1)[-1], guess_mime(name),
                                   download=False)
    except Exception:  # noqa: BLE001
        return message("Fayl vaqtincha mavjud emas", "Saqlash joyi javob bermayapti. Birozdan keyin qayta urinib ko'ring.", 503)


@router.get("/s/{token}", include_in_schema=False)
async def open_link(token: str, session: AsyncSession = Depends(get_session)):
    return await _serve(token, session, None)


@router.post("/s/{token}", include_in_schema=False)
async def open_link_password(token: str, password: str = Form(""), session: AsyncSession = Depends(get_session)):
    return await _serve(token, session, password)
