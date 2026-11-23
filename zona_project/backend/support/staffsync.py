"""Telegram foydalanuvchilarini haqiqiy xodimlarga bog'lash (PRBC / 1C / jamoa tuzilmasi).

- StaffPerson.telegram_id — eng aniq belgi: guruhda yozgan odam shu ID bo'yicha xodim kartasiga bog'lanadi;
- PRBC foydalanuvchisi (telegram_id, to'liq ism, lavozim, bo'lim, telefon) — TgUser'da "asli kim" sifatida saqlanadi,
  strukturada bo'lmagan xodimlar (ofis, ombor) ham tanilsin;
- qo'lda bog'langan (staff_link="manual") hech qachon o'zgartirilmaydi; avtomatik bog'lanish ID bo'yicha aniqlanadi.
"""
import re

from django.db import transaction

from .models import TgUser


def digits9(phone):
    d = re.sub(r"\D", "", str(phone or ""))
    return d[-9:] if len(d) >= 9 else ""


@transaction.atomic
def link_staff(people=None):
    """telegram_id bor xodim kartalari -> TgUser (yo'q bo'lsa yaratiladi, keyin u yozganda darhol taniladi).
    Qaytaradi: {"linked": n, "created": n, "kept_manual": n}."""
    from zona.models import StaffPerson
    qs = people if people is not None else StaffPerson.objects.filter(telegram_id__isnull=False, is_vacancy=False)
    out = {"linked": 0, "created": 0, "kept_manual": 0}
    for sp in qs:
        if not sp.telegram_id:
            continue
        u, created = TgUser.objects.get_or_create(tg_id=sp.telegram_id, defaults={
            "name": sp.name[:150], "username": (sp.telegram or "").lstrip("@")[:64]})
        out["created"] += created
        if u.staff_link == "manual" and u.staff_person_id and u.staff_person_id != sp.pk:
            out["kept_manual"] += 1
            continue
        if u.staff_person_id != sp.pk:
            TgUser.objects.filter(pk=u.pk).update(staff_person=sp, staff_link="prbc" if u.staff_link != "manual" else "manual")
            out["linked"] += 1
    return out


def staff_by_tg(tg_id, username=""):
    """Kontaktlardagi dala xodimi: avval Telegram ID, keyin @username bo'yicha (yagona bo'lsa)."""
    from zona.models import StaffPerson
    if tg_id:
        sp = StaffPerson.objects.filter(telegram_id=tg_id, is_vacancy=False).first()
        if sp:
            return sp
    u = (username or "").lstrip("@").lower()
    if u:
        hits = [p for p in StaffPerson.objects.filter(is_vacancy=False, telegram__iexact=u)[:2]]
        if len(hits) == 1:
            return hits[0]
    return None
