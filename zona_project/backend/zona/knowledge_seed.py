"""Savollar bazasini tartibga solish: zonalar, jarayon nomlari, doimiy savollar uchun aniq qoida va misollar.

Qayta ishga tushirish xavfsiz (idempotent): nomi bo'yicha topiladi, bor bo'lsa yangilanadi.
Ishga tushirish: python manage.py zona_knowledge [--dry-run]
"""
from django.db import transaction

from .models import Member, Process, Task, TaskFallback, Zone

ZONES = [
    # key, nomi, ikonka, rang, tavsif
    ("distributsiya", "Distributsiya", "truck", "#22C55E",
     "Savdo jarayoni: klient, savdo nuqtasi, marshrut va tashrif, plan, buyurtma, aksiya, agent profili. "
     "Asosan agent so'raydi; birinchi bo'lib supervayzer yoki operator javob beradi."),
    ("protarget", "ProTarget va mobil ilova", "smartphone", "#3987FF",
     "Kirish, parol, dostup va huquqlar, telefon almashtirish, mobil ilova va ProTarget dasturidagi xatolar."),
    ("1c", "1C va PRBC", "database", "#F59E0B",
     "1C va PRBC dagi ma'lumotlar, ularga dostup, 1C bot va 1C dasturidagi muammolar."),
    ("integratsiya", "Integratsiya", "plug", "#8B5CF6",
     "1C, ProTarget va PRBC o'rtasida ma'lumot o'tmasa, kechiksa yoki tizimlarda farq qilsa."),
    ("hisobot", "Hisobot va tahlil", "chart", "#06B6D4",
     "Hisobotlarga ruxsat, hisobot xatolari, yangi ko'rsatkichlar, o'zgarishlar tarixi va yangi funksiya takliflari."),
    ("infra", "IT infratuzilma", "server", "#64748B",
     "Kompyuter, printer, agent telefoni, internet, VPN, serverlar va ofis texnikasi."),
    ("xavfsizlik", "Pochta va xavfsizlik", "shield", "#EF4444",
     "Korporativ pochta, shubhali xatlar, parol oshkor bo'lishi, ruxsatsiz kirish va huquqlar."),
]

# eski nom -> (zona, yangi nom, tavsif). Nom allaqachon yangilangan bo'lsa — yangi nom bo'yicha topiladi.
PROCESSES = [
    ("1C & ProTarget & PRBC: klient", "distributsiya", "Klient bazasi: yaratish va ma'lumotlar",
     "Yangi klient, rekvizitlar, dublikat, tasdiqlash, faollashtirish va yopish."),
    ("ProTarget: klientga ulanish", "distributsiya", "Klientni agentga biriktirish",
     "Klientni agentga ulash, agentda ko'rinmasligi, boshqa agentga o'tkazish."),
    ("ProTarget: savdo nuqtalari va hudud", "distributsiya", "Savdo nuqtalari va hudud",
     "Nuqtani biriktirish, nomi/manzili, GPS, yangi hudud, hudud bo'yicha ko'rinish."),
    ("ProTarget: marshrut, plan, tashrif", "distributsiya", "Marshrut, tashrif va plan",
     "Marshrutga nuqta qo'shish, tashrif kunlari, haftalik jadval, plan ko'rsatkichi."),
    ("ProTarget: agent profili", "distributsiya", "Agent profili",
     "Agent ma'lumotlari, supervayzerga biriktirish, ishga kirish va ketish."),
    ("ProTarget: aksiya va chegirma", "distributsiya", "Aksiya va chegirmani klientga qo'llash",
     "Mavjud aksiya yoki skidkani klientga biriktirish, noto'g'ri chegirma, maxsus narx."),
    ("Aksiya yaratish", "distributsiya", "Yangi aksiya yaratish",
     "Yangi aksiya, uning shartlari va muddati, ProTarget va 1C da bir xil bo'lishi."),
    ("Aksiya va chegirma ishlamayapti", "distributsiya", "Aksiya va chegirma ishlamayapti",
     "Aksiya biriktirilgan, lekin buyurtmada hisoblanmasa yoki narx o'zgarmasa."),
    ("ProTarget: buyurtma va tovar", "distributsiya", "Buyurtma va tovar",
     "Buyurtmani o'chirish, tovar qo'shish/almashtirish, miqdor, narx, summa farqi."),
    ("1C bot: klient qo'shish", "distributsiya", "1C bot orqali klient qo'shish",
     "Agent bot orqali klient qo'shadi va holatini kuzatadi."),
    ("ProTarget: dostup ochish", "protarget", "Dostup ochish", "Yangi agent yoki supervayzerga akkaunt va huquqlar."),
    ("ProTarget: dostupni o'zgartirish va yopish", "protarget", "Dostupni o'zgartirish va yopish",
     "To'xtatish, ishdan ketganda yopish, hudud o'zgarganda eski huquqni olish."),
    ("ProTarget: kirish muammolari", "protarget", "Kirish muammolari",
     "Parol, bloklangan akkaunt, \"ruxsat yo'q\", menyular ko'rinmasligi."),
    ("ProTarget: telefon va akkaunt", "protarget", "Telefon almashtirish va akkaunt",
     "Akkauntni yangi telefonga ko'chirish, yo'qolgan telefonni bloklash."),
    ("ProTarget: mobil ilovaning texnik xatolari", "protarget", "Mobil ilova xatolari",
     "Ilova ochilmasa, sinxronlanmasa, buyurtma yuborilmasa, ruxsatlar o'chsa."),
    ("ProTarget dasturi", "protarget", "ProTarget dasturidagi xatolar",
     "Dasturdagi bug, yangilanishdan keyingi xato, plan hisoblash, xarita va bildirishnomalar."),
    ("1C: ma'lumot", "1c", "1C: ma'lumot kiritish va tuzatish", "1C da hujjat va ma'lumotni kiritish, tuzatish, o'chirish."),
    ("1C va PRBC: dostup", "1c", "1C va PRBC: dostup", "Foydalanuvchi yaratish, parol, huquq va menyular."),
    ("1C bot: kirish", "1c", "1C bot: kirish va huquq", "Botga kirish, menyu yoki tugma chiqmasligi."),
    ("1C bot", "1c", "1C bot ishlamayapti", "Bot javob bermasa, funksiya ishlamasa, yangi funksiya kerak bo'lsa."),
    ("1C dasturi", "1c", "1C dasturi", "1C sekinligi, yangilanishdan keyingi xato, chop etish va eksport."),
    ("Integratsiya: 1C va ProTarget", "integratsiya", "1C ↔ ProTarget almashinuvi",
     "Buyurtma, klient yoki o'zgarish tizimlar o'rtasida o'tmasa yoki farq qilsa."),
    ("Integratsiya: PRBC", "integratsiya", "PRBC almashinuvi", "PRBC va ProTarget ma'lumotlari mos kelmasa."),
    ("Hisobotlarga ruxsat", "hisobot", "Hisobotlarga ruxsat", "Hisobotni ko'rish huquqi."),
    ("Hisobotlar", "hisobot", "Hisobotlar", "Hisobot ochilmasa, yangilanmasa, formula xato, yangi ko'rsatkich kerak."),
    ("Yangi funksiya va tarix", "hisobot", "Yangi funksiya va o'zgarishlar tarixi",
     "Kim nimani o'zgartirganini ko'rish, yangi funksiya taklifi."),
    ("Kompyuter va ish joyi", "infra", "Kompyuter va ish joyi", ""),
    ("Printer, skaner, ofis qurilmalari", "infra", "Printer, skaner, ofis qurilmalari", ""),
    ("Agentning telefoni va jihozi", "infra", "Agentning telefoni va jihozi", ""),
    ("Internet va tarmoq", "infra", "Internet va tarmoq", ""),
    ("VPN va masofaviy kirish", "infra", "VPN va masofaviy kirish", ""),
    ("Serverlar (sysadmin)", "infra", "Serverlar", ""),
    ("Ofis va filial", "infra", "Ofis va filial", ""),
    ("Pochta", "xavfsizlik", "Korporativ pochta", ""),
    ("Xavfsizlik", "xavfsizlik", "Axborot xavfsizligi", ""),
]

# Nomi ro'yxatda bo'lmagan jarayonlar uchun: avval mazmuni (kalit so'zlar), keyin tizimi bo'yicha
DIST_WORDS = ("klient", "marshrut", "buyurtma", "aksiya", "chegirma", "nuqta", "hudud", "plan", "tashrif", "agent profili")
BY_SYSTEM = {"protarget": "protarget", "mobil ilova": "protarget", "1c": "1c", "1c bot": "1c", "prbc": "1c",
             "integratsiya": "integratsiya", "hisobot": "hisobot", "umumiy": "hisobot", "qurilma": "infra", "tarmoq": "infra",
             "server": "infra", "ofis": "infra", "pochta": "xavfsizlik", "xavfsizlik": "xavfsizlik"}


def guess_zone(process):
    name = process.name.lower()
    system = process.system.name.lower() if process.system else ""
    if any(w in name for w in DIST_WORDS) and not any(w in name for w in ("dostup", "kirish", "integratsiya")):
        return "distributsiya"
    if "integratsiya" in name:
        return "integratsiya"
    return BY_SYSTEM.get(system, "hisobot" if not system else "protarget")


# Zonaga qarab kim odatda so'raydi (savolning o'zida ko'rsatilmagan bo'lsa)
ASKER = {"distributsiya": "Agent", "protarget": "Agent", "1c": "Operator", "integratsiya": "Operator",
         "hisobot": "Supervayzer", "infra": "Ofis xodimi", "xavfsizlik": "Hamma"}

SV, OP, IT, DEV, TECH, PT, OPS = ("Supervayzerlar", "Saidabror", "Xusniddin", "Dasturchilar jamoasi", "Jahongir",
                                  "Pro-target", "Abdulbosit Tuychiev")

# Doimiy savollar: sarlavha (yoki [eski, yangi]) -> qoida, misollar, kim so'raydi, egasi, navbat [(kim, qachon)]
QUESTIONS = [
    {
        "title": ["Klient agent ro'yxatidan yo'qolgan yoki tashrif ro'yxatida chiqmayapti",
                  "Klient bazada bor, lekin agentda ko'rinmayapti"],
        "owner": SV,
        "fallbacks": [(OP, "Klient bazada umuman topilmasa — yangi klient yaratadi"),
                      (IT, "Marshrutga qo'shilgan, lekin ilovada baribir ko'rinmasa — sinxronlashni tekshiradi")],
        "rule": "1) Agent supervayzeriga yozadi: klient nomi, STIR yoki kodi.\n"
                "2) Supervayzer klientni agentning tashrif marshrutiga (kerakli kunga) qo'shadi — odatda shu yetarli.\n"
                "3) Klient bazada umuman topilmasa — Operator yangi klient yaratadi.\n"
                "4) Marshrutda bor, lekin ilovada ko'rinmasa — IT administrator sinxronlashni tekshiradi.",
        "examples": ["klient agentda ko'rinmayapti", "klient bazada bor lekin menda chiqmayapti", "klientim yo'qolib qoldi",
                     "tochka ro'yxatda yo'q", "magazin tashrif ro'yxatida chiqmayapti",
                     "клиент не отображается у агента", "клиента нет в маршруте"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Yangi klient qo'shish", "owner": SV,
        "fallbacks": [(OP, "Supervayzer tasdiqlagach — 1C va ProTarget'da klientni yaratadi")],
        "rule": "1) Agent yangi klient ma'lumotlarini supervayzerga yuboradi (yoki 1C bot orqali kiritadi): "
                "nomi, STIR, manzil, telefon, nuqta rasmi.\n"
                "2) Supervayzer tekshirib tasdiqlaydi.\n"
                "3) Operator klientni yaratadi; supervayzer uni agent marshrutiga qo'shadi.",
        "examples": ["yangi klient qanday qo'shiladi", "yangi magazin qo'shish kerak", "klient qo'shib bering",
                     "yangi tochka ochish", "новый клиент добавить", "как добавить нового клиента"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Dublikat klient (\"bunday klient mavjud\", ikki marta yaratilgan)", "owner": OP,
        "fallbacks": [(SV, "Qaysi kartochka to'g'riligini tasdiqlaydi"),
                      (DEV, "Dublikat integratsiya sababli qayta-qayta paydo bo'lsa")],
        "rule": "Operator ikkala kartochkani solishtiradi, to'g'risini qoldiradi, ortiqchasini yopadi; buyurtmalar bo'lsa "
                "to'g'ri kartochkaga o'tkaziladi. Dublikat o'z-o'zidan qayta paydo bo'lsa — Dasturchilar (integratsiya).",
        "examples": ["bunday klient mavjud deyapti", "klient ikki marta chiqyapti", "klient dublikat bo'lib qoldi",
                     "дубликат клиента"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Klient nomi, manzili, STIR yoki identifikatsiya ma'lumoti noto'g'ri", "owner": SV,
        "fallbacks": [(OP, "Supervayzer tasdiqlagach — 1C va ProTarget'da tuzatadi")],
        "rule": "Agent to'g'ri ma'lumotni (hujjat rasmi bilan) supervayzerga yuboradi; supervayzer tasdiqlaydi; "
                "Operator 1C va ProTarget'da bir xil qilib tuzatadi.",
        "examples": ["klient STIR xato", "klient manzili noto'g'ri", "klient nomini o'zgartirish", "ИНН клиента неправильный"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Klientga ulanish (podklyucheniya) qilish", "owner": SV,
        "fallbacks": [(OP, "Supervayzerda ulash huquqi bo'lmasa")],
        "rule": "Supervayzer klientni agentga ulaydi va marshrutiga qo'shadi. Keyingi sinxronlashdan so'ng agentda chiqadi.",
        "examples": ["podklyucheniya qilish kerak", "klientni menga ulab bering", "klientni agentga biriktirish",
                     "подключить клиента к агенту"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Klientni boshqa agentga o'tkazish yoki vaqtincha biriktirish", "owner": SV,
        "fallbacks": [(OP, "Supervayzerda huquq bo'lmasa")],
        "rule": "Supervayzer klientni yangi agentga o'tkazadi va eski agent marshrutidan olib tashlaydi. "
                "Vaqtincha bo'lsa — muddatini ko'rsatadi.",
        "examples": ["klientni boshqa agentga berish", "agent ta'tilda, klientlarini kim oladi", "передать клиента другому агенту"],
        "asker": "Supervayzer", "frequent": True,
    },
    {
        "title": "Agent boshqa hudud nuqtalarini ko'ryapti", "owner": IT,
        "fallbacks": [(OP, "Hududning o'zi agentga noto'g'ri biriktirilgan bo'lsa")],
        "rule": "Bu huquq sozlamasi: IT administrator agent hududini va ko'rish huquqini to'g'rilaydi. "
                "Hudud kartochkada noto'g'ri bo'lsa — Operator tuzatadi.",
        "examples": ["agentda boshqa hudud klientlari chiqyapti", "begona tochkalar ko'rinyapti", "агент видит чужие точки"],
        "asker": "Supervayzer", "frequent": False,
    },
    {
        "title": "Marshrutga nuqta qo'shish yoki olib tashlash", "owner": SV,
        "fallbacks": [(OP, "Supervayzer ProTarget'da o'zgartira olmasa"),
                      (IT, "Qo'shildi, lekin ertasi kuni ham ilovada ko'rinmasa")],
        "rule": "Supervayzer ProTarget'da agent marshrutiga nuqtani qo'shadi yoki olib tashlaydi va tashrif kunini belgilaydi. "
                "O'zgarish keyingi sinxronlashda agentda chiqadi.",
        "examples": ["marshrutga tochka qo'shish", "nuqtani marshrutdan olib tashlash", "marshrutga klient qo'shib bering",
                     "добавить точку в маршрут"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Tashrif kunini o'zgartirish, shanba yoki bayram kunini olib tashlash", "owner": SV,
        "rule": "Supervayzer marshrutda tashrif kunlarini o'zgartiradi. Bayram kunlari uchun jadvalni oldindan yangilaydi.",
        "examples": ["tashrif kunini o'zgartirish", "shanba kuni marshrut kerak emas", "день визита поменять"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Plan ko'rsatkichini kiritish yoki to'g'rilash", "owner": SV,
        "rule": "Plan supervayzer tomonidan kiritiladi. Plan to'g'ri kiritilgan, lekin bajarilishi noto'g'ri hisoblansa — "
                "\"Plan, tashrif soni ... noto'g'ri hisoblanishi\" savoli (Dasturchilar).",
        "examples": ["plan noto'g'ri", "planni o'zgartirish kerak", "план неправильный"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Tasdiqlangan marshrut yoki jadval tizimdan ilovaga uzatilmayapti", "owner": IT,
        "fallbacks": [(DEV, "Ko'p agentda bir vaqtda takrorlansa — tizim xatosi")],
        "rule": "IT administrator agent qurilmasida sinxronlashni va akkauntni tekshiradi. Muammo ko'p agentda bo'lsa — Dasturchilar.",
        "examples": ["marshrut ilovaga tushmadi", "yangi marshrut ko'rinmayapti", "маршрут не пришёл в приложение"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Ishdan ketgan agent profilini nofaol qilish", "owner": IT,
        "fallbacks": [(SV, "Agentning klientlarini boshqa agentga o'tkazadi")],
        "rule": "Supervayzer agent ketganini xabar qiladi → IT administrator profilni nofaol qiladi va dostupni yopadi → "
                "supervayzer klientlarni boshqa agentga o'tkazadi.",
        "examples": ["agent ishdan ketdi", "agentni o'chirish", "уволился агент"],
        "asker": "Supervayzer", "frequent": True,
    },
    {
        "title": "Yangi agent yoki supervayzerga ProTarget dostupi va huquqlari", "owner": IT,
        "fallbacks": [(TECH, "Yangi agentga telefon tayyorlash kerak bo'lsa")],
        "rule": "Supervayzer yangi agent ma'lumotini yuboradi: F.I.Sh., telefon, hudud, supervayzeri. IT administrator akkaunt va "
                "huquqlarni ochadi; Texnik telefonni tayyorlaydi; supervayzer klientlarni biriktiradi.",
        "examples": ["yangi agentga dostup", "yangi xodimga ProTarget ochish", "доступ новому агенту"],
        "asker": "Supervayzer", "frequent": True,
    },
    {
        "title": "Parolni tiklash", "owner": IT,
        "fallbacks": [(OPS, "IT administrator bo'lmasa yoki tizim parol tiklashga ruxsat bermasa")],
        "rule": "Agent IT administratorga yozadi (o'z telefon raqamidan). IT administrator shaxsni tasdiqlab vaqtinchalik parol beradi; "
                "agent birinchi kirishda parolni almashtiradi.",
        "examples": ["parol esdan chiqdi", "parolni unutdim", "kira olmayapman parol xato", "забыл пароль"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Eski telefondan yangisiga akkauntni ko'chirish", "owner": IT,
        "rule": "Agent eski va yangi telefon ma'lumotini yuboradi. IT administrator akkauntni yangi qurilmaga ko'chiradi va "
                "eski qurilmadan chiqaradi. Yuborilmagan buyurtmalar bo'lsa — avval eski telefondan sinxronlanadi.",
        "examples": ["telefon almashtirdim", "yangi telefonga ilovani o'tkazish", "сменил телефон"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Ilova ochilmayapti, oq ekran, o'z-o'zidan yopilyapti", "owner": IT,
        "fallbacks": [(TECH, "Telefonning o'zi nosoz bo'lsa")],
        "rule": "1) Agent telefonni qayta yoqadi va internetni tekshiradi.\n"
                "2) Hal bo'lmasa — IT administratorga ekran rasmi bilan yozadi.\n"
                "3) Telefonning o'zi nosoz bo'lsa — Texnik.",
        "examples": ["ilova ochilmayapti", "oq ekran chiqyapti", "dastur yopilib qolyapti", "приложение не открывается"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Sinxronlash tugamayapti yoki xato beryapti", "owner": IT,
        "fallbacks": [(DEV, "Ko'p agentda bir vaqtda bo'lsa — tizim muammosi")],
        "rule": "Agent internetni tekshirib qayta sinxronlaydi. O'tmasa — IT administrator. "
                "Bir vaqtda ko'p agentda bo'lsa — Dasturchilar (tizim muammosi).",
        "examples": ["sinxron bo'lmayapti", "sinxronizatsiya xato", "obmen o'tmayapti", "синхронизация не проходит"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Buyurtma yuborishda texnik xato chiqyapti (diagnostika)", "owner": IT,
        "fallbacks": [(DEV, "Xato dastur yoki integratsiyada bo'lsa")],
        "rule": "Agent xato matni rasmini yuboradi. IT administrator sababini aniqlaydi: internet/qurilma — o'zi hal qiladi, "
                "dastur yoki integratsiya — Dasturchilarga beradi.",
        "examples": ["zakaz ketmayapti", "buyurtma yuborilmayapti xato", "заказ не отправляется"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Klientga aksiya qo'shish yoki olib tashlash", "owner": OP,
        "fallbacks": [(SV, "So'rovni tasdiqlaydi"), (DEV, "Kerakli aksiya tizimda umuman bo'lmasa — yangi aksiya")],
        "rule": "Supervayzer so'rovni tasdiqlaydi; Operator mavjud aksiyani klientga biriktiradi yoki olib tashlaydi. "
                "Yangi aksiya kerak bo'lsa — Dasturchilar jamoasi (\"Yangi aksiya yaratish\").",
        "examples": ["klientga aksiya qo'shish", "aksiya biriktirib bering", "skidka yoqib bering", "добавить акцию клиенту"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Aksiya klientga qo'shilgan, lekin buyurtmada ishlamayapti", "owner": OP,
        "fallbacks": [(DEV, "Biriktirish to'g'ri, lekin aksiya hisoblanmasa"), (PT, "Xato ProTarget dasturining o'zida bo'lsa")],
        "rule": "1) Operator aksiya klientga to'g'ri biriktirilganini va muddatini tekshiradi.\n"
                "2) To'g'ri bo'lsa — Dasturchilar hisoblash qoidasini tekshiradi.\n"
                "3) Xato ProTarget'ning o'zida bo'lsa — Pro-target support.",
        "examples": ["aksiya ishlamayapti", "skidka tushmayapti", "aksiya bor lekin narx o'zgarmadi", "акция не работает"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Buyurtmani o'chirish", "owner": OP,
        "fallbacks": [(SV, "O'chirishni tasdiqlaydi")],
        "rule": "Agent buyurtma raqami va sababini supervayzerga yozadi; supervayzer tasdiqlaydi; Operator buyurtmani o'chiradi "
                "(1C ga o'tgan bo'lsa — 1C da ham).",
        "examples": ["zakazni o'chirish", "buyurtma xato ketdi", "buyurtmani bekor qilish", "удалить заказ"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Buyurtmaga tovar qo'shish, almashtirish yoki o'chirish", "owner": OP,
        "rule": "Agent buyurtma raqami va o'zgarishni yozadi; Operator 1C ga o'tishidan oldin tuzatadi. "
                "1C ga o'tib bo'lgan bo'lsa — 1C da tuzatadi.",
        "examples": ["zakazga tovar qo'shish", "tovarni almashtirish", "buyurtmada xato tovar", "изменить заказ"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "Kerakli tovar ro'yxatda chiqmayapti", "owner": OP,
        "fallbacks": [(DEV, "Tovar 1C da bor, ProTarget'ga o'tmagan bo'lsa — integratsiya")],
        "rule": "Operator tovar 1C da faol ekanini va agent narx turida borligini tekshiradi. 1C da bor, ProTarget'da yo'q bo'lsa — "
                "Dasturchilar (integratsiya).",
        "examples": ["tovar chiqmayapti", "mahsulot ro'yxatda yo'q", "товара нет в списке"],
        "asker": "Agent", "frequent": True,
    },
    {
        "title": "ProTargetdagi buyurtma 1C ga o'tmayapti (yoki 1C dagi buyurtma ProTargetda yo'q)", "owner": DEV,
        "fallbacks": [(PT, "Xato ProTarget tomonda bo'lsa")],
        "rule": "Operator buyurtma raqamini va vaqtini Dasturchilarga yuboradi; Dasturchilar almashinuv logini tekshiradi. "
                "ProTarget tomonda bo'lsa — Pro-target support.",
        "examples": ["zakaz 1C ga tushmadi", "buyurtma 1C da yo'q", "заказ не ушёл в 1С"],
        "asker": "Operator", "frequent": True,
    },
    {
        "title": "Supervayzer jamoa hisobotini yoki barcha agent ma'lumotini ko'ra olmayapti", "owner": IT,
        "rule": "IT administrator supervayzer huquqlariga jamoa agentlarini biriktiradi.",
        "examples": ["hisobotda agentlarim yo'q", "jamoa hisoboti ko'rinmayapti", "не вижу отчёт по команде"],
        "asker": "Supervayzer", "frequent": True,
    },
    {
        "title": "Internet yo'q, sekin yoki uzilib qolyapti", "owner": TECH,
        "rule": "Texnik ofis tarmog'ini tekshiradi. Faqat bitta ilova ishlamasa (internet bor) — IT administrator.",
        "examples": ["internet yo'q", "internet sekin", "интернет не работает"],
        "asker": "Ofis xodimi", "frequent": True,
    },
    {
        "title": "Printer chiqarmayapti, qog'oz tiqilyapti, toner tugagan", "owner": TECH,
        "rule": "Texnik printerni tekshiradi, toner yoki qog'ozni almashtiradi.",
        "examples": ["printer ishlamayapti", "printer chiqarmayapti", "принтер не печатает"],
        "asker": "Ofis xodimi", "frequent": True,
    },
    {
        "title": "1C yoki PRBC ga dostup ochish", "owner": IT,
        "fallbacks": [(OPS, "Server tomonda foydalanuvchi yaratish kerak bo'lsa")],
        "rule": "Rahbar xodim lavozimini va kerakli huquqlarni yozadi; IT administrator foydalanuvchini ochadi.",
        "examples": ["1C ga kirish kerak", "PRBC dostup", "доступ в 1С"],
        "asker": "Ofis xodimi", "frequent": True,
    },
    {
        "title": "Shubhali xat yoki havola", "owner": TECH,
        "fallbacks": [(IT, "Xat ochilgan yoki parol kiritilgan bo'lsa — akkauntni himoyalaydi")],
        "rule": "Havolani bosmang, xatni o'chirmang — Texnikka yuboring. Agar havola bosilgan yoki parol kiritilgan bo'lsa — "
                "darhol IT administratorga, parol almashtiriladi.",
        "examples": ["shubhali xat keldi", "noma'lum havola", "подозрительное письмо"],
        "asker": "Hamma", "frequent": False,
    },
]


# Xodimlar: kim qaysi holatda javob beradi (daraja, aniq vazifalar, nimaga murojaat qilinmaydi, kimga o'tkazadi)
MEMBERS = [
    {
        "name": "Saidabror", "role": "Ma'lumotlar operatori", "level": "L1", "manager": None,
        "trigger": "Dasturdagi ma'lumotni kiritish, o'zgartirish, o'chirish yoki chiqarib berish kerak",
        "does": "1C va ProTarget'dagi savdo ma'lumotlarini yuritadi: supervayzer tasdiqlagan o'zgarishlarni bajaradi.",
        "duties": [
            "Klient, savdo nuqtasi va agent profilidagi ma'lumotni kiritadi va tuzatadi (1C, ProTarget)",
            "Buyurtmani o'chiradi, tovar va miqdorni o'zgartiradi",
            "Mavjud aksiya va chegirmani klientga biriktiradi yoki olib tashlaydi",
            "Dublikat klientlarni birlashtiradi, yopilgan nuqtalarni ro'yxatdan chiqaradi",
            "Kerakli ma'lumotni dasturdan chiqarib beradi (ro'yxat, eksport)",
            "Supervayzer tasdiqlagan so'rovlarni bajaradi",
        ],
        "excludes": "Login, parol va dostup (Xusniddin); yangi aksiya yaratish, hisoblash va integratsiya xatosi (Dasturchilar); "
                    "qurilma va tarmoq (Jahongir).",
        "escalation": "Dastur ishlamasa — Xusniddin; aksiya hisoblanmasa yoki 1C ga o'tmasa — Dasturchilar jamoasi; "
                      "ProTarget dasturining o'zida xato — Pro-target.",
        "authorities": [("Ma'lumotni o'zgartirish va o'chirish", "Faqat supervayzer tasdiqlagan so'rov bo'yicha")],
    },
    {
        "name": "Xusniddin", "role": "IT operator (L1)", "level": "L1", "manager": "Abdulbosit Tuychiev",
        "trigger": "Kira olmayapman, dostup kerak yoki dastur ishlamayapti",
        "does": "Birinchi yordam (L1): dostuplar to'g'ri ishlashini va dasturlar uzilishsiz ishlashini ta'minlaydi, "
                "muammo bo'lsa kerakli xodimga xabar beradi.",
        "duties": [
            "Dostup ochadi, o'zgartiradi va yopadi: ProTarget, 1C, PRBC, pochta",
            "Login, parol va bloklangan akkaunt muammolarini hal qiladi",
            "Dasturlar (ProTarget, 1C, 1C bot, mobil ilova) to'g'ri ishlayotganini kuzatadi",
            "Uzilish bo'lsa birinchi bo'lib aniqlaydi va kerakli mutaxassisga xabar beradi",
            "Agent telefoni almashganda akkauntni yangi qurilmaga ko'chiradi",
            "Murojaatni birinchi qabul qiladi, hal qilmasa — to'g'ri odamga yo'naltiradi",
        ],
        "excludes": "Klient, buyurtma, aksiya va marshrut ma'lumotini o'zgartirish (Operator); kabel, printer va qurilma (Jahongir); "
                    "dasturiy o'zgarish (Dasturchilar).",
        "escalation": "Server yoki tizimli uzilish — Abdulbosit Tuychiev; dastur xatosi — Dasturchilar jamoasi yoki Pro-target; "
                      "qurilma va tarmoq — Jahongir.",
        "authorities": [("Login, parol va huquqlarni berish", "ProTarget, 1C, PRBC, email"),
                        ("Akkaunt va dostupni bloklash", "Yo'qolgan telefon, ishdan ketgan xodim")],
    },
    {
        "name": "Abdulbosit Tuychiev", "role": "DevOps", "level": "LEAD", "manager": None,
        "trigger": "Server, aloqa kanallari yoki dasturlarda tizimli uzilish; IT ishlari kechiksa",
        "does": "Infratuzilma uzluksiz ishlashi uchun javob beradi; Xusniddin va Jahongir ishlari bajarilishini nazorat qiladi, "
                "ish ko'p bo'lganda ularga yordam beradi.",
        "duties": [
            "Serverlar, ma'lumotlar bazasi va aloqa kanallari uzluksiz ishlashini ta'minlaydi",
            "Tizimli uzilishlarni bartaraf etadi, zaxira nusxa va tiklashni yuritadi",
            "Xusniddin va Jahongir ishlari o'z vaqtida bajarilishini nazorat qiladi",
            "Ish ko'p bo'lganda yoki murakkab holatda ularga yordam beradi",
            "L1 hal qila olmagan murakkab muammolarni hal qiladi",
        ],
        "excludes": "Kundalik ma'lumot kiritish (Operator) va oddiy parol tiklash — avval Xusniddin'ga.",
        "escalation": "Dasturiy o'zgarish yoki integratsiya kodi kerak bo'lsa — Dasturchilar jamoasi.",
        "authorities": [("IT ishlari bajarilishini nazorat qilish", "Xusniddin, Jahongir"),
                        ("Server va infratuzilmaga o'zgartirish kiritish", "Serverlar, tarmoq kanallari, zaxira")],
    },
    {
        "name": "Jahongir", "role": "IT texnik yordam", "level": "L1", "manager": "Abdulbosit Tuychiev",
        "trigger": "Ofisdagi texnik ish: qurilma, kabel, tarmoq, printer",
        "does": "Ofisda bajariladigan barcha texnik ishlar uchun mas'ul: qurilmalar, tarmoq qurish va kabel tortish.",
        "duties": [
            "Kompyuter, monitor, printer, skaner, IP-telefon va kameralarni sozlaydi va ta'mirlaydi",
            "Tarmoq quradi, kabel tortadi, Wi-Fi va LAN rozetkalarini o'rnatadi",
            "Yangi xodimga ish joyi, yangi agentga telefon tayyorlaydi",
            "Internet, VPN va filial tarmog'idagi muammolarni hal qiladi",
            "Texnika inventarini yuritadi, yo'qolgan yoki buzilganini almashtiradi",
        ],
        "excludes": "Dostup, parol va akkaunt (Xusniddin); dasturdagi ma'lumot (Operator); dastur xatosi (Dasturchilar).",
        "escalation": "Server yoki butun tarmoq ishlamasa — Abdulbosit Tuychiev.",
        "authorities": [("Qurilma berish va ish joyini tayyorlash", "Kompyuter, printer, telefon, tarmoq")],
    },
    {
        "name": "Pro-target", "role": "ProTarget operatori va support", "level": "EXT", "manager": None, "capacity": 20,
        "trigger": "ProTarget ma'lumotlari yoki ProTarget dasturidagi muammo",
        "does": "ProTarget tomonidan biriktirilgan alohida operator: dasturdagi ma'lumotlar bilan ishlaydi va dastur muammolari "
                "bo'yicha yordam beradi.",
        "duties": [
            "Klientlarni tasdiqlaydi",
            "Aksiyalar va ularga bog'liq ma'lumotlarni ProTarget'da yuritadi",
            "Mobil ilova va ProTarget dasturidagi xatolar bo'yicha yordam beradi",
            "Yangilanishdan keyin chiqqan xatolarni tuzatadi",
            "1C bilan almashinuvning ProTarget tomonini tekshiradi",
        ],
        "excludes": "1C, PRBC va Telegram bot bilan bog'liq ishlarda murojaat qilinmaydi.",
        "escalation": "Muammo 1C yoki integratsiya kodida bo'lsa — Dasturchilar jamoasi.",
        "authorities": [("Klientni tasdiqlash", "ProTarget")],
    },
    {
        "name": "Dasturchilar jamoasi", "role": "Dasturchilar", "level": "L3", "manager": None, "capacity": 80,
        "trigger": "Yangi aksiya, dastur o'zgarishi, hisoblash yoki integratsiya xatosi",
        "does": "Dasturlar, integratsiya va hisobotlarni ishlab chiqadi va tuzatadi.",
        "duties": [
            "Yangi aksiya yaratadi va uning qoidalarini sozlaydi",
            "1C, ProTarget va PRBC o'rtasidagi integratsiya xatolarini tuzatadi",
            "1C bot va hisobotlardagi xatolarni tuzatadi, yangi ko'rsatkich qo'shadi",
            "Yangi funksiya takliflarini baholaydi va ishlab chiqadi",
        ],
        "excludes": "Kundalik ma'lumot kiritish (Operator); dostup va parol (Xusniddin); qurilma va tarmoq (Jahongir).",
        "escalation": "Server resurslari yoki infratuzilma kerak bo'lsa — Abdulbosit Tuychiev.",
    },
    {
        "name": "Supervayzerlar", "role": "Savdo supervayzeri", "level": "BIZ", "manager": None, "capacity": 120,
        "trigger": "Agentning klienti, marshruti, plani yoki ma'lumotini o'zgartirish so'rovi",
        "does": "Agentlar ishini nazorat qiladi va ma'lumotni o'zgartirish so'rovlarini tasdiqlaydi.",
        "duties": [
            "Agentning birinchi murojaat nuqtasi: savolni qabul qiladi",
            "Klientni agentga ulaydi va tashrif marshrutiga qo'shadi",
            "Tashrif kunlari va planni kiritadi",
            "Ma'lumotni o'zgartirish so'rovini tasdiqlab Operatorga beradi",
        ],
        "excludes": "Ma'lumotni 1C da o'zi o'zgartirmaydi — tasdiqlangan so'rovni Operator bajaradi.",
        "escalation": "Ma'lumot o'zgarishi — Saidabror; dastur ishlamasa — Xusniddin.",
    },
]


def apply_members(log=print):
    from .models import Authority
    by_name = {m.name: m for m in Member.objects.all()}
    done = 0
    for spec in MEMBERS:
        m = by_name.get(spec["name"])
        if not m:
            log(f"  topilmadi — xodim: {spec['name']}")
            continue
        for f in ("role", "level", "trigger", "does", "duties", "excludes", "escalation"):
            setattr(m, f, spec[f])
        if "capacity" in spec and m.capacity == 40:  # faqat standart qiymat bo'lsa (qo'lda o'zgartirilganiga tegmaydi)
            m.capacity = spec["capacity"]
        if spec.get("manager") in by_name:
            m.manager = by_name[spec["manager"]]
        m.save()
        for order, (title, scope) in enumerate(spec.get("authorities", [])):
            Authority.objects.update_or_create(member=m, title=title, defaults={"scope": scope, "order": order})
        done += 1
    log(f"Xodim profillari: {done}")
    return done


def _find_process(old, new):
    return Process.objects.filter(name=new).first() or Process.objects.filter(name=old).first()


@transaction.atomic
def apply(dry_run=False, log=print):
    stats = {"zones": 0, "processes": 0, "questions": 0, "missing": []}
    zones = {}
    for order, (key, name, icon, color, desc) in enumerate(ZONES):
        z, created = Zone.objects.update_or_create(key=key, defaults={"name": name, "icon": icon, "color": color,
                                                                      "description": desc, "order": order})
        zones[key] = z
        stats["zones"] += 1
    for old, zkey, new, desc in PROCESSES:
        p = _find_process(old, new)
        if not p:
            stats["missing"].append(f"jarayon: {old}")
            continue
        p.zone, p.name = zones[zkey], new
        if desc:
            p.description = desc
        p.save()
        stats["processes"] += 1
    for p in Process.objects.filter(zone__isnull=True).select_related("system"):
        p.zone = zones[guess_zone(p)]
        p.save(update_fields=["zone"])
        stats["processes"] += 1
    members = {m.name: m for m in Member.objects.all()}
    for q in QUESTIONS:
        old, new = (q["title"], q["title"]) if isinstance(q["title"], str) else q["title"]
        t = Task.objects.filter(title=new).first() or Task.objects.filter(title=old).first()
        if not t:
            stats["missing"].append(f"savol: {old}")
            continue
        t.title, t.rule, t.examples = new, q["rule"], q["examples"]
        t.asker, t.frequent = q.get("asker", ""), q.get("frequent", False)
        if q.get("owner") in members:
            t.owner = members[q["owner"]]
        t.save()
        if "fallbacks" in q:
            chain = [(members[n], cond) for n, cond in q["fallbacks"] if n in members and members[n] != t.owner]
            t.fallbacks.all().delete()
            for order, (m, cond) in enumerate(chain):
                TaskFallback.objects.create(task=t, member=m, condition=cond, order=order)
        stats["questions"] += 1
    # qolgan savollar: kim so'rashi zonadan
    for t in Task.objects.filter(asker="").select_related("process__zone"):
        zone = t.process.zone.key if t.process and t.process.zone else None
        if zone in ASKER:
            Task.objects.filter(pk=t.pk).update(asker=ASKER[zone])
    stats["members"] = apply_members(log)
    from . import timeload
    stats["estimated"] = timeload.apply_estimates()
    log(f"Vaqt taxmini qo'yildi: {stats['estimated']} ta savol (qo'lda kiritilganlarga tegilmadi)")
    log(f"Zonalar: {stats['zones']}, jarayonlar: {stats['processes']}, qoidali savollar: {stats['questions']}")
    for m in stats["missing"]:
        log(f"  topilmadi — {m}")
    if dry_run:
        transaction.set_rollback(True)
        log("Sinov rejimi: o'zgarishlar saqlanmadi.")
    return stats
