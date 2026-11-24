"""Admin chatiga savol — to'liq va tushunarli: manba (guruh, vaqt, qancha vaqtdan beri), kim so'radi (haqiqiy ismi,
roli, loyihasi), savol matni, rasm va fayllari (albom bo'lib, xabar oldidan), javob va havolalar (guruhda / panelda).
OCR matni yuborilmaydi — rasmning o'zi boradi."""
import html
import logging

from django.utils import timezone

from .models import Media, Message

log = logging.getLogger("support")
esc = html.escape


def _who(q):
    u = q.user
    if u is None:
        return "?"
    sp = u.staff_person if u.staff_person_id else None
    name = (sp.name if sp else "") or u.real_name or u.name or (u.username and "@" + u.username) or "?"
    bits = [sp.get_role_display(), sp.project.name if sp.project_id else "", sp.territory] if sp else [u.position, u.department]
    tag = f" (@{esc(u.username)})" if u.username else ""
    extra = " · ".join(b for b in bits if b)
    return f"{esc(name)}{tag}" + (f" — {esc(extra)}" if extra else "")


def _when(q):
    from .resolution import TZ, elapsed
    lt = timezone.localtime(q.created_at, TZ)
    return f"{lt:%d.%m %H:%M} · {elapsed(q)} oldin"


def media_of(q, limit=10):
    """Savolning barcha fayllari: o'zi, albomdagi qismlari va savol egasining keyingi qo'shimchalari."""
    ids = {q.pk, *Message.objects.filter(question=q, kind=Message.INFO).values_list("pk", flat=True)}
    if q.media_group_id:
        ids |= set(Message.objects.filter(bot_id=q.bot_id, chat_id=q.chat_id, media_group_id=q.media_group_id)
                   .values_list("pk", flat=True))
    return list(Media.objects.filter(message_id__in=ids).order_by("message_id", "id")[:limit])


def card(q, title, extra=(), answer="", answer_label="💬 Javob"):
    group = q.group.title if q.group_id else ""
    files = media_of(q)
    text = (q.text or "").strip()
    lines = [f"<b>{title}</b>", f"👥 {esc(group)} · 🕒 {_when(q)}", f"👤 {_who(q)}"]
    from .agent import short
    ag = short(q.user)
    if ag:  # agent kodi, loyiha, hudud, supervayzer, telefon
        lines.append(f"🏷 {esc(ag)}")
    if text:
        lines.append(f"❓ <blockquote expandable>{esc(text[:1500])}</blockquote>")
    elif files:
        lines.append("❓ <i>Rasmli savol (matnsiz)</i>")
    if files:
        n_ph = sum(1 for m in files if m.kind == Media.PHOTO)
        lines.append(f"🖼 {len(files)} ta fayl{f' ({n_ph} ta rasm)' if n_ph else ''} — yuqorida")
    lines += [x for x in extra if x]
    if answer:
        lines.append(f"{answer_label}: <blockquote expandable>{esc(answer[:1800])}</blockquote>")
    return "\n".join(lines)


def links(q):
    from .runner import panel_url
    row = []
    link = q.group.message_link(q.message_id) if q.group_id else ""
    if link:
        row.append({"text": "↗ Guruhda ochish", "url": link})
    url = panel_url(f"/support?q={q.id}")
    if url:
        row.append({"text": "🖥 Panelda", "url": url})
    return [row] if row else []


def send(tg, chat_id, q, body, buttons=None):
    """Avval savol fayllari (albom), keyin matn — tugmalar bilan. Fayl yuborilmasa ham matn boradi."""
    if not chat_id or tg is None:
        return None
    files = media_of(q)
    if files and hasattr(tg, "send_media"):
        items = []
        for m in files:
            fid = (m.tg_file_ids or {}).get(str(q.bot_id))
            kind = m.kind if m.kind in ("photo", "video", "document", "animation") else "document"
            if fid:
                items.append({"kind": kind, "name": m.name, "file_id": fid})
            elif m.path:
                try:
                    items.append({"kind": kind, "name": m.name or "file", "data": open(m.path, "rb").read()})
                except OSError:
                    continue
        if items:
            try:
                tg.send_media(chat_id, items)
            except Exception as e:  # noqa: BLE001 — fayl ketmasa ham xabar ketadi
                log.info("admin media failed q=%s: %s", q.pk, e)
    rows = (buttons or []) + links(q)
    try:
        return tg.send(chat_id, body[:4096], buttons=rows or None)
    except Exception as e:  # noqa: BLE001
        log.info("admin card failed q=%s: %s", q.pk, e)
        return None
