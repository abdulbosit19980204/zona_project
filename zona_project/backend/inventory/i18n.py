"""Foydalanuvchiga ko'rinadigan backend xabarlarining ruscha tarjimasi.

Frontend har so'rovda X-Lang sarlavhasini yuboradi; "ru" bo'lsa javobdagi "detail" va import xatolari tarjima qilinadi.
Kalit — o'zbekcha matn (kodda shu matn yoziladi), shuning uchun yangi xabar qo'shilsa, bu yerga ham qo'shing.
"""
import re

RU = {
    "Bu filialga yozish huquqingiz yo'q.": "Нет прав на запись в этот филиал.",
    "F.I.Sh. ni yozing.": "Укажите Ф.И.О.",
    "Filialni tanlang (faqat o'z filialingiz).": "Выберите филиал (только свой филиал).",
    "Filialni tanlang.": "Выберите филиал.",
    "Holat noto'g'ri.": "Неверное состояние.",
    "Qurilma turini tanlang.": "Выберите тип устройства.",
    "Soni 1 dan katta butun son bo'lsin.": "Количество — целое число от 1.",
    "Bu qiymat ishlatilmoqda — o'chirib bo'lmaydi.": "Значение используется — удалить нельзя.",
    "Bu xodimni o'zgartirish huquqingiz yo'q.": "Нет прав на изменение этого сотрудника.",
    "Bunday foydalanuvchi topilmadi.": "Пользователь не найден.",
    "Bunday kod yoki nomli filial bor.": "Филиал с таким кодом или названием уже есть.",
    "Bunday login bor.": "Такой логин уже есть.",
    "Bunday nom bor.": "Такое название уже есть.",
    "Daraja noto'g'ri.": "Неверный уровень доступа.",
    "Faqat boshqaruvchi filial qo'sha oladi.": "Добавлять филиалы может только администратор.",
    "Fayl tanlanmagan.": "Файл не выбран.",
    "Faylda 'F.I.Sh.' ustuni topilmadi. Xodimlar shablonini yuklab, shu shaklda to'ldiring.":
        "В файле нет столбца «F.I.Sh.». Скачайте шаблон сотрудников и заполните его.",
    "Faylda 'Qurilma turi' ustuni topilmadi. Shablon yoki eksport qilingan jadvalni yuklang.":
        "В файле нет столбца «Qurilma turi». Загрузите шаблон или выгруженную таблицу.",
    "Filialda qurilmalar bor — avval ularni o'chiring yoki boshqa filialga o'tkazing.":
        "В филиале есть устройства — сначала удалите их или перенесите в другой филиал.",
    "Kod va nom bo'sh bo'lmasin.": "Код и название не должны быть пустыми.",
    "Kod va nomni yozing.": "Укажите код и название.",
    "Login kamida 3 belgi bo'lsin.": "Логин — минимум 3 символа.",
    "Noma'lum katalog turi.": "Неизвестный тип справочника.",
    "Nomini yozing.": "Укажите название.",
    "Rasm tanlanmagan.": "Фото не выбрано.",
    "Ruxsat yo'q.": "Нет доступа.",
    "Bu amal faqat boshqaruvchi (IT) uchun.": "Это действие только для администратора (ИТ).",
    "Bu bo'lim faqat boshqaruvchi va rahbarlar uchun.": "Раздел только для администраторов и руководителей.",
    "Inventarizatsiya moduliga ruxsatingiz yo'q.": "У вас нет доступа к модулю инвентаризации.",
    "Sizda faqat ko'rish huquqi bor.": "У вас только права на просмотр.",
    "Telefon raqamini to'g'ri yozing (masalan: +998 90 123 45 67).": "Укажите номер телефона правильно (например: +998 90 123 45 67).",
    "Telegram username noto'g'ri (5–32 belgi: harf, raqam, _).": "Неверный Telegram username (5–32 символа: буквы, цифры, _).",
    "Bu xodimga qurilma biriktirilmagan.": "За этим сотрудником не закреплено устройств.",
    "Havola topilmadi yoki bekor qilingan.": "Ссылка не найдена или отменена.",
    "Bu tasdiqnoma allaqachon imzolangan.": "Этот акт уже подписан.",
    "Ism-familiyangizni to'liq yozing.": "Укажите полностью фамилию и имя.",
    "Imzo qo'ying (barmoq bilan chizing).": "Поставьте подпись (нарисуйте пальцем).",
    "Imzo rasmi noto'g'ri.": "Неверное изображение подписи.",
    "Narxni raqam bilan yozing (so'm).": "Укажите цену цифрами (сум).",
    "Kafolat muddati 0–600 oy oralig'ida bo'lsin.": "Срок гарантии — от 0 до 600 месяцев.",
    "Sotib olingan sana noto'g'ri.": "Неверная дата покупки.",
    # import xatolari
    "Faqat o'z filialingiz xodimlari": "Только сотрудники своего филиала",
}
PATTERNS = [
    (re.compile(r"^Faylni o'qib bo'lmadi: (.*)$"), "Не удалось прочитать файл: {0}"),
    (re.compile(r"^(.*): rasm juda katta \(≤15 MB\)\.$"), "{0}: фото слишком большое (≤15 МБ)."),
    (re.compile(r"^(.*): Fayl rasm emas yoki buzilgan\.$"), "{0}: файл не является фото или повреждён."),
    (re.compile(r"^Filial topilmadi: (.*)$"), "Филиал не найден: {0}"),
    (re.compile(r"^Qurilma turi topilmadi: (.*)$"), "Тип устройства не найден: {0}"),
    (re.compile(r"^(.*): yozish huquqi yo'q$"), "{0}: нет прав на запись"),
    (re.compile(r"^Telefon noto'g'ri: (.*)$"), "Неверный телефон: {0}"),
    (re.compile(r"^Telegram noto'g'ri: (.*)$"), "Неверный Telegram: {0}"),
    (re.compile(r"^(.*): raqam yozing\.$"), "{0}: укажите число."),
    (re.compile(r"^Sana tanilmadi: (.*)$"), "Дата не распознана: {0}"),
    (re.compile(r"^Holat tanilmadi \((.*)\) — 'Ishlayapti'$"), "Состояние не распознано ({0}) — «Работает»"),
]


def is_ru(request):
    return str(request.META.get("HTTP_X_LANG", "")).lower().startswith("ru")


def tr(text, ru=True):
    if not ru or not isinstance(text, str):
        return text
    if text in RU:
        return RU[text]
    for rx, tpl in PATTERNS:
        m = rx.match(text)
        if m:
            return tpl.format(*m.groups())
    return text


def translate_response(request, response):
    """DRF javobidagi detail va import xatolarini rus tiliga o'giradi (render qilinishidan oldin)."""
    if not is_ru(request):
        return response
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        if "detail" in data:
            data["detail"] = tr(str(data["detail"]))
        for key in ("errors", "warnings"):
            for row in data.get(key) or []:
                if isinstance(row, dict) and "message" in row:
                    row["message"] = tr(row["message"])
    return response
