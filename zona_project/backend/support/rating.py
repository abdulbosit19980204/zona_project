"""Xodimni baholash (⭐ 1–5): savol yopilgach savol egasi baholaydi (Telegram tugmalari) yoki admin panelda.
Baholar har bir xodimda yig'iladi (o'rtacha, soni, taqsimot) — savol yopildimi-yo'qmi dan tashqari sifat ko'rsatkichi."""
import html

from django.db.models import Avg, Count

from .models import Message, StaffRating, TgUser

ASK = {"uz": "⭐ {who} javobini baholang:", "ru": "⭐ Оцените ответ: {who}"}
THANKS = {"uz": "✅ Rahmat! Savol yopildi. Baho: {stars} ({who})", "ru": "✅ Спасибо! Вопрос закрыт. Оценка: {stars} ({who})"}


def answerer(q):
    """Savolga javob bergan xodim: qabul qilgan (handler), yoki birinchi xodim javobi muallifi."""
    if q.handler_id and q.handler.is_staff:
        return q.handler
    m = (Message.objects.filter(question=q, kind=Message.STAFF, user__isnull=False).select_related("user__member", "user__contact")
         .order_by("created_at").first())
    return m.user if m is not None and m.user.is_staff else None


def buttons(q):
    return [[{"text": "⭐" * n if n <= 3 else f"{n}⭐", "callback_data": f"st:{q.id}:{n}"} for n in range(1, 6)]]


def ask_text(q, staff):
    lang = "ru" if q.lang == "ru" else "uz"
    return ("✅ Спасибо! Вопрос закрыт.\n" if lang == "ru" else "✅ Rahmat! Savol yopildi.\n") + ASK[lang].format(
        who=html.escape(staff.staff_name()))


def rate(q, stars, by_user=None, by_name="", source="asker", staff=None, comment=""):
    """Baho yoziladi (bir manbadan bir kishi — bitta baho, qayta bosilsa yangilanadi). Qaytaradi: StaffRating yoki None."""
    stars = max(1, min(5, int(stars)))
    staff = staff or answerer(q)
    if staff is None:
        return None
    obj, _ = StaffRating.objects.update_or_create(
        question=q, source=source, by_name=(by_name or (by_user.staff_name() if by_user else ""))[:150],
        defaults={"staff": staff, "staff_name": staff.staff_name()[:150], "stars": stars, "by_user": by_user,
                  "comment": (comment or "")[:500]})
    return obj


def summary(user_ids):
    """{tg_user_id: {"avg", "n", "dist": [1..5 sanog'i]}}"""
    out = {}
    rows = StaffRating.objects.filter(staff_id__in=user_ids)
    for r in rows.values("staff_id").annotate(avg=Avg("stars"), n=Count("id")):
        out[r["staff_id"]] = {"avg": round(r["avg"], 2), "n": r["n"], "dist": [0] * 5}
    for sid, st in rows.values_list("staff_id", "stars"):
        out[sid]["dist"][st - 1] += 1
    return out


def staff_tg(name):
    return TgUser.objects.filter(contact__name=name).first() or TgUser.objects.filter(member__name=name).first()
