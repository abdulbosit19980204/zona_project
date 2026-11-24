"""PRBC vazifalari to'g'ridan-to'g'ri API orqali (Telegram botdagi /vazifa buyrug'isiz).

- create(): paneldan yoki boshqa moduldan vazifa yaratish — mas'ul (ijrochi) PRBC user id bo'yicha, kuzatuvchi —
  sozlamadagi (standart: Kamoliddin aka);
- process_support_queue(): support boti «api» rejimida navbatga qo'ygan vazifalarni yaratadi;
- poll(): kuzatiladigan ochiq vazifalar holati (PRBC'da webhook yo'q — davriy so'rov). Bajarilganda hisobot
  (kim yopdi, izohlar, chek-list, sarflangan vaqt) to'ldiriladi va bog'langan savol "hal bo'ldi" bo'ladi.

Hammasi prbc_worker jarayonida ishlaydi — bot faqat navbatga yozadi, PRBC'ni kutmaydi.
"""
import logging
from datetime import datetime, time as dtime, timedelta

from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .client import Client, PrbcError
from .models import Change, Connection, Person, Task

log = logging.getLogger("prbc")
OPEN = ("new", "in_progress", "")
ROLES = {"assignee": "Ijrochi", "co_assignee": "Hamijrochi", "observer": "Kuzatuvchi"}


def _dt(v):
    return parse_datetime(v) if isinstance(v, str) else v


def _people(data):
    out = []
    for a in data.get("assignees") or []:
        u = a.get("user") or {}
        if u.get("id"):
            out.append({"id": u["id"], "name": (u.get("full_name") or "")[:200], "position": (u.get("position") or "")[:200],
                        "role": a.get("role") or "assignee"})
    return out


def _mirror(data, kind=Task.OURS, **extra):
    st = data.get("status") or {}
    people = _people(data)
    pa = data.get("primary_assignee") or next((p for p in people if p["role"] == "assignee"), None) or {}
    assignee = pa.get("full_name") or pa.get("name") or ""
    others = [p["name"] for p in people if p["role"] == "assignee" and p["name"] != assignee]
    project = data.get("project")
    defaults = {
        "code": data.get("code", ""), "title": (data.get("title") or "")[:300], "kind": kind,
        "status_name": (st.get("name") or "")[:60], "status_category": (st.get("category") or "")[:20],
        "project_id": project.get("id") if isinstance(project, dict) else project,
        "project_name": (project.get("name") or "")[:200] if isinstance(project, dict) else "",
        "assignee": (assignee + (f" +{len(others)}" if others else ""))[:200], "due_at": _dt(data.get("due_at")),
        "prbc_created_at": _dt(data.get("created_at")), "prbc_updated_at": _dt(data.get("updated_at")),
        "checked_at": timezone.now(), **extra}
    if "assignees" in data:  # to'liq javob (ro'yxat javobida ijrochilar yo'q — bor ma'lumot o'chirilmaydi)
        defaults["people"] = people
        defaults["watchers"] = ", ".join(p["name"] for p in people if p["role"] == "observer")[:300]
    if "completed_at" in data:
        defaults["completed_at"] = _dt(data.get("completed_at"))
    if data.get("spent_minutes") is not None:
        defaults["spent_minutes"] = int(data["spent_minutes"] or 0)
    t, _ = Task.objects.update_or_create(prbc_id=data["id"], defaults=defaults)
    return t


def default_due(hours=24):
    """Ish kuni oxiri (18:00) — kamida `hours` soatdan keyin."""
    at = timezone.localtime() + timedelta(hours=hours)
    return timezone.make_aware(datetime.combine(at.date(), dtime(18, 0))).isoformat()


def _full(client, data):
    try:
        return {**data, **client.get(f"/tasks/{data['id']}/")}
    except PrbcError:
        return data


def self_id(conn, client=None):
    """Ulangan akkaunt egasining vazifalardagi user id'si: xodimlar ro'yxatida ism bo'yicha (vazifa id'si aniq shu),
    bo'lmasa profil id'si. Profil hali o'qilmagan bo'lsa — bir marta o'qib saqlanadi."""
    me = conn.me or {}
    if not me and client is not None:
        try:
            p = client.profile() or {}
            emp = p.get("employee") if isinstance(p.get("employee"), dict) else {}
            me = {"id": p.get("id"), "full_name": p.get("full_name") or emp.get("full_name") or "",
                  "position": p.get("position") or emp.get("position", "")}
            Connection.objects.filter(pk=conn.pk).update(me=me)
            conn.me = me
        except PrbcError as e:
            log.info("profile: %s", e)
    if me.get("full_name"):
        from .people import name_key
        hit = list(Person.objects.filter(prbc_user__isnull=False, name_key=name_key(me["full_name"]))
                   .values_list("prbc_user", flat=True).distinct()[:2])
        if len(hit) == 1:
            return int(hit[0])
    return int(me["id"]) if str(me.get("id") or "").isdigit() else None


def create(*, title, description="", assignee_ids=(), watcher_ids=None, project=None, priority=None, due_at=None,
           actor="", support_task=None, conn=None, client=None):
    """Mas'ul — ijrochi (assignee_ids, bo'lmasa standart ijrochilar); kuzatuvchi — sozlamadagi (Kamoliddin aka) va
    ulangan akkaunt egasi (watch_self)."""
    conn = conn or Connection.get()
    client = client or Client(conn)
    assignees = [int(x) for x in (list(assignee_ids) or list(conn.task_default_assignees or []))]
    pool = list((conn.task_watchers or []) if watcher_ids is None else watcher_ids)
    if conn.watch_self:
        me = self_id(conn, client)
        if me:
            pool.append(me)
    watchers = list(dict.fromkeys(int(x) for x in pool if int(x) not in assignees))
    data = client.create_task(title=title, description=description, project=project or conn.task_project,
                              assignee_ids=assignees, watcher_ids=watchers, priority=priority, due_at=due_at)
    if not isinstance(data, dict) or not data.get("id"):
        raise PrbcError("PRBC vazifa yaratmadi (javobda id yo'q)", payload=data)
    data = _full(client, data)  # kod, ijrochilar, kuzatuvchilar
    if "assignees" in data:  # watcher_ids qabul qilinmagan bo'lsa — kuzatuvchini alohida qo'shamiz
        have = {p["id"] for p in _people(data) if p["role"] == "observer"}
        missing = [uid for uid in watchers if uid not in have]
        for uid in missing:
            try:
                client.post(f"/tasks/{data['id']}/watchers/", {"user_id": uid})
            except PrbcError as e:
                log.info("watcher %s not added to %s: %s", uid, data["id"], e)
        if missing:
            data = _full(client, data)
    t = _mirror(data, created_by=actor[:150], support_task=support_task)
    Change.objects.create(kind=Change.TASK, text=f"Vazifa yaratildi: {t.code} — {t.title}"[:500], actor=actor[:150],
                          data={"task": t.prbc_id})
    return t


def task_url(conn, t):
    return f"{(conn.base_url or 'https://prbc.uz').rstrip('/')}/tasks/{t.prbc_id}"


# ----------------------------------------------------------------------------- support boti (api rejimi)
def assignee_ids_for(username, conn=None):
    """Telegram @username -> PRBC user id: sozlamadagi qo'lda moslash, bog'langan mas'ul/kontakt/bot foydalanuvchisi,
    bo'lmasa — zona'dagi xodim ismi PRBC'da yagona bo'lsa."""
    u = (username or "").lstrip("@").lower()
    if not u:
        return []
    amap = {str(k).lstrip("@").lower(): v for k, v in ((conn or Connection.get()).assignee_map or {}).items()}
    if str(amap.get(u, "")).isdigit():
        return [int(amap[u])]
    active = Person.objects.filter(prbc_user__isnull=False).exclude(status=Person.LEFT)
    for p in active.select_related("member", "staff_person", "tg_user"):
        names = {(p.member.telegram if p.member_id else ""), (p.staff_person.telegram if p.staff_person_id else ""),
                 (p.tg_user.username if p.tg_user_id else "")}
        if u in {n.lstrip("@").lower() for n in names if n}:
            return [p.prbc_user]
    from zona.models import Member
    m = Member.objects.filter(telegram__iexact=u).first() or Member.objects.filter(telegram__iexact=f"@{u}").first()
    if m and m.name and not m.is_team:
        qs = active
        for part in m.name.split()[:3]:
            qs = qs.filter(full_name__icontains=part)
        ids = list(qs.values_list("prbc_user", flat=True).distinct()[:2])
        if len(ids) == 1:
            return ids
    return []


# savol fayllari va qo'shimcha xabarlari --------------------------------------------------------------------
MAX_FILE = 20 * 1024 * 1024
INFO_MARK = "📎 Savol egasidan qo'shimcha"
EXT = {"photo": ".jpg", "video": ".mp4", "video_note": ".mp4", "animation": ".mp4"}


def _bot_client(q):
    """Savol kelgan Telegram bot (fayl yuklab olish va guruhga yozish uchun) — worker o'zi chaqiradi, bot kutmaydi."""
    from support.telegram import Client as Tg
    from zona.crypto import decrypt
    token = decrypt(q.bot.token_enc) if q.bot_id and q.bot.token_enc else ""
    return Tg(token) if token else None


def _info(q):
    """Savol egasining keyingi qo'shimchalari (aniqlashtirish javobi, "mana skrin")."""
    from support.models import Message
    return list(Message.objects.filter(question=q, kind=Message.INFO).order_by("id"))


def _file_bytes(m, q, cache):
    import os

    from support.runner import media_dir
    if m.path:
        p = os.path.join(media_dir(), m.path)
        if os.path.isfile(p) and os.path.getsize(p) <= MAX_FILE:
            with open(p, "rb") as f:
                return f.read()
    fid = (m.tg_file_ids or {}).get(str(q.bot_id)) if q.bot_id else None
    if fid:
        if "tg" not in cache:
            cache["tg"] = _bot_client(q)
        if cache["tg"] is not None:
            try:
                return cache["tg"].download(fid, max_bytes=MAX_FILE)
            except Exception as e:  # noqa: BLE001 — fayl o'chirilgan yoki juda katta
                log.info("media %s download: %s", m.pk, e)
    return None


def _file_name(m):
    import os
    if m.name and not m.name.startswith("album:"):
        return m.name[:150]
    ext = EXT.get(m.kind) or os.path.splitext(m.path or "")[1]
    return f"savol_{m.message_id or 0}_{m.pk}{ext}"


def sync_question(conn, client, t, st=None):
    """Savoldagi rasm/fayllar va savol egasining keyingi qo'shimchalari PRBC vazifasiga (faqat hali o'tkazilmaganlari).
    Qaytaradi: (yuklangan fayllar, qo'shilgan izohlar)."""
    from support.adminmsg import media_of
    st = st or t.support_task
    q = st.message if st and st.message_id else None
    if q is None:
        return 0, 0
    from support.models import Media, Message
    sync = dict(t.sync or {})
    sent_media, sent_info = set(sync.get("media") or []), set(sync.get("info") or [])
    sent_dups = set(sync.get("dups") or [])
    files = comments = 0
    dups = list(Message.objects.filter(pk__in=[i for i in (st.duplicates or []) if i not in sent_dups])
                .select_related("user", "group").order_by("id"))
    for dq in dups:  # shu mavzudagi takroriy savol — vazifaga izoh (kim, qaysi guruh, matn)
        sent_dups.add(dq.pk)
        who = (dq.user.name if dq.user_id else "") + (f" · {dq.group.title}" if dq.group_id else "")
        text = (dq.text or dq.ocr_text or "").strip()
        try:
            client.comment(t.prbc_id, f"🔁 Shu mavzuda yana savol ({who}, {timezone.localtime(dq.created_at):%d.%m %H:%M}):"
                                      f"\n{text[:2000] or '(rasm)'}")
            comments += 1
        except PrbcError as e:
            log.info("dup comment %s: %s", t.prbc_id, e)
    if conn.attach_files:
        cache = {}
        extra = [i for i in (st.media_ids or []) if i not in sent_media]
        items = {m.pk: m for m in media_of(q, limit=20)}
        for dq in dups:
            items.update({m.pk: m for m in media_of(dq, limit=5)})
        items.update({m.pk: m for m in Media.objects.filter(pk__in=extra)})
        for m in sorted(items.values(), key=lambda x: x.pk):
            if m.pk in sent_media:
                continue
            data = _file_bytes(m, q, cache)
            sent_media.add(m.pk)  # yuklab bo'lmasa ham qayta urinilmaydi (har 2 daqiqada bir xil xato bo'lmasin)
            if not data:
                continue
            try:
                client.attach(t.prbc_id, _file_name(m), data, m.mime or "")
                files += 1
            except PrbcError as e:
                log.info("attach %s -> %s: %s", m.pk, t.prbc_id, e)
                if e.status in (401, 403, 404, 405):
                    sent_media.discard(m.pk)
                    break
    for info in _info(q):
        if info.pk in sent_info:
            continue
        sent_info.add(info.pk)
        text = (info.text or info.ocr_text or "").strip()
        if text and sync.get("created_info_done"):
            try:
                client.comment(t.prbc_id, f"{INFO_MARK} ({timezone.localtime(info.created_at):%d.%m %H:%M}):\n{text[:3000]}")
                comments += 1
            except PrbcError as e:
                log.info("info comment %s: %s", t.prbc_id, e)
    sync.update(media=sorted(sent_media), info=sorted(sent_info), dups=sorted(sent_dups), created_info_done=True,
                files=int(sync.get("files") or 0) + files, comments=int(sync.get("comments") or 0) + comments)
    Task.objects.filter(pk=t.pk).update(sync=sync)
    t.sync = sync
    return files, comments


def _esc(x):
    import html
    return html.escape(x or "", quote=False)


def notify_group(st, html_text):
    """Guruhdagi savolga javob (reply). Savol o'chirilgan bo'lsa ham yuboriladi (allow_sending_without_reply)."""
    q = st.message if st and st.message_id else None
    if q is None or not q.chat_id or not q.group_id:
        return False
    tg = _bot_client(q)
    if tg is None:
        return False
    try:
        tg.send(q.chat_id, html_text, reply_to=q.message_id)
        return True
    except Exception as e:  # noqa: BLE001
        log.info("group notify %s: %s", st.pk, e)
        return False


def created_text(t, lang):
    who = t.assignee or "—"
    if lang == "ru":
        return f"📌 Создана задача <b>{_esc(t.code)}</b> · ответственный: {_esc(who)}. Сообщим, когда будет выполнено."
    return f"📌 Vazifa ochildi: <b>{_esc(t.code)}</b> · mas'ul: {_esc(who)}. Bajarilganda shu yerda xabar beramiz."


def _human_minutes(minutes, lang):
    h, m = divmod(int(minutes), 60)
    if lang == "ru":
        return (f"{h} ч " if h else "") + f"{m} мин"
    return (f"{h} soat " if h else "") + f"{m} daq."


def done_text(t, lang):
    """Bajarildi: kim yopdi, qancha vaqtda, ijrochi izohlari (bizning avtomatik izohlarimizsiz)."""
    r = t.report or {}
    ru = lang == "ru"
    who = r.get("completed_by") or t.assignee or "—"
    lines = [("✅ <b>Выполнено</b> — " if ru else "✅ <b>Bajarildi</b> — ") + _esc(t.code),
             ("👤 Исполнитель: " if ru else "👤 Bajardi: ") + _esc(who)]
    took = None
    if t.completed_at and t.prbc_created_at:
        took = (t.completed_at - t.prbc_created_at).total_seconds() / 60
    if took is not None and took >= 1:
        lines.append(("⏱ За " if ru else "⏱ ") + _human_minutes(took, lang) + ("" if ru else " ichida"))
    notes = [c for c in r.get("comments") or [] if c.get("text")
             and not c["text"].startswith((INFO_MARK, "🔁 Shu mavzuda", "Inventarizatsiya bo'yicha"))][-3:]
    if notes:
        lines.append("💬 " + ("Комментарий:" if ru else "Izoh:"))
        lines += [f"<blockquote>{_esc((c.get('by') + ': ') if c.get('by') else '')}{_esc(c['text'][:600])}</blockquote>"
                  for c in notes]
    for c in r.get("checklist") or []:
        if c.get("total"):
            lines.append(f"☑ {_esc(c['title'] or ('Чек-лист' if ru else 'Chek-list'))}: {c['done']}/{c['total']}")
    lines.append("Если вопрос не решён — напишите здесь." if ru else "Hal bo'lmagan bo'lsa — shu yerda yozing.")
    return "\n".join(lines)[:4000]


def process_support_queue(conn=None, client=None, limit=10):
    """Support boti «api» rejimida yozgan vazifalar (status=queued) -> PRBC vazifasi: tavsif (savol, agent ma'lumoti,
    havola, qo'shimchalar), mas'ul, kuzatuvchi, savoldagi rasm/fayllar biriktiriladi."""
    from support.models import Settings, SupportTask
    from support.tasks import problem_text
    s = Settings.load()
    if s.task_mode != "api":
        return 0
    conn = conn or Connection.get()
    client = client or Client(conn)
    done = 0
    for st in SupportTask.objects.filter(status=SupportTask.QUEUED, attempts__lt=3).select_related(
            "message", "message__user", "message__group", "message__bot", "entry").order_by("created_at")[:limit]:
        st.attempts += 1
        ids = assignee_ids_for(st.assignee, conn)
        body = "\n".join(line for line in (st.text or "").splitlines() if not line.startswith("/vazifa")).strip()
        q = st.message if st.message_id else None
        title = st.title or "Savol"
        if q is not None:
            title = problem_text(q, title, st.entry)
            extra = [(i.text or "").strip() for i in _info(q) if (i.text or "").strip()]
            if extra:
                body += "\n\nQo'shimcha (savol egasidan):\n" + "\n".join(f"• {x[:500]}" for x in extra[:10])
        try:
            t = create(title=title, description=body, assignee_ids=ids, actor="support-bot",
                       support_task=st, conn=conn, client=client)
        except PrbcError as e:
            st.status = SupportTask.QUEUED if st.attempts < 3 else SupportTask.FAILED
            st.error = str(e)[:250]
            st.save(update_fields=["attempts", "status", "error"])
            continue
        files = 0
        try:
            files, _ = sync_question(conn, client, t, st)
        except Exception:  # noqa: BLE001 — fayl xatosi vazifani bekor qilmaydi
            log.exception("files for %s", t.prbc_id)
        st.status, st.sent_at, st.error = SupportTask.SENT, timezone.now(), ""
        st.reply = (f"{t.code} yaratildi: {task_url(conn, t)}\nMas'ul: {t.assignee or '—'}"
                    + (f" · Kuzatuvchi: {t.watchers}" if t.watchers else "")
                    + (f" · {files} ta fayl biriktirildi" if files else "")
                    + ("" if ids else " (ijrochi PRBC'da topilmadi — standart ijrochi qo'yildi)"))
        st.save(update_fields=["attempts", "status", "sent_at", "error", "reply"])
        if conn.notify_created and q is not None and notify_group(st, created_text(t, q.lang)):
            Task.objects.filter(pk=t.pk).update(sync={**t.sync, "notified": ["created"]})
        done += 1
    return done


# ----------------------------------------------------------------------------- holatni kuzatish va hisobot
def _activity(client, task_id, pages=3):
    try:
        return list(client.pages(f"/tasks/{task_id}/activity/", max_pages=pages))
    except PrbcError as e:
        log.info("activity %s: %s", task_id, e)
        return []


def _task_of(c):
    v = c.get("task")
    return v.get("id") if isinstance(v, dict) else v


def _comments(client, task_id, limit=30):
    """To'liq izohlar. Filtr qo'llab-quvvatlanmasa — boshqa vazifalarniki tashlab yuboriladi."""
    out = []
    try:
        for it in client.pages("/task-comments/", {"task": task_id, "ordering": "created_at"}, max_pages=2):
            if _task_of(it) != task_id:
                continue
            a = it.get("author") or it.get("user") or {}
            out.append({"at": it.get("created_at"), "by": a.get("full_name", "") if isinstance(a, dict) else str(a),
                        "text": (it.get("body") or it.get("text") or "")[:2000]})
            if len(out) >= limit:
                break
    except PrbcError as e:
        log.info("comments %s: %s", task_id, e)
    return out


def _worklog(client, task_id):
    try:
        w = client.get(f"/tasks/{task_id}/worklog/")
    except PrbcError:
        return {}
    if not isinstance(w, dict):
        return {}
    entries = []
    for e in (w.get("entries") or [])[:30]:
        u = e.get("user") or {}
        entries.append({"by": u.get("full_name", "") if isinstance(u, dict) else "",
                        "minutes": e.get("minutes") or e.get("duration_minutes"),
                        "note": (e.get("note") or e.get("comment") or "")[:300],
                        "at": e.get("started_at") or e.get("date") or e.get("created_at")})
    return {"totals": w.get("team") or w.get("mine") or {}, "entries": entries}


def build_report(client, data):
    """Bajarilgan vazifa hisoboti: kim va qachon yopdi, izohlar, chek-list, sarflangan vaqt, ijrochilar, tarix."""
    tid = data["id"]
    acts = _activity(client, tid)
    closed = next((a for a in acts if a.get("verb") == "status_changed"
                   and (a.get("metadata") or {}).get("to_category") == "done"), None)
    comments = _comments(client, tid)
    if not comments:  # izohlar ro'yxati yopiq bo'lsa — tarixdagi qisqa matnlar
        comments = [{"at": a.get("created_at"), "by": (a.get("actor") or {}).get("full_name", ""),
                     "text": (a.get("metadata") or {}).get("excerpt", "")} for a in reversed(acts)
                    if a.get("verb") == "comment_added"]
    checklist = []
    for c in data.get("checklists") or []:
        items = c.get("items") or []
        checklist.append({"title": c.get("title", ""), "done": sum(1 for i in items if i.get("is_done")), "total": len(items),
                          "items": [{"text": i.get("text", ""), "done": bool(i.get("is_done"))} for i in items]})
    due, completed = _dt(data.get("due_at")), _dt(data.get("completed_at"))
    return {
        "completed_at": data.get("completed_at"),
        "completed_by": ((closed or {}).get("actor") or {}).get("full_name", ""),
        "status": (data.get("status") or {}).get("name", ""),
        "spent_minutes": data.get("spent_minutes"), "estimated_minutes": data.get("estimated_minutes"),
        "progress": data.get("progress_percent"),
        "on_time": (completed <= due) if (due and completed) else None,
        "people": _people(data), "comments": comments, "checklist": checklist, "worklog": _worklog(client, tid),
        "history": [{"at": a.get("created_at"), "verb": a.get("verb"), "by": (a.get("actor") or {}).get("full_name", ""),
                     "meta": a.get("metadata") or {}} for a in acts[:40]],
    }


def report_text(t):
    """Qisqa matn (paneldagi vazifa javobida ko'rinadi)."""
    r = t.report or {}
    bits = [f"{t.code}: {t.status_name or 'Bajarildi'}"]
    if r.get("completed_by"):
        bits.append(f"yopdi: {r['completed_by']}")
    if t.completed_at:
        bits.append(f"{timezone.localtime(t.completed_at):%d.%m %H:%M}")
    if r.get("spent_minutes"):
        bits.append(f"{r['spent_minutes']} daq.")
    if r.get("on_time") is False:
        bits.append("muddatidan kech")
    lines = [" · ".join(bits)]
    for c in (r.get("comments") or [])[-3:]:
        if c.get("text"):
            lines.append(f"— {c.get('by') or '?'}: {c['text'][:300]}")
    for c in r.get("checklist") or []:
        if c.get("total"):
            lines.append(f"☑ {c['title']}: {c['done']}/{c['total']}")
    return "\n".join(lines)[:2000]


def _close_support(conn, t):
    """PRBC'da bajarildi -> bizdagi vazifa "bajarildi" + hisobot; bog'langan savol(lar) "hal bo'ldi"."""
    from support.models import Message, SupportTask
    from support.resolution import YES, is_final, mark
    st = SupportTask.objects.filter(pk=t.support_task_id).first()
    if st is None:
        return
    st.status, st.reply = SupportTask.DONE, f"{report_text(t)}\n{task_url(conn, t)}"[:4000]
    st.save(update_fields=["status", "reply"])
    q0 = st.message if st.message_id else None
    sync = dict(t.sync or {})
    if conn.notify_done and q0 is not None and "done" not in (sync.get("notified") or []):
        if notify_group(st, done_text(t, q0.lang)):  # guruhdagi savolga: bajarildi + izohlar
            sync["notified"] = [*(sync.get("notified") or []), "done"]
            Task.objects.filter(pk=t.pk).update(sync=sync)
            st.reply = f"{st.reply}\nGuruhga xabar berildi."[:4000]
            st.save(update_fields=["reply"])
    if not conn.close_on_done:
        return
    by = f"prbc: {t.code} bajarildi" + (f" ({t.completed_by})" if t.completed_by else "")
    ids = [i for i in [st.message_id, *(st.duplicates or [])] if i]
    tg = None
    for q in Message.objects.filter(pk__in=ids).select_related("bot"):
        if q.resolution != YES and not is_final(q):
            mark(q, YES, by)
            if q.confirm_msg_id or q.staff_msg_id:  # "hal bo'ldimi?" tugmalari yopiladi
                from support.resolution import DONE_TEXT, close_prompts
                tg = tg or _bot_client(q)
                close_prompts(tg, q, DONE_TEXT["ru" if q.lang == "ru" else "uz"])


def poll(conn=None, client=None, limit=30):
    """Kuzatiladigan ochiq vazifalar (biz yaratganlar + 1C'dan "Yangi xodim / Ishdan bo'shash"): holat, ijrochilar,
    kuzatuvchi. Bajarilganda — hisobot to'ldiriladi, bog'langan savol yopiladi. Eng uzoq tekshirilmaganlar birinchi."""
    conn = conn or Connection.get()
    client = client or Client(conn)
    n = 0
    qs = (Task.objects.filter(kind__in=[Task.OURS, Task.HIRE, Task.LEAVE], status_category__in=OPEN)
          | Task.objects.filter(kind=Task.OURS, status_category="done", report={}))
    for t in qs.order_by(F("checked_at").asc(nulls_first=True), "id")[:limit]:
        try:
            data = client.get(f"/tasks/{t.prbc_id}/")
        except PrbcError as e:
            upd = {"checked_at": timezone.now()}
            if e.status == 404:
                upd.update(status_category="cancelled", status_name="O'chirilgan")
            Task.objects.filter(pk=t.pk).update(**upd)
            continue
        before = t.status_category
        t = _mirror(data, kind=t.kind)
        if t.status_category == "done" and not t.report:
            report = build_report(client, data)
            t.report, t.completed_by = report, (report.get("completed_by") or "")[:200]
            t.save(update_fields=["report", "completed_by", "updated_at"])
            Change.objects.create(person=t.person, kind=Change.TASK, actor="prbc", data={"task": t.prbc_id},
                                  text=(f"Bajarildi: {t.code} — {t.title}"
                                        + (f" ({t.completed_by})" if t.completed_by else ""))[:500])
            if t.support_task_id:
                _close_support(conn, t)
        elif t.status_category != before and t.support_task_id:
            from support.models import SupportTask
            SupportTask.objects.filter(pk=t.support_task_id).update(
                reply=f"{t.code}: {t.status_name} — {t.assignee} — {task_url(conn, t)}"[:2000])
        if t.status_category in OPEN and t.support_task_id:  # savol egasi keyin yuborgan rasm/izoh ham vazifaga
            try:
                sync_question(conn, client, t)
            except Exception:  # noqa: BLE001
                log.exception("sync question %s", t.prbc_id)
        if t.status_category != before:
            n += 1
    return n


def since_q(since):
    from django.db.models import Q
    return Q(prbc_created_at__gte=since) | Q(prbc_created_at__isnull=True, created_at__gte=since)


def stats(since=None):
    """Ijrochilar bo'yicha nazorat: jami, bajarilgan, ochiq, muddati o'tgan, muddatida bajarilgan, o'rtacha vaqt."""
    now = timezone.now()
    qs = Task.objects.filter(kind__in=[Task.OURS, Task.HIRE, Task.LEAVE])
    if since:
        qs = qs.filter(since_q(since))
    rows = {}
    for t in qs.only("people", "assignee", "status_category", "due_at", "completed_at", "prbc_created_at", "report"):
        names = [p["name"] for p in t.people or [] if p.get("role") == "assignee"] or [t.assignee.split(" +")[0] or "—"]
        for name in names:
            r = rows.setdefault(name, {"name": name, "total": 0, "done": 0, "open": 0, "overdue": 0, "late": 0,
                                       "cancelled": 0, "hours": []})
            r["total"] += 1
            if t.status_category == "cancelled":
                r["cancelled"] += 1
            elif t.status_category == "done":
                r["done"] += 1
                if (t.report or {}).get("on_time") is False:
                    r["late"] += 1
                if t.completed_at and t.prbc_created_at:
                    r["hours"].append((t.completed_at - t.prbc_created_at).total_seconds() / 3600)
            elif t.status_category in OPEN:
                r["open"] += 1
                if t.due_at and t.due_at < now:
                    r["overdue"] += 1
    out = []
    for r in rows.values():
        h = r.pop("hours")
        r["avg_hours"] = round(sum(h) / len(h), 1) if h else None
        out.append(r)
    return sorted(out, key=lambda r: (-r["open"], -r["total"]))


def group_stats(since=None):
    """Guruhlar bo'yicha: savollardan ochilgan vazifalar — jami, bajarilgan, ochiq, muddati o'tgan, bekor qilingan."""
    now = timezone.now()
    qs = Task.objects.filter(kind=Task.OURS)
    if since:
        qs = qs.filter(since_q(since))
    rows = {}
    for title, cat, due in qs.values_list("support_task__message__group__title", "status_category", "due_at"):
        name = title or "Guruhsiz (panel yoki shaxsiy chat)"
        r = rows.setdefault(name, {"name": name, "total": 0, "done": 0, "open": 0, "overdue": 0, "cancelled": 0})
        r["total"] += 1
        if cat == "done":
            r["done"] += 1
        elif cat == "cancelled":
            r["cancelled"] += 1
        elif cat in OPEN:
            r["open"] += 1
            if due and due < now:
                r["overdue"] += 1
    return sorted(rows.values(), key=lambda r: (-r["total"], r["name"]))
