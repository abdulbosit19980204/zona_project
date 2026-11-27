"""Bot PRBC'da o'zi bajara oladigan amallar katalogi — har biri alohida ruxsat bilan (standart: o'chiq).

O'chiq amal: bot muammoni aniqlaydi, javobda nima topilganini va nima qilish kerakligini yozadi, savol mutaxassisga
o'tadi — PRBC'da hech narsa o'zgarmaydi. Yoqilgan amal: bot o'zi bajaradi va javobda nima qilinganini (oldin → keyin)
batafsil yozadi. Har amal AccessLog'ga oldingi va keyingi holati bilan yoziladi; ``reversible`` bo'lsa panelda
«Ortga qaytarish» bor."""

CATALOG = [
    # --- «Yangi tochka qo'sha olmayapman» (Заявки на точки: «ни одно подключение к 1С», «+» yo'q)
    {"key": "seat", "group": "outlet", "reversible": True,
     "title": "«Integratsiyalar» ruxsati — Xodim",
     "does": "Ruxsati yo'q yoki «Ko'ruvchi» savdo vakiliga «Xodim» darajasini beradi (Ko'ruvchi tochka yarata olmaydi). "
             "Admin va tekshiruvchiga tegilmaydi.",
     "api": "POST /admin/organization-modules/{org}/integration-access/"},
    {"key": "role", "group": "outlet", "reversible": True,
     "title": "Employee roli",
     "does": "Roli umuman yo'q xodimga Employee rolini beradi (butun tashkilot bo'yicha).",
     "api": "POST /auth/admin/users/{id}/roles/"},
    {"key": "node", "group": "outlet", "reversible": True,
     "title": "Guruh bo'limi",
     "does": "Xodimni savol yozilgan Telegram guruhiga mos PRBC bo'limiga qo'shadi (masalan «LOREAL ROP» guruhi → "
             "«LOREAL ROP» bo'limi). Asosiy bo'limi bo'lmasa — shu bo'lim asosiy bo'ladi; bor asosiy bo'lim o'zgarmaydi.",
     "api": "POST /auth/admin/users/{id}/nodes/"},
    {"key": "mapping", "group": "outlet", "reversible": True,
     "title": "1C pozivnoy biriktirish",
     "does": "Xodim yozgan pozivnoyni 1C ro'yxatidan aniq topib, shu bazada (food / nonfood) biriktiradi. To'liq yozilmasa "
             "— mos variantlarni ko'rsatib qayta so'raydi. Boshqa xodimga biriktirilgan pozivnoyga tegmaydi.",
     "api": "PUT /integrations/connections/{id}/employee-mappings/ (to'liq ro'yxat, saqlangach tekshiriladi)"},
    {"key": "refresh_refs", "group": "outlet", "reversible": False,
     "title": "1C ma'lumotnomalarini yangilash",
     "does": "Xodim yozgan pozivnoy 1C ro'yxatida topilmasa — bazaning ma'lumotnomalarini bir marta yangilab, qayta "
             "qidiradi (yangi qo'shilgan savdo vakili). Bir baza uchun soatiga ko'pi bilan bir marta.",
     "api": "POST /integrations/connections/{id}/refresh-refs/?groups=employees"},
    {"key": "telegram_sync", "group": "outlet", "reversible": False,
     "title": "Telegram ma'lumotini yangilash",
     "does": "Savol bergan xodimning Telegram username'i PRBC'dagidan farq qilsa (o'zgartirgan) — PRBC'dagi nusxani "
             "Telegram'dan qayta o'qitadi. Faqat Telegram ma'lumoti (ism, username, rasm) yangilanadi; kirish huquqiga "
             "tegilmaydi.",
     "api": "POST /auth/admin/users/{id}/telegram-sync/"},
    # --- PRBC modullari («PRBC'da vazifalar ko'rinmayapti», «PRBC chat ochilmayapti»)
    {"key": "task_seat", "group": "module", "reversible": True,
     "title": "«Vazifalar» moduli — A'zo",
     "does": "«PRBC'da vazifalar ko'rinmayapti / ochilmayapti» — moduldan ruxsati yo'q xodimga «A'zo» darajasini beradi. "
             "Ruxsati bor bo'lsa — aralashmaydi; menejer/admin darajasiga tegilmaydi.",
     "api": "POST /admin/organization-modules/{org}/task-access/"},
    {"key": "chat_seat", "group": "module", "reversible": True,
     "title": "«Chat» moduli — A'zo",
     "does": "«PRBC chat ochilmayapti» — moduldan ruxsati yo'q xodimga «A'zo» darajasini beradi. Ruxsati bor bo'lsa — "
             "aralashmaydi.",
     "api": "POST /admin/organization-modules/{org}/chat-access/"},
    # --- mijoz arizasi (savolda STIR / JShShIR / 1C kodi)
    {"key": "outlet_resend", "group": "request", "reversible": False,
     "title": "Arizani 1C ga qayta yuborish",
     "does": "Ariza «1C rad etdi» holatida va sababi 1C bazasi band / javob bermagani bo'lsa — arizani 1C ga qayta "
             "yuboradi. Ma'lumot xatosi (bo'linma, ma'lumotnoma) bo'lsa — qayta yubormaydi, nima qilishni yozadi.",
     "api": "POST /integrations/outlet-requests/{id}/send/"},
    {"key": "route_resend", "group": "request", "reversible": False,
     "title": "Mavjud nuqtani marshrutga qayta qo'shish",
     "does": "«Marshrutimga qo'shish» so'rovi 1C da xato bergan va sababi 1C bazasi band / javob bermagani bo'lsa — "
             "so'rovni qayta navbatga qo'yadi. Ma'lumot xatosida qayta yubormaydi.",
     "api": "POST /integrations/route-attachments/{id}/requeue/"},
    # --- «Bu raqam boshqa PRBC akkauntiga bog'langan» (prbc.binding): uchala asosiy amal birga yoqilganda ishlaydi
    {"key": "bind_unlink_old", "group": "binding", "reversible": True,
     "title": "1C xodimini eski akkauntdan uzish",
     "does": "G1–G7 shartlari bajarilganda 1C xodimini eski (1C, «Kutilmoqda», Telegramsiz) akkauntdan uzadi — /staff "
             "dagi «Bog'lanishni uzish». Ortga qaytarishda qayta bog'lanadi.",
     "api": "POST /hr/persons/{id}/unlink/"},
    {"key": "bind_free_phone", "group": "binding", "reversible": True,
     "title": "Eski akkauntdagi raqamni bo'shatish",
     "does": "Eski akkauntning Kirish telefoni maydonini tozalaydi (raqam buzilmaydi; eski qiymat jurnalda saqlanadi). "
             "PRBC bo'sh qiymatni qabul qilmasa — hammasi ortga qaytariladi, mutaxassisga o'tadi.",
     "api": "PATCH /auth/admin/users/{id}/profile/ {phone: \"\"}"},
    {"key": "bind_link_new", "group": "binding", "reversible": True,
     "title": "1C xodimini yangi (Telegram'li) akkauntga bog'lash",
     "does": "1C xodimini xodim Telegram orqali kirgan akkauntga bog'laydi — 1C ma'lumotlari (lavozim, bo'lim) shu "
             "akkauntga o'tadi. Ortga qaytarishda uziladi.",
     "api": "POST /hr/persons/{id}/link/ {employee}"},
    {"key": "bind_set_phone", "group": "binding", "reversible": True,
     "title": "Yangi akkauntga raqamni yozish (ixtiyoriy)",
     "does": "Xodim bot tugmasi orqali tasdiqlagan raqamni yangi akkauntning Kirish telefoniga yozadi. O'chiq bo'lsa — "
             "xodimga «PRBC botida raqamni qayta yuboring» deyiladi.",
     "api": "PATCH /auth/admin/users/{id}/profile/ {phone}"},
    {"key": "bind_archive_old", "group": "binding", "reversible": True,
     "title": "Bo'sh eski akkauntni bloklash (ixtiyoriy)",
     "does": "Bog'lashdan keyin bo'sh qolgan eski akkauntni bloklaydi (o'chirmaydi). Ortga qaytarishda qayta yoqiladi.",
     "api": "POST /auth/admin/users/{id}/active/ {is_active: false}"},
]

# keyingi bosqich: API bor, lekin bot savoldan hali bajarmaydi. Hisobni tasdiqlash (pending -> approve) bu yerda YO'Q:
# xodim PRBC'ga bog'langan guruhga qo'shilganda PRBC o'zi tasdiqlaydi — bot bunga tegmaydi.
PLANNED = []

KEYS = {a["key"] for a in CATALOG}
REVERSIBLE = {a["key"] for a in CATALOG if a["reversible"]}


def allowed(conn, key):
    """Amal yoqilganmi (panel → Yangi tochka ruxsatlari → Avtomatik amallar). Standart — o'chiq."""
    return bool(((getattr(conn, "auto_actions", None) or {}).get(key)) if conn is not None else False)
