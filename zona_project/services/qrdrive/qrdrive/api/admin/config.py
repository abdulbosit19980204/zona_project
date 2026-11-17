"""Panel: saqlash joylari, bot sozlamalari, QR dizayni, setup ustasi, API kalitlar va webhooklar."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ... import settings_store
from ...core.config import config
from ...core.crypto import decrypt, encrypt, encrypt_json, new_api_key, token
from ...core.errors import TelegramError
from ...core.security import Principal
from ...db.models import ApiKey, Employee, FileRecord, Storage, WebhookDelivery
from ...db.session import get_session
from ...services import qr
from ...services.audit import add_audit
from ...services.naming import validate_template
from ...services.telegram import TelegramClient
from ...storage import diagnose, gdrive, registry
from ...storage.base import FIELDS, KINDS
from ..deps import SCOPES, admin, superadmin, viewer

router = APIRouter(tags=["admin: config"])


# ---------------- saqlash joylari ----------------
def storage_out(s: Storage, files: int = 0) -> dict[str, Any]:
    return {"id": s.id, "name": s.name, "kind": s.kind, "kind_label": KINDS.get(s.kind, {}).get("label", s.kind),
            "base_folder": s.base_folder, "link_mode": s.link_mode, "is_primary": s.is_primary, "is_fallback": s.is_fallback,
            "enabled": s.enabled, "status": s.status, "last_check_at": s.last_check_at, "last_error": s.last_error,
            "latency_ms": s.latency_ms, "quota_used": s.quota_used, "quota_total": s.quota_total,
            "config": registry.public_config(s), "files": files}


@router.get("/storages/kinds")
async def storage_kinds(_: Principal = Depends(viewer)):
    return [{"kind": k, **v, "fields": FIELDS.get(k, [])} for k, v in KINDS.items()]


@router.get("/storages")
async def list_storages(session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    counts = dict((await session.execute(select(FileRecord.storage_id, func.count()).where(
        FileRecord.deleted_at.is_(None)).group_by(FileRecord.storage_id))).all())
    rows = (await session.execute(select(Storage).order_by(Storage.is_primary.desc(), Storage.id))).scalars()
    return [storage_out(s, counts.get(s.id, 0)) for s in rows]


class StorageIn(BaseModel):
    name: str | None = None
    kind: str | None = None
    base_folder: str | None = None
    link_mode: str | None = None
    is_primary: bool | None = None
    is_fallback: bool | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None


def _apply(s: Storage, body: StorageIn) -> None:
    if body.name is not None:
        s.name = body.name.strip() or s.name
    if body.base_folder is not None:
        s.base_folder = "/" + body.base_folder.strip().strip("/")
    if body.link_mode in ("provider", "system"):
        s.link_mode = body.link_mode
    if not KINDS.get(s.kind, {}).get("links"):
        s.link_mode = "system"
    for f in ("is_fallback", "enabled"):
        if getattr(body, f) is not None:
            setattr(s, f, getattr(body, f))
    if body.config is not None:
        registry.set_config(s, body.config)


async def _make_primary(session: AsyncSession, s: Storage) -> None:
    await session.execute(update(Storage).where(Storage.id != s.id).values(is_primary=False))
    s.is_primary = True


@router.post("/storages")
async def create_storage(body: StorageIn, session: AsyncSession = Depends(get_session), user: Principal = Depends(superadmin)):
    if body.kind not in KINDS:
        raise HTTPException(400, "Saqlash joyi turini tanlang")
    s = Storage(name=(body.name or KINDS[body.kind]["label"]).strip(), kind=body.kind, base_folder="/")
    _apply(s, body)
    session.add(s)
    await session.flush()
    first = (await session.execute(select(func.count()).select_from(Storage))).scalar_one() == 1
    if body.is_primary or first:
        await _make_primary(session, s)
    result = await registry.check(s)
    add_audit(session, "storage.create", actor=user.username, target=s.name, details={"kind": s.kind})
    await session.commit()
    return {**storage_out(s), "check": result}


async def _storage(session: AsyncSession, sid: int) -> Storage:
    s = await session.get(Storage, sid)
    if s is None:
        raise HTTPException(404, "Saqlash joyi topilmadi")
    return s


@router.patch("/storages/{sid}")
async def update_storage(sid: int, body: StorageIn, session: AsyncSession = Depends(get_session), user: Principal = Depends(superadmin)):
    s = await _storage(session, sid)
    _apply(s, body)
    if body.is_primary:
        await _make_primary(session, s)
    result = await registry.check(s) if body.config is not None else None
    changed = body.model_dump(exclude_unset=True)
    if "config" in changed:
        secret = registry.secret_keys(s.kind)
        changed["config"] = {k: ("••••••" if k in secret else v) for k, v in (body.config or {}).items() if v not in ("", None)}
    add_audit(session, "storage.update", actor=user.username, target=s.name, details=changed)
    await session.commit()
    return {**storage_out(s), "check": result}


@router.post("/storages/{sid}/test")
async def test_storage(sid: int, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    s = await _storage(session, sid)
    result = await registry.check(s)
    await session.commit()
    return {**storage_out(s), "check": result}


@router.post("/storages/test")
async def test_unsaved(body: StorageIn, _: Principal = Depends(superadmin)):
    """Saqlashdan oldin «Ulanishni tekshirish»."""
    if body.kind not in KINDS:
        raise HTTPException(400, "Saqlash joyi turini tanlang")
    s = Storage(name="test", kind=body.kind, base_folder="/")
    _apply(s, body)
    return await registry.check(s)


# ---------------- Google Drive: «Google bilan ulash» (OAuth) ----------------
def _state(sid: int) -> str:
    exp = int(time.time()) + 900
    msg = f"{sid}.{exp}"
    sig = hmac.new(config.master_key.encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{msg}.{sig}"


def _check_state(state: str) -> int | None:
    try:
        sid, exp, sig = state.split(".")
    except ValueError:
        return None
    good = hmac.new(config.master_key.encode(), f"{sid}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, good) or int(exp) < time.time():
        return None
    return int(sid)


def _redirect_uri(settings: dict[str, Any]) -> str:
    return f"{settings_store.public_base(settings)}{config.prefix}/api/admin/storages/google/callback"


@router.post("/storages/{sid}/google/start")
async def google_start(sid: int, session: AsyncSession = Depends(get_session), _: Principal = Depends(superadmin)):
    s = await _storage(session, sid)
    cfg = registry.get_config(s)
    if s.kind != "gdrive" or not cfg.get("client_id") or not cfg.get("client_secret"):
        raise HTTPException(400, "Avval OAuth Client ID va Client secret'ni kiriting va saqlang")
    settings = await settings_store.load(session)
    return {"url": gdrive.oauth_url(cfg["client_id"], _redirect_uri(settings), _state(sid)),
            "redirect_uri": _redirect_uri(settings)}


@router.get("/storages/google/callback", include_in_schema=False)
async def google_callback(state: str = "", code: str = "", error: str = "", session: AsyncSession = Depends(get_session)):
    """Google qaytargan manzil (brauzer yo'naltiradi, token yo'q — state imzosi tekshiriladi)."""
    settings = await settings_store.load(session)
    back = f"{settings_store.public_base(settings)}/qr/storages"
    sid = _check_state(state)
    if sid is None or error or not code:
        return RedirectResponse(f"{back}?google=error")
    s = await session.get(Storage, sid)
    if s is None:
        return RedirectResponse(f"{back}?google=error")
    cfg = registry.get_config(s)
    try:
        cfg["refresh_token"] = await gdrive.exchange_code(cfg.get("client_id", ""), cfg.get("client_secret", ""), code,
                                                          _redirect_uri(settings))
    except Exception:  # noqa: BLE001
        return RedirectResponse(f"{back}?google=error")
    s.config_enc = encrypt_json(cfg)
    await registry.check(s)
    add_audit(session, "storage.google_connected", actor="google-oauth", target=s.name)
    await session.commit()
    return RedirectResponse(f"{back}?google=ok")


@router.post("/storages/{sid}/diagnose")
async def diagnose_storage(sid: int, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    """Bosqichma-bosqich tekshiruv: sozlama → ulanish → papka → yozish → havola → kvota (sinov fayli o'chiriladi)."""
    s = await _storage(session, sid)
    result = await diagnose.diagnose(s)
    add_audit(session, "storage.diagnose", actor=user.username, target=s.name, details={"ok": result["ok"]})
    await session.commit()
    return {**result, "storage": storage_out(s)}


@router.post("/storages/diagnose")
async def diagnose_unsaved(body: StorageIn, _: Principal = Depends(superadmin)):
    if body.kind not in KINDS:
        raise HTTPException(400, "Saqlash joyi turini tanlang")
    s = Storage(name="test", kind=body.kind, base_folder="/", link_mode="provider")
    _apply(s, body)
    return await diagnose.diagnose(s)


@router.post("/storages/{sid}/primary")
async def make_primary(sid: int, session: AsyncSession = Depends(get_session), user: Principal = Depends(superadmin)):
    s = await _storage(session, sid)
    await _make_primary(session, s)
    add_audit(session, "storage.primary", actor=user.username, target=s.name)
    await session.commit()
    return {"ok": True}


@router.delete("/storages/{sid}")
async def delete_storage(sid: int, session: AsyncSession = Depends(get_session), user: Principal = Depends(superadmin)):
    s = await _storage(session, sid)
    used = (await session.execute(select(func.count()).select_from(FileRecord).where(FileRecord.storage_id == sid))).scalar_one()
    if used:
        raise HTTPException(400, f"Bu saqlash joyida {used} ta fayl bor. O'chirish o'rniga uni «O'chirilgan» holatga o'tkazing.")
    await session.delete(s)
    add_audit(session, "storage.delete", actor=user.username, target=s.name)
    await session.commit()
    return {"ok": True}


# ---------------- sozlamalar ----------------
@router.get("/settings")
async def get_settings(session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    data = settings_store.public(await settings_store.load(session, fresh=True))
    data["logo"] = qr.logo_path().is_file()
    data["default_texts"] = settings_store.BOT_TEXTS
    return data


@router.patch("/settings")
async def patch_settings(body: dict[str, Any], session: AsyncSession = Depends(get_session), user: Principal = Depends(superadmin)):
    values = {k: v for k, v in body.items() if k in settings_store.EDITABLE}
    for key in ("folder_template", "filename_template"):
        if key in values and not validate_template(str(values[key])):
            raise HTTPException(400, "Shablonda noma'lum o'zgaruvchi bor. Ruxsat etilganlar: {xodim} {bo'lim} {yyyy} {mm} {dd} {sana} {vaqt} {asl_nom}")
    if "max_file_mb" in values:
        values["max_file_mb"] = max(1, min(int(values["max_file_mb"]), 2000))
    if "bot_token" in values and values["bot_token"]:
        try:
            current = await settings_store.load(session)
            async with TelegramClient(values["bot_token"], body.get("bot_api_url", current.get("bot_api_url", ""))) as tg:
                me = await tg.get_me()
            values["bot_username"] = me.get("username", "")
        except TelegramError as e:
            raise HTTPException(400, "Bot tokeni ishlamadi. @BotFather bergan tokenni to'liq nusxalang.") from e
    elif "bot_token" in values:
        values["bot_username"] = ""
    changes = await settings_store.save(session, values)
    add_audit(session, "settings.update", actor=user.username,
              details={k: {"old": o, "new": n} for k, (o, n) in changes.items()})
    await session.commit()
    return settings_store.public(await settings_store.load(session, fresh=True))


class BotTest(BaseModel):
    token: str = ""
    api_url: str | None = None


@router.post("/settings/bot/test")
async def bot_test(body: BotTest, session: AsyncSession = Depends(get_session), _: Principal = Depends(admin)):
    """getMe: bot nomi va rasmi. Token berilmasa — saqlangan token tekshiriladi."""
    settings = await settings_store.load(session)
    tok = body.token or settings.get("bot_token", "")
    api_url = settings.get("bot_api_url", "") if body.api_url is None else body.api_url
    if not tok:
        return {"ok": False, "title": "Bot tokeni kiritilmagan", "hint": "@BotFather'dan token oling va shu yerga kiriting."}
    try:
        async with TelegramClient(tok, api_url) as tg:
            me = await tg.get_me()
            photo = ""
            try:
                photos = await tg.call("getUserProfilePhotos", {"user_id": me["id"], "limit": 1})
                if photos.get("total_count"):
                    fid = photos["photos"][0][0]["file_id"]
                    info = await tg.call("getFile", {"file_id": fid})
                    r = await tg._client.get(f"{tg.base}/file/bot{tok}/{info['file_path']}")
                    photo = "data:image/jpeg;base64," + base64.b64encode(r.content).decode() if r.status_code == 200 else ""
            except Exception:  # noqa: BLE001
                photo = ""
        return {"ok": True, "id": me["id"], "username": me.get("username"), "name": me.get("first_name"), "photo": photo}
    except TelegramError as e:
        hint = ("Token noto'g'ri yoki bekor qilingan. @BotFather'dan yangi token oling." if "Unauthorized" in str(e)
                else "Bot API serveriga ulanib bo'lmadi. Lokal server manzilini tekshiring yoki bo'sh qoldiring.")
        if "logged out" in str(e).lower() or "logOut" in str(e):
            hint = "Bot rasmiy serverdan chiqarilgan. Lokal server manzilini kiriting."
        return {"ok": False, "title": "Botga ulanib bo'lmadi", "hint": hint}


@router.post("/settings/bot/logout")
async def bot_logout(session: AsyncSession = Depends(get_session), user: Principal = Depends(superadmin)):
    """Lokal Bot API serverga o'tishdan oldin: botni rasmiy serverdan chiqarish (bir marta)."""
    settings = await settings_store.load(session)
    try:
        async with TelegramClient(settings.get("bot_token", "")) as tg:
            await tg.log_out()
    except TelegramError as e:
        raise HTTPException(400, "Botni rasmiy serverdan chiqarib bo'lmadi (balki allaqachon chiqarilgan).") from e
    add_audit(session, "settings.bot_logout", actor=user.username)
    await session.commit()
    return {"ok": True}


class QrPreview(BaseModel):
    style: dict[str, Any] = {}
    text: str = "https://example.com/s/namuna"
    filename: str = "namuna-hujjat.pdf"
    company: str = ""


@router.post("/settings/qr/preview")
async def qr_preview(body: QrPreview, _: Principal = Depends(viewer)):
    data = qr.png(body.text, body.style, qr.caption_for(body.style, body.filename, body.company))
    return Response(data, media_type="image/png")


@router.post("/settings/logo")
async def upload_logo(file: UploadFile = File(...), session: AsyncSession = Depends(get_session), user: Principal = Depends(superadmin)):
    try:
        img = Image.open(file.file)
        img.load()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, "Rasmni o'qib bo'lmadi. PNG yoki JPG yuklang.") from e
    img.thumbnail((512, 512))
    qr.logo_path().parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGBA").save(qr.logo_path(), format="PNG")
    add_audit(session, "settings.logo", actor=user.username)
    await session.commit()
    return {"ok": True}


@router.delete("/settings/logo")
async def delete_logo(session: AsyncSession = Depends(get_session), user: Principal = Depends(superadmin)):
    qr.logo_path().unlink(missing_ok=True)
    add_audit(session, "settings.logo_removed", actor=user.username)
    await session.commit()
    return {"ok": True}


class TestSend(BaseModel):
    chat_id: int


@router.post("/settings/test-send")
async def test_send(body: TestSend, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    """Setup ustasi oxirgi qadami: admin Telegramiga sinov QR yuborish."""
    settings = await settings_store.load(session)
    if not settings.get("bot_token"):
        raise HTTPException(400, "Avval bot tokenini kiriting")
    style = settings.get("qr_style") or {}
    image = qr.png("https://t.me/" + (settings.get("bot_username") or "telegram"), style, "QR Drive — sinov")
    try:
        async with TelegramClient.from_settings(settings) as tg:
            await tg.send_photo(body.chat_id, image, "✅ QR Drive ishlayapti! Bu sinov xabari.")
    except TelegramError as e:
        raise HTTPException(400, "Xabar yuborilmadi. Avval botga /start yozing, keyin qayta urinib ko'ring. "
                                 "ID'ingizni bilish uchun botga /id yozing.") from e
    add_audit(session, "setup.test_sent", actor=user.username)
    await session.commit()
    return {"ok": True}


# ---------------- setup ustasi ----------------
@router.get("/setup")
async def setup_status(session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    settings = await settings_store.load(session, fresh=True)
    storages = (await session.execute(select(Storage))).scalars().all()
    employees = (await session.execute(select(func.count()).select_from(Employee))).scalar_one()
    delivered = (await session.execute(select(func.count()).select_from(FileRecord).where(FileRecord.status == "delivered"))).scalar_one()
    return {"done": bool(settings.get("setup_done")),
            "steps": {"admin": True, "bot": bool(settings.get("bot_token") and settings.get("bot_username")),
                      "storage": any(s.status == "ok" for s in storages), "employees": employees > 0, "test": delivered > 0},
            "bot_username": settings.get("bot_username", ""), "storages": len(storages), "employees": employees}


@router.post("/setup/complete")
async def setup_complete(session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    await settings_store.save(session, {"setup_done": True})
    add_audit(session, "setup.complete", actor=user.username)
    await session.commit()
    return {"ok": True}


# ---------------- API kalitlar ----------------
def key_out(k: ApiKey) -> dict[str, Any]:
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "scopes": k.scopes, "rate_limit": k.rate_limit,
            "allowed_ips": k.allowed_ips, "storage_id": k.storage_id, "expires_at": k.expires_at, "webhook_url": k.webhook_url,
            "webhook_secret_set": bool(k.webhook_secret_enc), "created_by": k.created_by, "created_at": k.created_at,
            "last_used_at": k.last_used_at, "uses": k.uses, "revoked": k.revoked}


@router.get("/api-keys/scopes")
async def scopes(_: Principal = Depends(viewer)):
    return SCOPES


@router.get("/api-keys")
async def list_keys(session: AsyncSession = Depends(get_session), _: Principal = Depends(admin)):
    return [key_out(k) for k in (await session.execute(select(ApiKey).order_by(ApiKey.id.desc()))).scalars()]


class KeyIn(BaseModel):
    name: str | None = None
    scopes: list[str] | None = None
    rate_limit: int | None = None
    allowed_ips: list[str] | None = None
    storage_id: int | None = None
    expires_days: int | None = None
    webhook_url: str | None = None


def _apply_key(k: ApiKey, body: KeyIn) -> None:
    if body.name is not None:
        k.name = body.name.strip() or k.name
    if body.scopes is not None:
        k.scopes = [s for s in body.scopes if s in SCOPES]
    if body.rate_limit is not None:
        k.rate_limit = max(0, body.rate_limit)
    if body.allowed_ips is not None:
        k.allowed_ips = [ip.strip() for ip in body.allowed_ips if ip.strip()]
    if body.storage_id is not None:
        k.storage_id = body.storage_id or None
    if body.expires_days is not None:
        k.expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_days) if body.expires_days > 0 else None
    if body.webhook_url is not None:
        k.webhook_url = body.webhook_url.strip()
        if k.webhook_url and not k.webhook_secret_enc:
            k.webhook_secret_enc = encrypt("whsec_" + token(24))


@router.post("/api-keys")
async def create_key(body: KeyIn, session: AsyncSession = Depends(get_session), user: Principal = Depends(superadmin)):
    raw, prefix, hashed = new_api_key()
    k = ApiKey(name=(body.name or "API kalit").strip(), prefix=prefix, key_hash=hashed, scopes=["files:write", "files:read", "qr:generate"],
               created_by=user.username)
    _apply_key(k, body)
    session.add(k)
    add_audit(session, "apikey.create", actor=user.username, target=k.name, details={"scopes": k.scopes})
    await session.commit()
    return {**key_out(k), "key": raw, "webhook_secret": decrypt(k.webhook_secret_enc)}


@router.patch("/api-keys/{kid}")
async def update_key(kid: int, body: KeyIn, session: AsyncSession = Depends(get_session), user: Principal = Depends(superadmin)):
    k = await session.get(ApiKey, kid)
    if k is None:
        raise HTTPException(404, "Kalit topilmadi")
    had_secret = bool(k.webhook_secret_enc)
    _apply_key(k, body)
    add_audit(session, "apikey.update", actor=user.username, target=k.name, details=body.model_dump(exclude_unset=True))
    await session.commit()
    out = key_out(k)
    if not had_secret and k.webhook_secret_enc:
        out["webhook_secret"] = decrypt(k.webhook_secret_enc)
    return out


@router.post("/api-keys/{kid}/webhook-secret")
async def rotate_secret(kid: int, session: AsyncSession = Depends(get_session), user: Principal = Depends(superadmin)):
    k = await session.get(ApiKey, kid)
    if k is None:
        raise HTTPException(404, "Kalit topilmadi")
    secret = "whsec_" + token(24)
    k.webhook_secret_enc = encrypt(secret)
    add_audit(session, "apikey.webhook_secret", actor=user.username, target=k.name)
    await session.commit()
    return {"webhook_secret": secret}


@router.delete("/api-keys/{kid}")
async def revoke_key(kid: int, session: AsyncSession = Depends(get_session), user: Principal = Depends(superadmin)):
    k = await session.get(ApiKey, kid)
    if k is None:
        raise HTTPException(404, "Kalit topilmadi")
    k.revoked = True
    add_audit(session, "apikey.revoke", actor=user.username, target=k.name)
    await session.commit()
    return {"ok": True}


@router.get("/api-keys/{kid}/deliveries")
async def deliveries(kid: int, session: AsyncSession = Depends(get_session), _: Principal = Depends(admin)):
    rows = (await session.execute(select(WebhookDelivery).where(WebhookDelivery.api_key_id == kid)
                                  .order_by(WebhookDelivery.id.desc()).limit(100))).scalars()
    return [{"id": d.id, "event": d.event, "file_id": d.file_id, "status": d.status, "status_code": d.status_code,
             "attempts": d.attempts, "error": d.error, "created_at": d.created_at} for d in rows]


@router.post("/api-keys/{kid}/test-webhook")
async def test_webhook(kid: int, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    k = await session.get(ApiKey, kid)
    if k is None or not k.webhook_url:
        raise HTTPException(400, "Bu kalitda webhook manzili yo'q")
    session.add(WebhookDelivery(api_key_id=k.id, event="test", payload={"event": "test", "message": "QR Drive webhook sinovi"},
                                next_attempt_at=datetime.now(timezone.utc)))
    await session.commit()
    return {"ok": True}
