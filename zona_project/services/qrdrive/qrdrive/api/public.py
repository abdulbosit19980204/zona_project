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


# ---------------- katta fayllar uchun bir martalik veb-yuklash (/u/<token>) ----------------
UPLOAD_TEXTS = {
    "uz": {"title": "Faylni yuklash", "lead": "Fayl 20 MB dan katta — Telegram bunday faylni botga bermaydi. Shu yerda yuklang, "
                                             "QR kod va havola Telegram'dagi chatingizga keladi.",
           "pick": "Faylni tanlang", "send": "Yuklash", "public": "🌐 Public", "private": "🔒 Private",
           "done": "✅ Yuklandi! QR kod bir necha soniyada Telegram'ga keladi. Bu oynani yopishingiz mumkin.",
           "err": "Yuklab bo'lmadi", "big": "Fayl juda katta. Ruxsat: {mb} MB gacha.", "expected": "Botga yuborilgan fayl",
           "invalid": "Havola yaroqsiz yoki muddati tugagan. Botga faylni qayta yuboring — yangi havola beriladi.",
           "used": "Bu havola orqali fayl allaqachon yuklangan. Yana fayl uchun botga qayta yuboring."},
    "ru": {"title": "Загрузка файла", "lead": "Файл больше 20 МБ — Telegram не отдаёт такие файлы ботам. Загрузите его здесь, "
                                             "QR-код и ссылка придут в ваш чат в Telegram.",
           "pick": "Выберите файл", "send": "Загрузить", "public": "🌐 Public", "private": "🔒 Private",
           "done": "✅ Загружено! QR-код придёт в Telegram через несколько секунд. Окно можно закрыть.",
           "err": "Не удалось загрузить", "big": "Файл слишком большой. Допустимо: до {mb} МБ.", "expected": "Файл, отправленный боту",
           "invalid": "Ссылка недействительна или устарела. Отправьте файл боту ещё раз — придёт новая ссылка.",
           "used": "По этой ссылке файл уже загружен. Для нового файла отправьте его боту ещё раз."},
}

UPLOAD_SCRIPT = """<script>
(function(){var f=document.getElementById('f'),b=document.getElementById('b'),p=document.getElementById('p'),m=document.getElementById('m'),
bar=document.getElementById('bar'),d=document.body.dataset,max=+d.max;
function fail(t){m.className='e';m.textContent=t||d.err;b.disabled=false;f.disabled=false}
f.onchange=function(){b.disabled=!f.files.length;m.textContent='';if(f.files.length&&f.files[0].size>max){m.className='e';m.textContent=d.big;b.disabled=true}};
b.onclick=function(){var file=f.files[0];if(!file)return;b.disabled=true;f.disabled=true;p.style.display='block';
var v=document.querySelector('input[name=v]:checked');var x=new XMLHttpRequest();x.open('POST',location.pathname);
x.setRequestHeader('X-File-Name',encodeURIComponent(file.name));if(v)x.setRequestHeader('X-Visibility',v.value);
x.upload.onprogress=function(e){if(e.lengthComputable){var pc=Math.round(e.loaded/e.total*100);bar.style.width=pc+'%';bar.textContent=pc+'%'}};
x.onload=function(){var r={};try{r=JSON.parse(x.responseText)}catch(e){}
if(x.status==200&&r.ok){m.className='ok';m.textContent=d.done;bar.style.width='100%'}else fail(r.detail)};
x.onerror=function(){fail()};x.send(file)}})();
</script>"""


async def _ticket(session: AsyncSession, token: str):
    from ..db.models import TgAccount, UploadTicket
    ticket = await session.get(UploadTicket, token)
    acc = await session.get(TgAccount, ticket.account_id) if ticket else None
    return ticket, acc


def _ticket_state(ticket, acc) -> str:
    if ticket is None or acc is None:
        return "invalid"
    if ticket.used_at is not None:
        return "used"
    exp = ticket.expires_at if ticket.expires_at.tzinfo else ticket.expires_at.replace(tzinfo=timezone.utc)
    return "invalid" if exp < datetime.now(timezone.utc) else "ok"


@router.get("/u/{token}", include_in_schema=False)
async def upload_page(token: str, session: AsyncSession = Depends(get_session)):
    from .. import settings_store
    ticket, acc = await _ticket(session, token)
    tx = UPLOAD_TEXTS.get(getattr(acc, "lang", "uz"), UPLOAD_TEXTS["uz"])
    state = _ticket_state(ticket, acc)
    if state != "ok":
        return message(tx["title"], tx[state], 410)
    settings = await settings_store.load(session)
    max_mb = int(settings.get("max_file_mb") or 100)
    vis = ""
    if (settings.get("visibility_mode") or "ask") == "ask":
        default = settings.get("default_visibility") or "public"
        vis = "<div class='v'>" + "".join(
            f"<label><input type='radio' name='v' value='{k}'{' checked' if k == default else ''}> {tx[k]}</label>"
            for k in ("public", "private")) + "</div>"
    expected = (f"<p class='x'>{tx['expected']}: <b>{html.escape(ticket.name)}</b>"
                f"{' · ' + _size(ticket.size) if ticket.size else ''}</p>") if ticket.name else ""
    body = (f"<h1>{tx['title']}</h1><p>{tx['lead']}</p>{expected}"
            f"<label class='pick'>{tx['pick']}<input id='f' type='file'></label>{vis}"
            f"<button id='b' disabled>{tx['send']}</button>"
            f"<div id='p' class='prog'><div id='bar'></div></div><div id='m'></div>")
    style = ("<style>.pick{display:block;font-size:13px;color:var(--mut)}.pick input{margin-top:6px}"
             ".v{display:flex;gap:16px;margin-top:12px}.v label{display:flex;gap:6px;align-items:center}.v input{width:auto}"
             "button:disabled{opacity:.5;cursor:default}.prog{display:none;margin-top:12px;height:22px;border-radius:6px;"
             "background:#8883;overflow:hidden}#bar{height:100%;width:0;background:var(--acc);color:#fff;font-size:12px;"
             "text-align:center;line-height:22px;transition:width .2s}#m{margin-top:12px}.ok{color:#16a34a}.x{font-size:13px}</style>")
    doc = PAGE.format(title=html.escape(tx["title"]), body=body).replace("</head>", style + "</head>", 1)
    attrs = (f" data-max='{max_mb * 1024 * 1024}' data-big='{html.escape(tx['big'].format(mb=max_mb), quote=True)}'"
             f" data-done='{html.escape(tx['done'], quote=True)}' data-err='{html.escape(tx['err'], quote=True)}'")
    doc = doc.replace("<body>", f"<body{attrs}>", 1).replace("</body>", UPLOAD_SCRIPT + "</body>", 1)
    return HTMLResponse(doc, headers={"Cache-Control": "no-store"})


@router.post("/u/{token}", include_in_schema=False)
async def upload_file(token: str, request: Request, session: AsyncSession = Depends(get_session)):
    """Fayl so'rov tanasida (oqim bilan diskka yoziladi — xotiraga yig'ilmaydi), nomi X-File-Name sarlavhasida."""
    from urllib.parse import unquote

    from fastapi.responses import JSONResponse

    from .. import settings_store
    from ..services import accounts
    from ..services.audit import add_audit
    from ..services.files import enqueue, spool_path
    from ..services.pipeline import allowed

    ticket, acc = await _ticket(session, token)
    tx = UPLOAD_TEXTS.get(getattr(acc, "lang", "uz"), UPLOAD_TEXTS["uz"])
    state = _ticket_state(ticket, acc)
    if state != "ok":
        return JSONResponse({"ok": False, "detail": tx[state]}, status_code=410)
    if await accounts.access_state(session, acc) != "ok":
        return JSONResponse({"ok": False, "detail": tx["invalid"]}, status_code=403)
    settings = await settings_store.load(session)
    max_bytes = int(settings.get("max_file_mb") or 100) * 1024 * 1024
    too_big = tx["big"].format(mb=max_bytes // 1024 // 1024)
    name = unquote(request.headers.get("x-file-name") or "") or ticket.name or "fayl"
    if not allowed(name, settings.get("allowed_types", "")):
        return JSONResponse({"ok": False, "detail": f"{tx['err']}: {settings.get('allowed_types', '')}"}, status_code=400)
    if int(request.headers.get("content-length") or 0) > max_bytes:
        return JSONResponse({"ok": False, "detail": too_big}, status_code=413)
    dest = spool_path("web")
    size = 0
    try:
        with open(dest, "wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("too_big")
                fh.write(chunk)
    except Exception:  # noqa: BLE001 — uzilgan yoki juda katta yuklash: vaqtinchalik fayl o'chiriladi
        dest.unlink(missing_ok=True)
        return JSONResponse({"ok": False, "detail": too_big if size > max_bytes else tx["err"]},
                            status_code=413 if size > max_bytes else 400)
    declared = int(request.headers.get("content-length") or 0)
    if size == 0 or (declared and size != declared):  # bo'sh yoki yo'lda kesilgan (to'liq kelmagan) fayl saqlanmaydi
        dest.unlink(missing_ok=True)
        return JSONResponse({"ok": False, "detail": tx["err"]}, status_code=400)
    await session.refresh(ticket)
    if ticket.used_at is not None:  # shu havola bilan parallel ikkinchi yuklash
        dest.unlink(missing_ok=True)
        return JSONResponse({"ok": False, "detail": tx["used"]}, status_code=410)
    vis = request.headers.get("x-visibility") or ""
    options: dict = {"web_upload": True}
    if vis in ("public", "private"):
        options["visibility"] = vis
    rec = await enqueue(session, source="telegram", original_name=name, actor=acc.display, employee_id=acc.employee_id,
                        account_id=acc.id, temp_path=dest, size=size, caption=ticket.caption, options=options,
                        tg={"chat_id": ticket.chat_id, "file_id": "", "status_msg_id": None})
    ticket.used_at, ticket.file_id = datetime.now(timezone.utc), rec.id
    add_audit(session, "file.web_upload", actor=str(acc.telegram_id), actor_kind="bot", target=name, details={"size": size})
    await session.commit()
    return {"ok": True, "id": rec.id}
