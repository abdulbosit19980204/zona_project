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
    # --- mijoz arizasi (savolda STIR / JShShIR / 1C kodi)
    {"key": "outlet_resend", "group": "request", "reversible": False,
     "title": "Arizani 1C ga qayta yuborish",
     "does": "Ariza «1C rad etdi» holatida va sababi 1C bazasi band / javob bermagani bo'lsa — arizani 1C ga qayta "
             "yuboradi. Ma'lumot xatosi (bo'linma, ma'lumotnoma) bo'lsa — qayta yubormaydi, nima qilishni yozadi.",
     "api": "POST /integrations/outlet-requests/{id}/send/"},
]

# keyingi bosqich: API bor, lekin bot savoldan hali bajarmaydi (sinovdan keyin qo'shiladi)
PLANNED = [
    {"key": "account_approve", "title": "Kutilayotgan hisobni tasdiqlash",
     "does": "«PRBC'ga kira olmayapman / ожидает подтверждения» — holati pending xodimni tasdiqlash (Employee + bo'lim + "
             "rol). HR qarori talab qilinishi mumkin.", "api": "POST /auth/admin/users/{id}/approve/"},
    {"key": "telegram_sync", "title": "Telegram ma'lumotini yangilash",
     "does": "Xodim Telegram nomi yoki username'ini o'zgartirgan bo'lsa — PRBC'dagi nusxani yangilash.",
     "api": "POST /auth/admin/users/{id}/telegram-sync/"},
    {"key": "module_seats", "title": "Vazifalar / Chat / Uchrashuvlar ruxsati",
     "does": "«Vazifalar ko'rinmayapti», «chat ochilmayapti» — tegishli modulga xodim darajasini berish.",
     "api": "POST /admin/organization-modules/{org}/task-access/ (chat-access, meeting-access)"},
    {"key": "route_resend", "title": "Mavjud nuqtani marshrutga qayta qo'shish",
     "does": "«Marshrutimga qo'shish» 1C da xato bergan bo'lsa — so'rovni qayta navbatga qo'yish.",
     "api": "POST /integrations/route-attachments/{id}/requeue/"},
]

KEYS = {a["key"] for a in CATALOG}
REVERSIBLE = {a["key"] for a in CATALOG if a["reversible"]}


def allowed(conn, key):
    """Amal yoqilganmi (panel → Yangi tochka ruxsatlari → Avtomatik amallar). Standart — o'chiq."""
    return bool(((getattr(conn, "auto_actions", None) or {}).get(key)) if conn is not None else False)
