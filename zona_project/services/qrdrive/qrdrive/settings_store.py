"""Bazadagi sozlamalar. Maxfiylar shifrlangan, API javobida faqat «o'rnatilgan/yo'q».
Har jarayon sozlamalarni bir necha soniyalik kesh bilan o'qiydi — o'zgarish qayta ishga tushirishsiz kuchga kiradi."""
from __future__ import annotations

import copy
import re
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .core.crypto import decrypt, encrypt
from .db.models import Setting

SECRET_KEYS = {"bot_token", "link_password"}
OLD_FILENAME_TEMPLATE = "{sana}_{vaqt}_{asl_nom}"
CACHE_TTL = 3.0

BOT_TEXTS: dict[str, dict[str, str]] = {
    "uz": {
        "start": "Assalomu alaykum, {name}! Menga fayl yuboring (hujjat, rasm, video, audio) — uni saqlab, havolasini QR kod ko'rinishida qaytaraman.\nMaksimal hajm: {max_mb} MB.\n\nRasm sifati buzilmasligi uchun «Fayl sifatida» yuboring.",
        "request_sent": "Assalomu alaykum! Sizning so'rovingiz administratorga yuborildi. Tasdiqlangach, fayl yubora olasiz.\nSizning ID: {id}",
        "request_pending": "So'rovingiz hali ko'rib chiqilmoqda. Tasdiqlangach xabar beramiz.",
        "blocked": "Sizga fayl yuklash ruxsati berilmagan. Administratorga murojaat qiling.",
        "approved": "✅ So'rovingiz tasdiqlandi! Endi fayl yuborishingiz mumkin.",
        "received": "⏳ Fayl qabul qilindi, navbatga qo'yildi…",
        "downloading": "⏳ Fayl olinmoqda…",
        "uploading": "⏳ Saqlash joyiga yuklanmoqda…",
        "sharing": "⏳ Havola yaratilmoqda…",
        "retrying": "⏳ Saqlash joyi vaqtincha javob bermayapti, birozdan keyin yana urinaman ({attempt}/{max})…",
        "done": "✅ Saqlandi: {path}\n{vis}\n🔗 {url}",
        "expires": "⏰ Havola {date} gacha amal qiladi",
        "duplicate": "ℹ️ Bu fayl avval yuklangan — oldingi QR kod:",
        "failed": "❌ Faylni saqlab bo'lmadi: {reason}\nAdministratorga xabar berildi.",
        "too_big": "Fayl juda katta ({size} MB). Ruxsat: {max_mb} MB gacha.",
        "type_not_allowed": "Bu turdagi fayllarni qabul qila olmayman. Ruxsat etilgan: {types}",
        "help": "Fayl yuboring — QR kod qaytaraman.\n/myfiles — oxirgi fayllarim\n/id — Telegram ID\n/lang — til",
        "myfiles_empty": "Hali fayl yubormagansiz.",
        "myfiles_title": "Oxirgi fayllaringiz:",
        "invite_ok": "✅ Akkauntingiz {name} xodimiga biriktirildi. Fayllaringiz saqlanib qolgan.",
        "invite_invalid": "Taklif havolasi yaroqsiz yoki muddati tugagan. Administratordan yangisini so'rang.",
        "lang_set": "Til: o'zbekcha",
        "send_file": "Iltimos, fayl yuboring. ID'ingizni bilish uchun: /id",
        "your_id": "Sizning Telegram ID: {id}",
        "link_refreshed": "🔗 Havola yangilandi.",
        "reg_welcome": "Assalomu alaykum! Botdan foydalanish uchun ro'yxatdan o'ting — 4 ta savol.",
        "reg_name": "1/4. To'liq ism-familiyangizni yozing (F.I.Sh.):",
        "reg_name_short": "Iltimos, to'liq F.I.Sh. ni yozing (kamida 2 so'z).",
        "reg_phone": "2/4. Telefon raqamingizni yuboring — pastdagi «📱 Raqamni yuborish» tugmasini bosing.",
        "reg_phone_btn": "📱 Raqamni yuborish",
        "reg_phone_wrong": "Iltimos, o'z raqamingizni pastdagi «📱 Raqamni yuborish» tugmasi orqali yuboring.",
        "reg_department": "3/4. Bo'limingizni tanlang yoki yozing:",
        "reg_position": "4/4. Lavozimingizni yozing:",
        "reg_skip": "⏭ O'tkazib yuborish",
        "reg_confirm": "Ma'lumotlaringiz:\n👤 {name}\n📱 {phone}\n🏢 {department}\n💼 {position}\n\nTo'g'rimi?",
        "reg_yes": "✅ Yuborish",
        "reg_edit": "✏️ Qaytadan",
        "reg_sent": "✅ Ro'yxatdan o'tdingiz. So'rovingiz administratorga yuborildi — tasdiqlangach fayl yubora olasiz.",
        "reg_need": "Avval ro'yxatdan o'ting — quyidagi savolga javob bering.",
        "ask_replace": "♻️ «{name}» avval yuklangan ({date}).\nEskisini yangilasak — QR va havola o'zgarmaydi. Yoki yangi fayl sifatida saqlaymizmi?",
        "ask_archive": "📦 «{name}» — arxiv.\nArxiv holida saqlaymizmi yoki ochib, papka qilib (bitta QR bilan ichidagi fayllar ko'rinadi)?",
        "btn_replace": "♻️ Eskisini yangilash",
        "btn_new": "🆕 Yangi fayl",
        "btn_archive": "📦 Arxiv holida",
        "btn_folder": "📂 Papka qilib",
        "replaced_done": "♻️ Yangilandi (v{version}): {path}\nQR va havola o'zgarmadi:\n🔗 {url}",
        "unchanged": "ℹ️ Fayl o'zgarmagan — oldingi QR:",
        "folder_done": "📂 Papka saqlandi: {count} ta fayl\n{path}\n{vis}\n🔗 {url}",
        "chosen": "⏳ Qabul qilindi: {choice}. Saqlanmoqda…",
        "ask_batch": "📥 {n} ta fayl qabul qilindi:\n{names}\n\nQanday saqlaymiz?",
        "btn_one_folder": "📂 Bitta papka (1 QR)",
        "btn_separate": "📄 Har biri alohida",
        "batch_more": "… yana {n} ta",
        "choose_visibility": "📎 {name}\nHavola turini tanlang:\n🌐 Public — havolasi bor har kim ochadi\n🔒 Private — faqat NAS'da ruxsati borlar ochadi",
        "btn_public": "🌐 Public",
        "btn_private": "🔒 Private",
        "vis_public": "🌐 Public havola",
        "vis_private": "🔒 Private havola (faqat ruxsat berilganlar)",
        "vis_chosen": "⏳ Qabul qilindi: {vis}. Saqlanmoqda…",
    },
    "ru": {
        "start": "Здравствуйте, {name}! Отправьте мне файл (документ, фото, видео, аудио) — я сохраню его и верну ссылку в виде QR-кода.\nМаксимальный размер: {max_mb} МБ.\n\nЧтобы не терять качество фото, отправляйте «Как файл».",
        "request_sent": "Здравствуйте! Ваш запрос отправлен администратору. После подтверждения вы сможете отправлять файлы.\nВаш ID: {id}",
        "request_pending": "Ваш запрос ещё рассматривается. Мы сообщим после подтверждения.",
        "blocked": "У вас нет доступа к загрузке файлов. Обратитесь к администратору.",
        "approved": "✅ Ваш запрос подтверждён! Теперь можно отправлять файлы.",
        "received": "⏳ Файл принят и поставлен в очередь…",
        "downloading": "⏳ Получаю файл…",
        "uploading": "⏳ Загружаю в хранилище…",
        "sharing": "⏳ Создаю ссылку…",
        "retrying": "⏳ Хранилище временно недоступно, попробую ещё раз ({attempt}/{max})…",
        "done": "✅ Сохранено: {path}\n{vis}\n🔗 {url}",
        "expires": "⏰ Ссылка действует до {date}",
        "duplicate": "ℹ️ Этот файл уже загружался — предыдущий QR-код:",
        "failed": "❌ Не удалось сохранить файл: {reason}\nАдминистратор уведомлён.",
        "too_big": "Файл слишком большой ({size} МБ). Допустимо: до {max_mb} МБ.",
        "type_not_allowed": "Такие файлы не принимаются. Разрешено: {types}",
        "help": "Отправьте файл — я верну QR-код.\n/myfiles — мои последние файлы\n/id — Telegram ID\n/lang — язык",
        "myfiles_empty": "Вы ещё не отправляли файлы.",
        "myfiles_title": "Ваши последние файлы:",
        "invite_ok": "✅ Аккаунт привязан к сотруднику {name}. Все файлы сохранены.",
        "invite_invalid": "Ссылка-приглашение недействительна или устарела. Попросите новую у администратора.",
        "lang_set": "Язык: русский",
        "send_file": "Пожалуйста, отправьте файл. Узнать свой ID: /id",
        "your_id": "Ваш Telegram ID: {id}",
        "link_refreshed": "🔗 Ссылка обновлена.",
        "reg_welcome": "Здравствуйте! Чтобы пользоваться ботом, пройдите регистрацию — 4 вопроса.",
        "reg_name": "1/4. Напишите полностью фамилию, имя, отчество (Ф.И.О.):",
        "reg_name_short": "Пожалуйста, напишите полное Ф.И.О. (минимум 2 слова).",
        "reg_phone": "2/4. Отправьте номер телефона — нажмите кнопку «📱 Отправить номер» внизу.",
        "reg_phone_btn": "📱 Отправить номер",
        "reg_phone_wrong": "Пожалуйста, отправьте свой номер кнопкой «📱 Отправить номер» внизу.",
        "reg_department": "3/4. Выберите или напишите свой отдел:",
        "reg_position": "4/4. Напишите свою должность:",
        "reg_skip": "⏭ Пропустить",
        "reg_confirm": "Ваши данные:\n👤 {name}\n📱 {phone}\n🏢 {department}\n💼 {position}\n\nВсё верно?",
        "reg_yes": "✅ Отправить",
        "reg_edit": "✏️ Заново",
        "reg_sent": "✅ Регистрация завершена. Запрос отправлен администратору — после подтверждения можно отправлять файлы.",
        "reg_need": "Сначала пройдите регистрацию — ответьте на вопрос ниже.",
        "ask_replace": "♻️ «{name}» уже загружался ({date}).\nОбновим старый — QR и ссылка не изменятся. Или сохраним как новый файл?",
        "ask_archive": "📦 «{name}» — архив.\nСохранить архивом или распаковать в папку (один QR — видны все файлы внутри)?",
        "btn_replace": "♻️ Обновить старый",
        "btn_new": "🆕 Новый файл",
        "btn_archive": "📦 Архивом",
        "btn_folder": "📂 Папкой",
        "replaced_done": "♻️ Обновлено (v{version}): {path}\nQR и ссылка не изменились:\n🔗 {url}",
        "unchanged": "ℹ️ Файл не изменился — прежний QR:",
        "folder_done": "📂 Папка сохранена: {count} файлов\n{path}\n{vis}\n🔗 {url}",
        "chosen": "⏳ Принято: {choice}. Сохраняю…",
        "ask_batch": "📥 Получено файлов: {n}\n{names}\n\nКак сохранить?",
        "btn_one_folder": "📂 Одной папкой (1 QR)",
        "btn_separate": "📄 Каждый отдельно",
        "batch_more": "… и ещё {n}",
        "choose_visibility": "📎 {name}\nВыберите тип ссылки:\n🌐 Public — откроет любой, у кого есть ссылка\n🔒 Private — только пользователи с доступом к NAS",
        "btn_public": "🌐 Public",
        "btn_private": "🔒 Private",
        "vis_public": "🌐 Публичная ссылка",
        "vis_private": "🔒 Приватная ссылка (только с доступом)",
        "vis_chosen": "⏳ Принято: {vis}. Сохраняю…",
    },
}

DEFAULTS: dict[str, Any] = {
    "setup_done": False,
    "company_name": "",
    # Tizim havolalari (/qrdrive/s/...) va QR'dagi manzil: masalan https://zona.stargroup.uz. Bo'sh — ishga tushirish qiymati
    "public_base_url": "",
    "bot_token": "",
    "bot_username": "",
    "bot_api_url": "",  # bo'sh = rasmiy api.telegram.org (20 MB yuklab olish cheklovi)
    "bot_api_local": False,
    "max_file_mb": 100,
    "allowed_types": "",  # bo'sh = hamma tur; masalan: pdf,docx,jpg,png
    "folder_template": "{xodim}",
    "filename_template": "{asl_nom}_{sana}_{vaqt}",  # kengaytma (.pdf, .jpg) doim oxiriga qo'yiladi
    # Havola turi: ask — botda tugmalar (Public / Private); public / private — har doim shu
    # Telegram'da ro'yxatdan o'tish majburiy: F.I.Sh., telefon (kontakt), bo'lim, lavozim -> keyin kirish so'rovi
    "registration_required": True,
    # Shu nomdagi fayl qayta yuborilsa: ask — so'rash | replace — eskisini yangilash (QR o'zgarmaydi) | new — yangi fayl
    "replace_mode": "ask",
    # Arxiv (zip, tar) yuborilsa: ask — so'rash | archive — arxiv holida | folder — ochib papka qilib (bitta QR)
    "archive_mode": "ask",
    # Bir nechta fayl birdaniga yuborilsa: ask — so'rash | folder — bitta papka (bitta QR) | separate — har biri alohida
    "multi_mode": "ask",
    "archive_max_files": 1000,
    "archive_max_mb": 2048,  # ochilgandagi umumiy hajm chegarasi (zip-bomba himoyasi)
    "visibility_mode": "ask",
    "default_visibility": "public",
    "visibility_timeout_min": 10,  # tanlanmasa shuncha daqiqadan keyin standart tur
    "link_expire_days": 0,
    "link_password": "",
    "duplicate_policy": "reuse",  # reuse — oldingi QR'ni yuborish | upload — baribir yuklash
    "auto_fallback": False,
    "qr_style": {"size": 600, "fg": "#000000", "bg": "#FFFFFF", "logo": False, "caption": "filename", "caption_text": ""},
    "bot_texts": BOT_TEXTS,
    "default_lang": "uz",
    "timezone": "Asia/Tashkent",
    "notify_chat_ids": "",
    "notify": {"failed": True, "storage": True, "quota": True, "request": True, "expiring": False, "daily": False},
    "daily_report_time": "09:00",
    "saved_minutes_per_file": 3,
    "retention_days": 365,
    "trash_days": 30,
    "backup_keep_days": 14,
}

# Admin paneldan o'zgartirish mumkin bo'lgan kalitlar va ularning turi
EDITABLE: dict[str, type] = {k: type(v) for k, v in DEFAULTS.items() if k not in ("bot_username",)}

_cache: tuple[float, dict[str, Any]] | None = None


def invalidate() -> None:
    global _cache
    _cache = None


async def load(session: AsyncSession, fresh: bool = False) -> dict[str, Any]:
    """Barcha sozlamalar (maxfiylar ochilgan holda — faqat server ichida ishlatiladi)."""
    global _cache
    if not fresh and _cache and time.monotonic() - _cache[0] < CACHE_TTL:
        return _cache[1]
    data = copy.deepcopy(DEFAULTS)
    for row in (await session.execute(select(Setting))).scalars():
        if row.key in SECRET_KEYS:
            data[row.key] = decrypt(row.secret_enc)
        elif row.key in ("qr_style", "notify") and isinstance(row.value, dict):
            data[row.key] = {**DEFAULTS[row.key], **row.value}
        elif row.key == "filename_template" and row.value == OLD_FILENAME_TEMPLATE:
            data[row.key] = DEFAULTS["filename_template"]  # eski standart -> asl nom boshida
        elif row.key == "bot_texts" and isinstance(row.value, dict):
            data[row.key] = {lang: {**BOT_TEXTS.get(lang, BOT_TEXTS["uz"]), **(row.value.get(lang) or {})} for lang in BOT_TEXTS}
        else:
            data[row.key] = row.value
    _cache = (time.monotonic(), data)
    return data


def public(data: dict[str, Any]) -> dict[str, Any]:
    """API uchun: maxfiylar o'rniga faqat o'rnatilganmi-yo'qmi."""
    out = {k: v for k, v in data.items() if k not in SECRET_KEYS}
    for k in SECRET_KEYS:
        out[f"{k}_set"] = bool(data.get(k))
    return out


async def save(session: AsyncSession, values: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    """Qiymatlarni saqlaydi. Qaytaradi: {kalit: (eski, yangi)} — jurnal uchun (maxfiylar yashirilgan)."""
    current = await load(session, fresh=True)
    changes: dict[str, tuple[Any, Any]] = {}
    for key, value in values.items():
        if key not in DEFAULTS:
            continue
        old = current.get(key)
        if key in SECRET_KEYS:
            value = str(value or "").strip()
            if value == old:
                continue
            row = await session.get(Setting, key) or Setting(key=key)
            row.secret_enc, row.value = encrypt(value), None
            session.add(row)
            changes[key] = ("••••••" if old else "", "••••••" if value else "")
            continue
        if old == value:
            continue
        row = await session.get(Setting, key) or Setting(key=key)
        row.value = value
        session.add(row)
        changes[key] = (old, value)
    await session.commit()
    invalidate()
    return changes


def public_base(settings: dict[str, Any]) -> str:
    from .core.config import config
    return (str(settings.get("public_base_url") or "").strip().rstrip("/")) or config.public_base_url


def text(settings: dict[str, Any], lang: str, key: str, **kw: Any) -> str:
    texts = settings.get("bot_texts") or BOT_TEXTS
    template = (texts.get(lang) or {}).get(key) or BOT_TEXTS.get(lang, BOT_TEXTS["uz"]).get(key) or BOT_TEXTS["uz"][key]
    try:
        return template.format(**kw)
    except (KeyError, IndexError):
        return template


def parse_ids(value: str) -> list[int]:
    return [int(x) for x in re.split(r"[,\s]+", value or "") if x.strip().lstrip("-").isdigit()]
