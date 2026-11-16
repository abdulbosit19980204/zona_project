"""Vaqt va yuklama: har bir savol turi qancha vaqt oladi, haftasiga necha marta tushadi, kimga qancha soat to'g'ri keladi.

Formula (frontend lib/model.ts dagi bilan bir xil):
    haftalik daqiqa = bir martalik vaqt × haftasiga soni
    asosiy mas'ul — 100%, 1-zaxira — 15%, keyingi zaxiralar — 5% (asosiy mas'ul bo'lmaganda yoki
    yordam kerak bo'lganda ular ham vaqt sarflaydi)
    bandlik = (mas'ul + zaxira soatlari) / haftalik sig'im
"""
import re

from .models import Member, Task

FALLBACK_SHARE = (0.15, 0.05)
OVERLOAD, BUSY = 0.85, 0.7

# (kalit so'zlar regexi, daqiqa) — birinchi mos kelgani olinadi
RULES = [
    (r"yangi funksiya|funksiya taklif|biznes jarayonni o'zgartirish", 480),
    (r"yangi aksiya|aksiya yaratish|shartlari, muddati", 240),
    (r"yangi ustun|ko'rsatkich qo'shish|hisobot olish imkoniyati|formula", 240),
    (r"yangi filial|korporativ tarmoqqa ulash|it tayyorgarligi", 480),
    (r"kabel|lan port|yangi lan|rozetka", 120),
    (r"integratsiya|almashinuv|1c ga o'tmayapti|o'tmayapti|tizimlar o'rtasida|bog'lanish ishlamay|log va vaqt", 90),
    (r"server|ma'lumotlar bazasi|zaxira nusxa|ssl|portal", 60),
    (r"yangilanishdan keyin|dasturdagi xato|bug|hisoblanmayapti|noto'g'ri hisoblan|ishlamayapti|xato beryapti", 60),
    (r"ish joyi|telefon va dasturni tayyorlash|ta'mirlash|almashtirish", 60),
    (r"hisobot ochilmayapti|hisobot yangilanmagan|eksport", 45),
    (r"kompyuter|windows|disk|monitor|klaviatura|usb", 30),
    (r"internet|wi-?fi|vpn|tarmoq|ip manzil", 30),
    (r"dublikat|ikki marta|birlashtir", 20),
    (r"printer|skaner|nusxa ko'chirish|chek|shtrix", 20),
    (r"shubhali|ruxsatsiz|parol boshqa|yubormagan xabar", 20),
    (r"dostup|huquq|foydalanuvchi yaratish|ruxsat", 15),
    (r"yangi klient|klient qo'shish|ulanish|podklyuchen", 15),
    (r"ilova ochilmayapti|sinxron|ma'lumotlar yangilanmayapti|telefondan yangisiga|qayta sozlash|qayta ulash", 15),
    (r"marshrut|tashrif|jadval|plan", 10),
    (r"aksiya|chegirma|skidka|narx", 10),
    (r"o'zgartirish|tuzatish|noto'g'ri|to'g'rilash|yangilanmagan", 10),
    (r"parol|bloklangan|login|kira olmayapman|botga kirish", 5),
    (r"o'chirish|bekor qilish|olib tashlash|nofaol", 5),
]
ZONE_DEFAULT = {"distributsiya": 10, "protarget": 15, "1c": 15, "integratsiya": 90, "hisobot": 60, "infra": 30,
                "xavfsizlik": 20}


def estimate(task):
    """Savol matni va zonasiga qarab boshlang'ich taxmin: (daqiqa, haftasiga soni)."""
    title = task.title.lower().replace("ʻ", "'").replace("’", "'")
    minutes = next((m for rx, m in RULES if re.search(rx, title)), None)
    zone = task.process.zone.key if task.process_id and task.process.zone_id else ""
    if minutes is None:
        minutes = ZONE_DEFAULT.get(zone, 15)
    # takrorlanish: har bir savol haftasiga 1 marta deb hisoblanadi (kerak bo'lsa savolda qo'lda o'zgartiriladi)
    per_week = 1
    return minutes, per_week


def apply_estimates(force=False):
    """Vaqti qo'lda kiritilmagan savollarga taxmin qo'yadi. Qo'lda yoki AI kiritganiga tegmaydi (force bo'lmasa)."""
    n = 0
    for t in Task.objects.select_related("process__zone"):
        if t.time_source in ("manual", "ai") and not force:
            continue
        if t.time_source == "manual":
            continue
        minutes, per_week = estimate(t)
        if (t.minutes, t.per_week, t.time_source) != (minutes, per_week, "auto"):
            Task.objects.filter(pk=t.pk).update(minutes=minutes, per_week=per_week, time_source="auto")
            n += 1
    return n


def weekly_minutes(task):
    return (task.minutes or 0) * (task.per_week or 0)


def member_load(tasks=None, members=None):
    """{member_id: {...}} — mas'ul va zaxira daqiqalari, zonalar, bandlik."""
    tasks = tasks if tasks is not None else list(Task.objects.select_related("process__zone").prefetch_related("fallbacks"))
    members = members if members is not None else list(Member.objects.all())
    out = {m.id: {"member": m, "owner_min": 0.0, "backup_min": 0.0, "tasks": [], "zones": {}} for m in members}
    for t in tasks:
        w = weekly_minutes(t)
        zone = t.process.zone.name if t.process_id and t.process.zone_id else "—"
        if t.owner_id in out:
            o = out[t.owner_id]
            o["owner_min"] += w
            o["tasks"].append(t)
            o["zones"][zone] = o["zones"].get(zone, 0) + w
        for i, f in enumerate(sorted(t.fallbacks.all(), key=lambda f: f.order)):
            if f.member_id in out:
                share = FALLBACK_SHARE[0] if i == 0 else FALLBACK_SHARE[1]
                out[f.member_id]["backup_min"] += w * share
    for v in out.values():
        cap = max(v["member"].capacity or 0, 0.1)
        v["total_h"] = (v["owner_min"] + v["backup_min"]) / 60
        v["util"] = v["total_h"] / cap
        v["status"] = "over" if v["util"] > OVERLOAD else "busy" if v["util"] > BUSY else "ok"
    return out


def recommendations(load=None, tasks=None):
    """Qoidaga asoslangan tavsiyalar: ortiqcha yuklangan xodimning eng ko'p vaqt oladigan savolini
    navbatdagi (zaxira) yoki shu zonada ishlaydigan, bandligi past xodimga o'tkazish."""
    tasks = tasks if tasks is not None else list(Task.objects.select_related("process__zone").prefetch_related("fallbacks"))
    load = load or member_load(tasks)
    recs = []
    for mid, v in sorted(load.items(), key=lambda kv: -kv[1]["util"]):
        if v["status"] != "over":
            continue
        need_h = v["total_h"] - v["member"].capacity * BUSY
        moved = 0.0
        for t in sorted(v["tasks"], key=lambda t: -weekly_minutes(t)):
            if moved >= need_h:
                break
            # nomzodlar: rahbari (ish ko'p bo'lganda yordam beradi) -> shu zonadagi bir xil darajali hamkasb -> zaxira.
            # L3 (dasturchilar), tashqi hamkor va biznes (tasdiqlovchi) almashtiruvchi emas — ular faqat eskalatsiya/tasdiq bosqichi.
            me = v["member"]
            zone = t.process.zone_id if t.process_id else None
            cands = [me.manager_id] if me.manager_id else []
            cands += [o for o, ov in load.items() if o != mid and ov["member"].level == me.level and any(
                x.process_id and x.process.zone_id == zone for x in ov["tasks"])]
            cands += [f.member_id for f in sorted(t.fallbacks.all(), key=lambda f: f.order)]
            best = next((c for c in dict.fromkeys(cands) if c in load and c != mid and load[c]["status"] == "ok"
                         and load[c]["member"].level not in ("L3", "EXT")
                         and (load[c]["member"].level != "BIZ" or me.level == "BIZ")), None)
            if not best:
                continue
            h = weekly_minutes(t) / 60
            recs.append({"kind": "reassign", "task": t.id, "title": t.title, "from": mid, "to": best, "hours": round(h, 1)})
            moved += h
            load[best]["total_h"] += h  # keyingi tavsiyalar yangi yuklamani hisobga olsin
            load[best]["util"] = load[best]["total_h"] / max(load[best]["member"].capacity, 0.1)
            if load[best]["util"] > BUSY:
                load[best]["status"] = "busy"
        if moved < need_h:
            recs.append({"kind": "capacity", "member": mid, "hours": round(need_h - moved, 1)})
    return recs


def context_for_ai(lang=None):
    """AI tahlili uchun ixcham, real bazadan olingan ma'lumot."""
    tasks = list(Task.objects.select_related("process__zone", "owner").prefetch_related("fallbacks__member"))
    load = member_load(tasks)
    people = []
    for mid, v in load.items():
        m = v["member"]
        people.append({
            "id": mid, "name": m.name, "role": m.role, "level": m.level, "is_team": m.is_team,
            "duties": m.duties[:8], "not_for": m.excludes[:300], "capacity_h": m.capacity,
            "owner_h": round(v["owner_min"] / 60, 1), "backup_h": round(v["backup_min"] / 60, 1),
            "utilization_pct": round(v["util"] * 100), "status": v["status"],
            "zones_h": {z: round(mn / 60, 1) for z, mn in sorted(v["zones"].items(), key=lambda kv: -kv[1])},
        })
    heavy = sorted(tasks, key=lambda t: -weekly_minutes(t))[:40]
    items = [{"id": t.id, "q": t.title, "zone": t.process.zone.name if t.process_id and t.process.zone_id else "",
              "owner": t.owner.name if t.owner else None, "min": t.minutes, "per_week": t.per_week,
              "week_h": round(weekly_minutes(t) / 60, 1), "source": t.time_source,
              "next": [f.member.name for f in sorted(t.fallbacks.all(), key=lambda f: f.order)]} for t in heavy]
    unassigned = [t.title for t in tasks if not t.owner_id][:20]
    return {"people": people, "heaviest_questions": items, "unassigned_questions": unassigned,
            "total_week_h": round(sum(weekly_minutes(t) for t in tasks) / 60, 1),
            "rule_based": recommendations(load, tasks)}
