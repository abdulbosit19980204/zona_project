"""Pro-target to'plami: Pro-target jamoasining o'z ko'rsatmalari asosida (2026-11-19, guruhdagi e'lonlari).

Manba — Pro-target jamoasi yozgan qoidalar, shuning uchun yozuvlar tasdiqlangan holda qo'shiladi.
`update` — mavjud (hali hech kim tegmagan) boshlang'ich shablonni shu matn bilan yangilash.
"""

PT, PTZ = "Pro-target", "ProTarget va mobil ilova"
BY = "Pro-target ko'rsatmasi"

VISIT_INFO_UZ = ("1. Xato skrinshoti\n2. Savdo nuqtasi (TT) kodi\n3. Geolokatsiyangiz (do'kon ichida turib)\n"
                 "4. Do'konning jonli (real vaqtda olingan) videosi — dumaloq video (kruzhok)")
VISIT_INFO_RU = ("1. Скриншот ошибки\n2. Код торговой точки (ТТ)\n3. Геолокация (находясь в магазине)\n"
                 "4. Видео магазина, снятое в реальном времени — кружочек")

PACK = [
    dict(
        title="ProTarget: vizitni (tashrifni) boshlab bo'lmayapti",
        status="approved", who=PT, zone=PTZ,
        questions=["vizit boshlanmayapti", "vizitni boshlay olmayapman", "tashrifni boshlab bo'lmayapti", "vizit ochilmayapti",
                   "vizit boshlash tugmasi ishlamayapti", "magazinda vizit ochilmadi", "не могу начать визит",
                   "визит не начинается", "не открывается визит", "не получается начать визит", "визит не стартует",
                   "не даёт начать визит", "vizit nachat ne mogu"],
        ask_first="",  # javobning o'zi kerakli ma'lumotlar ro'yxati
        answer=("Avval tekshiring: **UZ kodi bo'yicha aynan kerakli savdo nuqtasini** ochyapsizmi? Ko'p hollarda agentlar "
                "do'konlarni adashtirib, aslida yo'q muammo haqida yozadi.\n\n"
                "Haqiqatan ham vizitni boshlab bo'lmasa, darhol quyidagilarni yuboring:\n" + VISIT_INFO_UZ + "\n\n"
                "⚠️ Forward qilingan (boshqa joydan uzatilgan) xabarlar qabul qilinmaydi.\n"
                "To'liq ma'lumotsiz tekshirib bo'lmaydi — hammasini birdan yuborsangiz, muammo tezroq hal bo'ladi."),
        answer_ru=("Сначала проверьте: открываете ли вы **нужную торговую точку по коду УЗ**? Часто агенты путают магазины "
                   "и сообщают о проблеме, которой на самом деле нет.\n\n"
                   "Если вы действительно не можете начать визит, сразу приложите:\n" + VISIT_INFO_RU + "\n\n"
                   "⚠️ Пересланные сообщения не принимаются.\n"
                   "Без полной информации проверить невозможно — пришлите всё сразу, так проблема решится быстрее."),
    ),
    dict(
        title="ProTarget: savdo nuqtasi geolokatsiyasini (geoteg) o'zgartirish",
        status="approved", who=PT, zone=PTZ,
        questions=["geoteg o'zgartirish", "geolokatsiyani o'zgartirish kerak", "nuqta lokatsiyasi noto'g'ri", "lokatsiyani to'g'rilash",
                   "tochka joylashuvi xato", "gps nuqtani ko'chirish", "смена геотега", "поменять геолокацию точки",
                   "изменить геотег", "неправильная геолокация точки", "сменить координаты тт", "геотег не тот"],
        ask_first="",  # javobning o'zi kerakli ma'lumotlar ro'yxati
        answer=("Geotegni (nuqta joylashuvini) o'zgartirish uchun bir xabarda quyidagilarni yuboring:\n" + VISIT_INFO_UZ + "\n\n"
                "⚠️ Forward qilingan xabarlar qabul qilinmaydi. Ma'lumot to'liq bo'lmasa so'rov ko'rib chiqilmaydi.\n"
                "So'rovlar ish vaqtida (9:00–18:00) navbat tartibida ko'rib chiqiladi."),
        answer_ru=("Для смены геотега (координат точки) пришлите одним сообщением:\n" + VISIT_INFO_RU + "\n\n"
                   "⚠️ Пересланные сообщения не принимаются. Без полной информации запрос не рассматривается.\n"
                   "Запросы рассматриваются в рабочее время (9:00–18:00) в порядке очереди."),
    ),
    dict(
        title="ProTarget: moderatsiya natijasi va bildirishnomalar",
        status="approved", who=PT, zone=PTZ,
        questions=["tasdiqlandimi qanday bilaman", "moderatsiyadan o'tdimi", "nuqta tasdiqlandi mi", "bildirishnoma kelmadi",
                   "uvedomleniye kelmadi", "rad etildi qayerda ko'raman", "где посмотреть статус модерации",
                   "как узнать подтвердили точку", "уведомление не пришло", "точку отклонили где посмотреть",
                   "подтвердили ли тт"],
        ask_first="",
        answer=("Moderatsiya natijasi (tasdiqlandi yoki rad etildi) ilovada **bildirishnoma** bo'lib avtomatik keladi — "
                "chatda javob kutish shart emas. Shu maqsadda bildirishnomalar qilingan.\n\n"
                "Barcha bildirishnomalar ilovadagi **Profil → Bildirishnomalar** bo'limida saqlanadi.\n"
                "Bildirishnoma ko'rinmasa — telefon sozlamalarida ilova bildirishnomalari o'chirilmaganini tekshiring."),
        answer_ru=("Результат модерации (подтверждена или отклонена) приходит в приложение **уведомлением** автоматически — "
                   "ждать ответа в чате не нужно. Для этого уведомления и сделаны.\n\n"
                   "Все уведомления сохраняются в разделе **Профиль → Уведомления**.\n"
                   "Если уведомлений нет — проверьте, не отключены ли уведомления приложения в настройках телефона."),
    ),
    dict(
        update="ProTarget: yangi nuqta moderatsiyaga yuborilgan",
        title="ProTarget: yangi nuqta moderatsiyaga yuborilgan",
        status="approved", who=PT, zone=PTZ,
        questions=["moderatsiya qancha vaqt oladi", "qachon tasdiqlanadi", "tochka qachon tasdiqlanadi", "nuqta moderatsiyada",
                   "moderatsiyani tezlashtirish", "srochno tasdiqlab bering", "сколько длится модерация", "когда подтвердят точку",
                   "точка на модерации", "ускорить модерацию", "срочно подтвердите точку"],
        answer=("Nuqta moderatsiyaga yuborilgan — bu normal holat.\nNuqta: **{nom}**\n\n"
                "⏱ **Muddat:** ish vaqtida (9:00–18:00) odatda 5–10 daqiqa.\n"
                "🔎 **Nima tekshiriladi:** rasm, telefon, manzil, rekvizitlar va nom 100 m radiusdagi nuqtalar bilan solishtiriladi. "
                "Bozorlarda hajm katta (butiklar bir-biriga o'xshash), shuning uchun ko'proq vaqt olishi mumkin.\n"
                "📋 **Tartib:** navbat bo'yicha; juda shoshilinch bo'lsa — faollashtirilgan nuqtaning skrinshotini yuboring.\n"
                "🔔 **Natija:** ilovada bildirishnoma bo'lib keladi va **Profil → Bildirishnomalar** bo'limida saqlanadi — "
                "chatda kutish shart emas."),
        answer_ru=("Точка отправлена на модерацию — это нормально.\nТочка: **{nom}**\n\n"
                   "⏱ **Срок:** в рабочее время (9:00–18:00) обычно 5–10 минут.\n"
                   "🔎 **Что проверяется:** фото, телефон, адрес, реквизиты и название сравниваются с точками в радиусе 100 м. "
                   "На базарах объём большой (бутики похожи между собой), поэтому может занять больше времени.\n"
                   "📋 **Порядок:** в порядке очереди; если очень срочно — пришлите скриншот активированной ТТ.\n"
                   "🔔 **Результат:** приходит уведомлением в приложение и сохраняется в **Профиль → Уведомления** — "
                   "ждать в чате не нужно."),
    ),
]
