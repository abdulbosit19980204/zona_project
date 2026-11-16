"""Savollar katalogidan (savollar-katalogi.md) bazada yo'q savollarni qo'shish.

- Mazmunan yangi savollar — tegishli jarayonga (kerak bo'lsa yangi jarayon ochiladi), mas'ul va navbati bilan.
- Bazada bor savollarning boshqacha ifodasi — o'sha savolga "qanday so'raladi" misoli sifatida qo'shiladi
  (bot va qidiruv shu iboralar bilan ham topadi).
- Chegaraviy holatlar — navbat shartlari, aniq qoida va "aralash holatlar" (EdgeCase) sifatida.
Qayta ishga tushirish xavfsiz: sarlavha bo'yicha topiladi, bor bo'lsa takrorlanmaydi.
Ishga tushirish: python manage.py zona_knowledge  (knowledge_seed.apply ichida chaqiriladi)
"""
from django.db import transaction

from .models import EdgeCase, Member, Process, ProcessRole, Task, TaskFallback, Zone

SV, OP, IT, DEV, TECH, PT, OPS = ("Supervayzerlar", "Saidabror", "Xusniddin", "Dasturchilar jamoasi", "Jahongir",
                                  "Pro-target", "Abdulbosit Tuychiev")

# Yangi jarayonlar: nomi -> (zona, egasi, tavsif)
NEW_PROCESSES = {
    "Hujjatlar: vozvrat, to'lov va tuzatish": ("distributsiya", OP,
                                               "Zakaz, vozvrat va to'lov hujjatlaridagi xatolarni tuzatish, sanasi va holatini o'zgartirish."),
    "Ma'lumot chiqarib berish (vygruzka)": ("hisobot", OP,
                                            "Klientlar, zakazlar, savdo, qarzdorlik va aksiya bo'yicha ro'yxatlarni Excelga chiqarib berish."),
    "Nomenklatura (tovar kartochkasi)": ("1c", OP, "Yangi tovar, nomi, shtrix-kod, o'lchov birligi, guruh va narx turi."),
    "Uzilishlar: kuzatish va xabar berish": ("infra", IT,
                                             "Dastur ishlamay qolganda ko'lamini aniqlash, kerakli mutaxassisga yetkazish va holat haqida xabar berish."),
    "Aloqa kanallari": ("infra", OPS, "Filiallar bilan aloqa, provayder, zaxira kanal, router, tashqi IP va portlar."),
    "Nazorat va eskalatsiya": ("infra", OPS, "L1 hal qila olmagan murojaatlar, SLA, takrorlanuvchi muammolar va ish taqsimoti."),
    "ProTarget: klient tasdiqlash": ("protarget", PT, "ProTarget tomonda klientni tasdiqlash, rad etish sabablari va hujjatlar."),
    "ProTarget: aksiyalar": ("protarget", PT, "ProTarget tomonidagi aksiya shartlari, qatnashchilar, bonus va natijalar."),
    "Boshqa integratsiyalar (bot, EDO, bank)": ("integratsiya", DEV, "1C bilan bot, elektron faktura (EDO) va bank almashinuvi."),
    "Agentning birinchi murojaati": ("distributsiya", SV,
                                     "Agent savolini supervayzer qabul qiladi, birlamchi tekshiradi va to'g'ri mutaxassisga yo'naltiradi."),
    "Tasdiqlash so'rovlari": ("distributsiya", SV, "O'zgarish bajarilishidan oldin supervayzer tasdiqlaydigan so'rovlar."),
    "Biznes savollari": ("distributsiya", SV, "Plan, KPI, bonus, aksiya qoidalari va klient bilan nizolar."),
}

# Yangi savollar: (jarayon nomi, sarlavha, egasi, [(navbatdagi, qachon)], kim so'raydi, doimiy, qoida, misollar)
Q = []


def q(process, title, owner, fallbacks=(), asker="", frequent=False, rule="", examples=()):
    Q.append({"process": process, "title": title, "owner": owner, "fallbacks": list(fallbacks), "asker": asker,
              "frequent": frequent, "rule": rule, "examples": list(examples)})


# ---------------------------------------------------------------- 1. Saidabror — ma'lumotlar operatori
KB = "Klient bazasi: yaratish va ma'lumotlar"
q(KB, "Klientning telefon raqamini yoki kontakt shaxsini (egasi, sotuvchi) o'zgartirish", OP, [(SV, "O'zgarishni tasdiqlaydi")], "Agent",
  examples=["Klient telefon raqamini yangilang", "Kontakt shaxsni (egasi, sotuvchi) o'zgartiring"])
q(KB, "Klient kanali yoki kategoriyasi noto'g'ri (do'kon, supermarket, HoReCa)", OP, [(SV, "To'g'ri kanalni tasdiqlaydi")], "Agent",
  examples=["Klient kanali yoki kategoriyasi noto'g'ri"])
q(KB, "Klientning narx turini o'zgartirish", OP, [(SV, "Yangi narx turini tasdiqlaydi")], "Supervayzer",
  rule="Supervayzer tasdiqlaydi; Operator 1C va ProTarget'da klient narx turini o'zgartiradi. Yangi narx keyingi zakazdan amal qiladi.",
  examples=["Klientning narx turini o'zgartiring", "klient boshqa narxda olishi kerak"])
q(KB, "Klientni boshqa filialga o'tkazish", OP, [(SV, "Ikkala filial supervayzerlari kelishadi")], "Supervayzer",
  examples=["Klientni boshqa filialga o'tkazing"])
q(KB, "Klient kartochkasiga hujjat yoki rasm biriktirish", OP, asker="Agent",
  examples=["Klient kartochkasiga hujjat yoki rasm biriktiring", "guvohnoma rasmini qo'shib qo'ying"])

DOC = "Hujjatlar: vozvrat, to'lov va tuzatish"
q(DOC, "Zakaz ikki marta tushib qolgan (dublikat zakaz)", OP, [(SV, "Qaysi zakaz qolishini tasdiqlaydi")], "Agent", True,
  rule="Agent ikkala zakaz raqamini yuboradi; supervayzer tasdiqlaydi; Operator ortiqchasini o'chiradi. "
       "Zakaz o'z-o'zidan ikki marta ketayotgan bo'lsa — Dasturchilar.",
  examples=["Zakaz ikki marta tushib qoldi", "bitta zakaz ikki marta ketibdi"])
q(DOC, "Zakaz boshqa klientga yozilib ketgan", OP, [(SV, "Tuzatishni tasdiqlaydi")], "Agent", True,
  rule="Operator zakazni to'g'ri klientga o'tkazadi (yoki o'chirib qayta kiritadi), qarz va to'lovlarni tekshiradi.",
  examples=["Zakaz boshqa klientga yozilib ketdi"])
q(DOC, "Zakazdagi narx noto'g'ri chiqqan", OP, [(DEV, "Narx turi to'g'ri, lekin narx noto'g'ri hisoblansa")], "Agent", True,
  rule="Operator klient narx turi va tovar narxini tekshiradi, zakazni tuzatadi. Ma'lumot to'g'ri bo'lsa-yu narx xato chiqsa — Dasturchilar.",
  examples=["Zakazdagi narx noto'g'ri", "zakazda narx boshqacha chiqdi"])
q(DOC, "Vozvrat (qaytarish) hujjatini kiritish", OP, [(SV, "Vozvratni tasdiqlaydi")], "Agent", True,
  rule="Agent vozvrat sababi va tovarlarni yuboradi; supervayzer tasdiqlaydi; Operator vozvrat hujjatini 1C da kiritadi.",
  examples=["Vozvrat (qaytarish) hujjatini kiriting", "tovar qaytdi, vozvrat qilish kerak"])
q(DOC, "Vozvrat noto'g'ri kiritilgan — tuzatish", OP, [(SV, "Tuzatishni tasdiqlaydi")], "Agent",
  examples=["Vozvrat noto'g'ri kiritilgan, tuzating"])
q(DOC, "Hujjat sanasini o'zgartirish", OP, [(SV, "Sana o'zgarishini tasdiqlaydi")], "Agent",
  examples=["Hujjat sanasini o'zgartiring"])
q(DOC, "To'lov boshqa klientga tushib qolgan", OP, [(SV, "To'g'ri klientni tasdiqlaydi")], "Agent", True,
  rule="Operator to'lovni to'g'ri klientga o'tkazadi va ikkala klientning qarzdorligini tekshiradi.",
  examples=["To'lov boshqa klientga tushib qolgan", "pul boshqa magazinga yozilibdi"])
q(DOC, "To'lov ikki marta tushgan", OP, [(SV, "Qaysi to'lov qolishini tasdiqlaydi")], "Agent",
  examples=["To'lov ikki marta tushgan"])
q(DOC, "To'lov summasi noto'g'ri kiritilgan", OP, [(SV, "To'g'ri summani tasdiqlaydi")], "Agent",
  examples=["To'lov summasi noto'g'ri kiritilgan"])
q(DOC, "Hujjatni o'tkazilmagan holatga qaytarish (provodkani bekor qilish)", OP, [(SV, "Tasdiqlaydi")], "Operator",
  examples=["Hujjatni o'tkazilmagan holatga qaytaring"])
q(DOC, "Hujjatni boshqa agent nomiga o'tkazish", OP, [(SV, "Tasdiqlaydi")], "Supervayzer",
  examples=["Hujjatni boshqa agent nomiga o'tkazing"])

AK = "Aksiya va chegirmani klientga qo'llash"
q(AK, "Klientlar ro'yxatini (Excel) aksiyaga ommaviy biriktirish", OP, [(SV, "Ro'yxatni tasdiqlaydi")], "Supervayzer",
  rule="Supervayzer klientlar ro'yxatini (Excel: kod yoki STIR) yuboradi; Operator ularni aksiyaga biriktiradi va natijani qaytaradi.",
  examples=["Klientlar ro'yxatini (Excel) aksiyaga biriktiring"])

DUP = "Dublikat klientdagi zakaz va qarzni asosiy kartochkaga o'tkazish"
q(KB, DUP, OP, [(SV, "Asosiy kartochkani tasdiqlaydi")], "Operator",
  examples=["Dublikat klientdagi zakaz va qarzni asosiy kartochkaga o'tkazing"])

VYG = "Ma'lumot chiqarib berish (vygruzka)"
for title, ex in [
    ("Agent bo'yicha klientlar ro'yxatini chiqarib berish", "Agent bo'yicha klientlar ro'yxati kerak"),
    ("Filial bo'yicha klientlar ro'yxatini chiqarib berish", "Filial bo'yicha klientlar ro'yxati kerak"),
    ("Oylik savdoni Excelga chiqarib berish", "Shu oydagi savdoni Excelga chiqarib bering"),
    ("Zakazlar ro'yxatini chiqarib berish (davr, agent yoki klient bo'yicha)", "Zakazlar ro'yxati kerak"),
    ("Debitorlik (qarzdorlik) ro'yxatini chiqarib berish", "Debitorlik (qarzdorlik) ro'yxati kerak"),
    ("Klient bilan akt sverka tayyorlash", "Klient bilan akt sverka kerak"),
    ("Aksiya bo'yicha sotuv hajmini chiqarib berish", "Aksiya bo'yicha qancha sotilganini chiqarib bering"),
    ("Aksiyaga biriktirilgan klientlar ro'yxatini chiqarib berish", "Aksiya qaysi klientlarga biriktirilganini ro'yxat qilib bering"),
    ("Nofaol (zakaz bermayotgan) klientlar ro'yxatini chiqarib berish", "Nofaol klientlar ro'yxati"),
    ("Vozvratlar ro'yxatini chiqarib berish", "Vozvratlar ro'yxati kerak"),
    ("Yangi ochilgan klientlar ro'yxatini chiqarib berish (davr bo'yicha)", "Yangi ochilgan klientlar ro'yxati"),
    ("Lokatsiyasi yoki STIR raqami yo'q klientlar ro'yxatini chiqarib berish", "Lokatsiyasi yo'q klientlar ro'yxati"),
    ("Dublikat klientlar ro'yxatini chiqarib berish", "Dublikatlar ro'yxatini chiqarib bering"),
]:
    q(VYG, title, OP, [(DEV, "Bunday hisobot tizimda umuman bo'lmasa — yangi hisobot")], "Supervayzer", examples=[ex])

NOM = "Nomenklatura (tovar kartochkasi)"
q(NOM, "Yangi tovar (SKU) qo'shish", OP, [(DEV, "Tovar 1C da bor, ProTarget'ga o'tmasa — integratsiya")], "Operator", True,
  rule="Operator tovarni 1C da yaratadi: nomi, shtrix-kod, o'lchov birligi, karobkadagi soni, guruh/brend va narx turlari. "
       "Keyingi almashinuvda ProTarget'ga o'tadi.",
  examples=["Yangi tovar (SKU) qo'shing", "yangi mahsulot keldi, bazaga kiriting"])
q(NOM, "Tovar shtrix-kodini qo'shish yoki o'zgartirish", OP, asker="Operator", examples=["Shtrix-kodini qo'shing yoki o'zgartiring"])
q(NOM, "O'lchov birligi yoki karobkadagi dona soni noto'g'ri", OP, asker="Agent",
  examples=["O'lchov birligi noto'g'ri (dona, blok, karobka)", "Karobkadagi dona sonini tuzating"])
q(NOM, "Tovarni nofaol qilish", OP, asker="Operator", examples=["Tovarni nofaol qiling"])
q(NOM, "Tovarni guruh yoki brendga biriktirish", OP, asker="Operator", examples=["Tovarni guruhga yoki brendga biriktiring"])
q(NOM, "Tovarga narx turi biriktirish", OP, asker="Operator", examples=["Tovarga narx turi biriktiring"])
q(NOM, "Tovar (nomenklatura) dublikat bo'lib qolgan", OP, [(DEV, "Dublikat integratsiya sababli paydo bo'lsa")], "Operator",
  examples=["Tovar (nomenklatura) dublikat bo'lib qolgan"])

# ---------------------------------------------------------------- 2. Xusniddin — IT operator
q("Korporativ pochta", "Yangi xodimga korporativ pochta ochish", IT, [(TECH, "Pochta telefonda sozlanishi kerak bo'lsa")], "Ofis xodimi",
  rule="Rahbar yangi xodim ma'lumotini yuboradi; IT operator pochta qutisini ochadi va kirish ma'lumotini xodimga beradi.",
  examples=["Korporativ pochta oching"])
q("1C va PRBC: dostup", "1C da yangi filial yoki omborga huquq qo'shish", IT, [(SV, "Rahbar tasdiqlaydi")], "Ofis xodimi",
  examples=["Menga yangi filial yoki omborga huquq qo'shing"])
q("1C va PRBC: dostup", "Kompyuterga 1C ni (yorliq yoki baza) qo'shib berish", IT, [(TECH, "1C klient dasturi o'rnatilmagan bo'lsa")], "Ofis xodimi",
  examples=["1C klientni (ярлык / baza) qo'shib bering"])
q("Dostupni o'zgartirish va yopish", "Foydalanuvchi rolini o'zgartirish (masalan, agent → supervayzer)", IT, [(SV, "Rahbar tasdiqlaydi")], "Supervayzer",
  examples=["Rolimni o'zgartiring (masalan, agent → supervayzer)"])
q("Dostupni o'zgartirish va yopish", "Ortiqcha huquqlarni olib tashlash", IT, [(OPS, "Huquqlarni tekshirish (audit) kerak bo'lsa")], "Ofis xodimi",
  examples=["Ortiqcha huquqlarni olib tashlang"])
q("Dostup ochish", "Vaqtincha dostup berish (o'rinbosar uchun)", IT, [(SV, "Rahbar muddat va huquqlarni tasdiqlaydi")], "Supervayzer",
  rule="Rahbar o'rinbosar ismini, kerakli tizimlar va muddatni yozadi; IT operator vaqtincha dostup ochadi va muddat tugaganda yopadi.",
  examples=["Vaqtincha dostup bering (o'rinbosar uchun)"])
q("VPN va masofaviy kirish", "RDP orqali masofaviy kirish kerak", IT, [(TECH, "VPN yoki tarmoq sozlamasi kerak bo'lsa")], "Ofis xodimi",
  examples=["RDP orqali kirish kerak"])
q("Kirish muammolari", "SMS yoki 2FA kod kelmayapti", IT, [(OPS, "Kod yuborish xizmati butunlay ishlamasa")], "Agent",
  examples=["SMS yoki 2FA kod kelmayapti", "tasdiqlash kodi kelmadi"])
q("1C bot: kirish va huquq", "Telegram botga qayta ulanish", IT, asker="Agent", examples=["Telegram botga qayta ulanish kerak"])
q("1C bot: kirish va huquq", "Botni boshqa telefon raqamiga bog'lash", IT, asker="Agent", examples=["Botni boshqa telefon raqamiga bog'lash kerak"])
q("1C dasturi", "1C ochilmayapti", IT,
  [(TECH, "Faqat bitta kompyuterda va sabab kompyuterning o'zida bo'lsa"), (OPS, "Hammada ochilmasa — server muammosi")], "Ofis xodimi", True,
  rule="1) IT operator muammo bitta xodimdami yoki hammadami — aniqlaydi.\n"
       "2) Bitta xodimda, login/parol — o'zi hal qiladi.\n3) Bitta xodimda, kompyuter muammosi — Jahongir.\n"
       "4) Hammada — Abdulbositga xabar beradi va foydalanuvchilarga holatni yetkazadi.",
  examples=["1C ochilmayapti", "1C ga kira olmayapman"])
q("1C dasturi", "PRBC ochilmayapti", IT, [(OPS, "Hammada ochilmasa — server muammosi")], "Ofis xodimi",
  examples=["PRBC ochilmayapti"])
UZ = "Uzilishlar: kuzatish va xabar berish"
q(UZ, "Muammo hammadami yoki faqat bir xodimdami — ko'lamini aniqlash", IT, [(OPS, "Hammada bo'lsa — tizimli uzilish")], "Hamma", True,
  rule="IT operator boshqa xodimlarda ham tekshiradi. Bitta xodimda bo'lsa — o'zi hal qiladi yoki Jahongir'ga beradi; "
       "hammada bo'lsa — Abdulbositga xabar beradi va guruhga uzilish haqida yozadi.",
  examples=["Hammada ishlamayaptimi yoki faqat mendami?", "faqat menda ishlamayaptimi"])
q(UZ, "Uzilish qachon tuzaladi — holat haqida xabar berish", IT, [(OPS, "Tuzatish muddatini aytadi")], "Hamma",
  examples=["Qachon tuzaladi?"])
q(UZ, "Muammo kimga yetkazildi va holati qanday", IT, asker="Hamma", examples=["Muammo kimga yetkazildi, holati qanday?"])
q(UZ, "Uzilish tugagani haqida hammaga xabar berish", IT, asker="Hamma", examples=["Uzilish tugadi, hammaga xabar berish"])
q("Mobil ilova xatolari", "Ilovani yangi versiyaga yangilash (\"eski versiya\" deb kirgizmayapti)", IT, asker="Agent", frequent=True,
  rule="IT operator agentga yangi versiya havolasini yuboradi yoki telefonda yangilab beradi; yangilangach qayta kiriladi.",
  examples=["Ilovani yangi versiyaga yangilang", "Ilova eski versiya deb kirgizmayapti"])

# ---------------------------------------------------------------- 3. Abdulbosit — DevOps, nazorat
SRV = "Serverlar"
q(SRV, "Server juda sekin — hamma qotib qoldi", OPS, asker="Hamma", frequent=False,
  examples=["Server juda sekin, hamma qotib qoldi"])
q(SRV, "1C litsenziyasi tugadi yoki yetmayapti", OPS, asker="Ofis xodimi", examples=["1C litsenziyasi tugadi yoki yetmayapti"])
q(SRV, "Server qayta yuklandi, xizmatlar ko'tarilmadi", OPS, asker="Hamma", examples=["Server qayta yuklandi, xizmatlar ko'tarilmadi"])
q(SRV, "Yangi server yoki virtual mashina kerak", OPS, asker="Ofis xodimi", examples=["Yangi server yoki virtual mashina kerak"])
q(SRV, "Dasturchilar uchun test baza kerak", OPS, asker="Ofis xodimi", examples=["Test baza kerak (dasturchilar uchun)"])
KAN = "Aloqa kanallari"
q(KAN, "Filial bilan aloqa yo'q (VPN uzildi)", OPS, [(TECH, "Filialdagi qurilmani joyida tekshirish kerak bo'lsa")], "Hamma",
  examples=["Filial bilan aloqa yo'q (VPN uzildi)"])
q(KAN, "Provayder internetni uzdi", OPS, [(TECH, "Ofis ichidagi tarmoqni tekshiradi")], "Hamma", examples=["Provayder internetni uzdi"])
q(KAN, "Asosiy kanal ishlamayapti — zaxira kanalga o'tkazish", OPS, asker="Hamma",
  examples=["Asosiy kanal ishlamayapti, zaxira kanalga o'tkazish"])
q(KAN, "Router yoki Mikrotik ishlamayapti", OPS, [(TECH, "Qurilmani joyida qayta yoqish kerak bo'lsa")], "Ofis xodimi",
  examples=["Router yoki Mikrotik muammosi", "mikrotik ishlamayapti", "router ishlamayapti", "mikrotik o'chib qoldi"])
q(KAN, "Integratsiya uchun tashqi IP yoki port ochish", OPS, asker="Ofis xodimi",
  examples=["Tashqi IP yoki port ochish kerak (integratsiya uchun)"])
XAV = "Axborot xavfsizligi"
q(XAV, "Virus yoki shifrlovchi (ransomware) gumoni", OPS, [(TECH, "Kompyuterni tarmoqdan uzib tekshiradi")], "Hamma",
  rule="Darhol kompyuterni tarmoqdan uzing va hech narsani o'chirmang. Jahongir kompyuterni ajratadi; Abdulbosit serverlar va "
       "zaxira nusxalarni tekshiradi, kerak bo'lsa tiklaydi.",
  examples=["Virus yoki shifrlovchi (ransomware) gumoni", "fayllar shifrlanib qoldi"])
q(XAV, "Parol siyosatini o'zgartirish", OPS, asker="Ofis xodimi", examples=["Parol siyosatini o'zgartirish"])
q(XAV, "Ruxsatsiz ma'lumot chiqarilgan bo'lishi mumkin", OPS, asker="Hamma",
  examples=["Kimdir ruxsatsiz ma'lumot chiqargan bo'lishi mumkin"])
q(XAV, "Ishdan ketgan xodimning dostuplari to'liq yopilganini tekshirish", OPS, [(IT, "Yopilmagan dostupni yopadi")], "Ofis xodimi",
  examples=["Ishdan ketgan xodim dostupi to'liq yopilganini tekshirish"])
NAZ = "Nazorat va eskalatsiya"
q(NAZ, "L1 (Xusniddin yoki Jahongir) hal qila olmagan murojaat", OPS, [(DEV, "Muammo dasturiy bo'lsa")], "Hamma",
  rule="L1 xodim nima qilinganini yozib Abdulbositga beradi; Abdulbosit hal qiladi yoki Dasturchilarga yo'naltiradi.",
  examples=["Xusniddin yoki Jahongir hal qila olmadi"])
q(NAZ, "Murojaat muddati (SLA) o'tib ketdi", OPS, asker="Hamma", examples=["Murojaat muddati (SLA) o'tib ketdi"])
q(NAZ, "Bir xil muammo takrorlanyapti", OPS, [(DEV, "Sabab dasturda bo'lsa — doimiy tuzatish")], "Hamma",
  examples=["Bir xil muammo takrorlanyapti"])
q(NAZ, "Ish ko'p — L1 xodimlarga yordam kerak", OPS, asker="Ofis xodimi", examples=["Ish ko'p, yordam kerak"])
q(NAZ, "Murojaatlar statistikasi yoki hisoboti", OPS, asker="Ofis xodimi", examples=["Murojaatlar statistikasi yoki hisoboti kerak"])
q(NAZ, "L1 xodimlar o'rtasida ishni taqsimlash", OPS, asker="Ofis xodimi", examples=["L1 xodimlar o'rtasida ishni taqsimlash"])
q(NAZ, "Muhim uzilish bo'yicha rahbariyatga hisobot", OPS, asker="Ofis xodimi", examples=["Muhim uzilish bo'yicha rahbariyatga hisobot"])

# ---------------------------------------------------------------- 4. Jahongir — IT texnik yordam
KOMP = "Kompyuter va ish joyi"
q(KOMP, "Kompyuterda ovoz yoki mikrofon ishlamayapti", TECH, asker="Ofis xodimi",
  examples=["Kompyuterda ovoz yoki mikrofon ishlamayapti"])
q(KOMP, "Fayllarni eski kompyuterdan yangisiga ko'chirish", TECH, asker="Ofis xodimi",
  examples=["Fayllarni eski kompyuterdan yangisiga ko'chiring"])
q("Internet va tarmoq", "Switch yoki router o'chib qolgan (ofis ichida)", TECH, [(OPS, "Butun ofis yoki filial aloqasiz qolsa")], "Ofis xodimi",
  examples=["Switch yoki router o'chib qolgan"])
OF = "Ofis va filial"
q(OF, "UPS (uzluksiz quvvat manbai) ishlamayapti", TECH, asker="Ofis xodimi", examples=["UPS (uzluksiz quvvat manbai) ishlamayapti"])
q(OF, "Majlis xonasini tayyorlash (proyektor, televizor, ovoz, internet)", TECH, asker="Ofis xodimi",
  examples=["Majlis xonasini tayyorlang (proyektor, ovoz, internet)", "Proyektor yoki televizorni ulang"])
q(OF, "Ishdan ketgan xodimdan qurilmalarni qaytarib olish", TECH, [(IT, "Dostuplarini yopadi")], "Ofis xodimi",
  examples=["Ishdan ketgan xodimdan qurilmalarni qaytarib oling"])
q(KOMP, "Yangi xodim keldi — ish joyi, qurilma va dostuplar", TECH, [(IT, "Dasturlarga dostup — supervayzer yoki rahbar tasdiqlagandan keyin")],
  "Ofis xodimi", True,
  rule="Jahongir ish joyi va qurilmani (kompyuter, telefon) tayyorlaydi. Xusniddin dasturlarga (1C, ProTarget, PRBC, pochta) "
       "dostup ochadi — supervayzer yoki rahbar tasdiqlagandan keyin.",
  examples=["Yangi xodim keldi", "yangi xodimni ishga tayyorlash"])

# ---------------------------------------------------------------- 5. Pro-target — tashqi hamkor
PTK = "ProTarget: klient tasdiqlash"
q(PTK, "Yangi klient qachon tasdiqlanadi?", PT, [(OP, "Klient ma'lumotlari 1C da noto'g'ri bo'lsa")], "Agent", True,
  rule="Pro-target operatori klient holatini tekshirib, tasdiqlash muddatini aytadi yoki yetishmayotgan ma'lumotni so'raydi.",
  examples=["Yangi klient qachon tasdiqlanadi?", "klientim hali tasdiqlanmadi"])
q(PTK, "Klient nega rad etildi?", PT, [(OP, "Rekvizitlarni tuzatish kerak bo'lsa")], "Agent", examples=["Klient nega rad etildi?"])
q(PTK, "Klient hujjatlari yetishmayapti", PT, asker="Agent", examples=["Klient hujjatlari yetishmayapti"])
q(PTK, "Klient ma'lumotlari ProTargetda noto'g'ri", PT, [(OP, "Xato 1C dan kelgan bo'lsa")], "Agent",
  examples=["Klient ma'lumotlari ProTargetda noto'g'ri"])
q(PTK, "Tasdiqlangan klientlar ro'yxati", PT, asker="Supervayzer", examples=["Tasdiqlangan klient ro'yxati kerak"])
PTA = "ProTarget: aksiyalar"
q(PTA, "Aksiya shartlari qanday?", PT, [(SV, "Agentlarga tushuntiradi")], "Agent", True, examples=["Aksiya shartlari qanday?"])
q(PTA, "Qaysi klientlar aksiyada qatnashadi?", PT, [(OP, "1C dagi biriktirish ro'yxati kerak bo'lsa")], "Supervayzer",
  examples=["Qaysi klientlar aksiyada qatnashadi?"])
q(PTA, "Bonus yoki sovg'a qachon beriladi?", PT, asker="Agent", examples=["Bonus yoki sovg'a qachon beriladi?"])
q(PTA, "Aksiya ProTarget tomonda ishlamadi", PT, [(DEV, "Sabab 1C yoki integratsiyada bo'lsa")], "Agent",
  examples=["Aksiya ProTarget tomonda ishlamadi"])
q(PTA, "Aksiya natijalari (ProTarget hisobi bo'yicha)", PT, asker="Supervayzer", examples=["Aksiya natijalari (ProTarget hisobi bo'yicha)"])

# ---------------------------------------------------------------- 6. Dasturchilar — L3
q("Aksiya va chegirma ishlamayapti", "Aksiya bo'yicha bonus noto'g'ri hisoblandi", DEV, [(OP, "Avval biriktirish to'g'riligini tekshiradi")],
  "Supervayzer", examples=["Aksiya bo'yicha bonus noto'g'ri hisoblandi"])
INT = "Boshqa integratsiyalar (bot, EDO, bank)"
q(INT, "1C ↔ bot almashinuvi ishlamayapti", DEV, [(IT, "Bot umuman javob bermasa — avval uzilishni tekshiradi")], "Operator",
  examples=["1C ↔ bot almashinuvi ishlamayapti"])
q(INT, "EDO yoki soliq (elektron faktura) integratsiyasi xatosi", DEV, asker="Operator",
  examples=["EDO yoki soliq (elektron faktura) integratsiyasi xatosi"])
q(INT, "Bank bilan almashinuv xatosi", DEV, asker="Operator", examples=["Bank bilan almashinuv xatosi"])
q(INT, "Yangi tizim bilan integratsiya qilish so'rovi", DEV, [(OPS, "Server, IP yoki port kerak bo'lsa")], "Ofis xodimi",
  examples=["Yangi tizim bilan integratsiya qilish so'rovi"])
BOT = "1C bot ishlamayapti"
q(BOT, "Bot noto'g'ri ma'lumot ko'rsatyapti yoki buyruqqa xato javob beryapti", DEV, [(OP, "Ma'lumotning o'zi 1C da xato bo'lsa")], "Agent",
  examples=["Bot noto'g'ri ma'lumot ko'rsatyapti", "Bot buyruqqa xato javob beryapti"])
q(BOT, "Bot bildirishnomasi kelmayapti", DEV, [(IT, "Faqat bitta xodimda bo'lsa — ulanishni tekshiradi")], "Agent",
  examples=["Bot xabarnomasi (bildirishnoma) kelmayapti"])
HIS = "Hisobotlar"
q(HIS, "Yangi hisobot yaratish", DEV, asker="Supervayzer", examples=["Yangi hisobot yaratish"])
q(HIS, "Hisobot juda sekin shakllanyapti", DEV, [(OPS, "Server resurslari yetmasa")], "Supervayzer",
  examples=["Hisobot juda sekin shakllanyapti"])
q("1C dasturi", "1C da hammada xato oynasi chiqyapti", DEV, [(IT, "Avval ko'lamini aniqlaydi va xabar beradi")], "Hamma",
  examples=["1C da xato oynasi chiqyapti (barcha uchun)"])
q("PRBC almashinuvi", "PRBC funksiyasi noto'g'ri ishlayapti", DEV, [(IT, "Avval dostup va ulanishni tekshiradi")], "Ofis xodimi",
  examples=["PRBC funksiyasi noto'g'ri ishlayapti"])

# ---------------------------------------------------------------- 7. Supervayzerlar — biznes
BM = "Agentning birinchi murojaati"
q(BM, "Agentda zakaz o'tmayapti yoki ketmayapti — birlamchi tekshiruv", SV,
  [(IT, "Login yoki dostup muammosi"), (OP, "Klient yoki tovar ma'lumoti xato"),
   (DEV, "Ilova crash yoki sinxronizatsiya xatosi"), (OPS, "Server yoki aloqa muammosi")], "Agent", True,
  rule="Supervayzer xato matnini so'raydi va yo'naltiradi:\n- login/dostup → Xusniddin\n- klient yoki tovar ma'lumoti xato → Saidabror\n"
       "- ilova crash yoki sinxronizatsiya xatosi → Dasturchilar\n- server yoki aloqa → Abdulbosit",
  examples=["Zakaz o'tmayapti", "Agentda zakaz ketmayapti", "zakaz yuborilmayapti", "agentda zakaz ketmayapti nima qilay",
            "заказ не уходит у агента"])
q(BM, "Agentda aksiya ko'rinmayapti yoki chiqmayapti", SV,
  [(OP, "Klient aksiyaga biriktirilmagan"), (DEV, "Biriktirilgan, lekin ishlamayapti"), (PT, "Muammo ProTarget tomonda")], "Agent", True,
  rule="1) Klient aksiyaga biriktirilmagan bo'lsa → Saidabror biriktiradi.\n2) Biriktirilgan, lekin ishlamayapti → Dasturchilar.\n"
       "3) Muammo ProTarget tomonda → Pro-target.",
  examples=["Aksiya ko'rinmayapti", "aksiya chiqmayapti", "agentda aksiya ko'rinmayapti", "aksiya korinmayapti", "акция не видна",
            "Klient aksiyada yo'q, agentda ko'rinmayapti"])
q(BM, "Agentda narx noto'g'ri chiqyapti", SV, [(OP, "Klient narx turi yoki tovar narxi noto'g'ri"), (DEV, "Ma'lumot to'g'ri, narx noto'g'ri hisoblanadi")],
  "Agent", True, examples=["Narx noto'g'ri chiqyapti"])
q(BM, "Agentda ilova ishlamayapti", SV, [(IT, "Texnik muammo — IT operator")], "Agent", True, examples=["Ilova ishlamayapti"])
q(BM, "Qaysi xodimga murojaat qilish kerak?", SV, asker="Agent", frequent=True,
  rule="Supervayzer savolni \"Savol kimga?\" yoki Telegram bot orqali tekshiradi va agentga mas'ul xodim va uning kontaktini beradi.",
  examples=["Qaysi xodimga murojaat qilish kerak?", "bu savol bilan kimga boray"])
TS = "Tasdiqlash so'rovlari"
for title, then, ex in [
    ("Yangi klient ochishni tasdiqlash", OP, "Yangi klient ochishni tasdiqlash"),
    ("Klientni boshqa agentga o'tkazishni tasdiqlash", None, "Klientni boshqa agentga o'tkazishni tasdiqlash"),
    ("Klientni aksiyaga qo'shishni tasdiqlash", OP, "Klientni aksiyaga qo'shishni tasdiqlash"),
    ("Vozvratni tasdiqlash", OP, "Vozvratni tasdiqlash"),
    ("Chegirma yoki maxsus narxni tasdiqlash", OP, "Chegirma yoki maxsus narxni tasdiqlash"),
    ("Zakazni o'chirish yoki tahrirlashni tasdiqlash", OP, "Zakazni o'chirish yoki tahrirlashni tasdiqlash"),
    ("Marshrutni o'zgartirishni tasdiqlash", None, "Marshrutni o'zgartirishni tasdiqlash"),
    ("Yangi agentga dostup ochishni tasdiqlash", IT, "Yangi agentga dostup ochishni tasdiqlash"),
    ("Agent dostupini yopishni tasdiqlash", IT, "Agent dostupini yopishni tasdiqlash"),
    ("Kredit limiti yoki to'lov muddatini tasdiqlash", OP, "Kredit limiti yoki to'lov muddatini tasdiqlash"),
]:
    q(TS, title, SV, [(then, "Tasdiqlangandan keyin bajaradi")] if then else [], "Agent", examples=[ex])
BZ = "Biznes savollari"
q(BZ, "Plan va bajarilish holati", SV, asker="Agent", frequent=True, examples=["Plan va bajarilish holati"])
q(BZ, "Aksiya qoidalarini agentlarga tushuntirish", SV, [(PT, "ProTarget aksiyasi shartlari bo'yicha")], "Agent",
  examples=["Aksiya qoidalari agentlarga tushuntirish"])
q(BZ, "KPI va bonus hisob-kitobi", SV, asker="Agent", examples=["KPI va bonus hisob-kitobi"])
q(BZ, "Klient bilan nizoli holat", SV, asker="Agent", examples=["Klient bilan nizoli holatlar"])

# Bazada bor savollarning katalogdagi boshqacha ifodasi -> misol sifatida qo'shiladi
EXAMPLES = {
    "Yangi klient qo'shish": ["Yangi klient qo'shib bering (nomi, STIR, manzil, telefon, kontakt)"],
    "Klient nomi, manzili, STIR yoki identifikatsiya ma'lumoti noto'g'ri": [
        "Klientning STIR raqami noto'g'ri, o'zgartiring", "Klient nomi noto'g'ri yozilgan", "Klient manzili o'zgardi"],
    "Xaritadagi joylashuv yoki GPS koordinatasi noto'g'ri kiritilgan": ["Klient lokatsiyasi xaritada noto'g'ri turibdi"],
    "Klientni boshqa agentga o'tkazish yoki vaqtincha biriktirish": ["Klientni boshqa agentga o'tkazing"],
    "Tashrif kunini o'zgartirish, shanba yoki bayram kunini olib tashlash": ["Klientni haftaning boshqa kuniga qo'ying"],
    "Marshrutga nuqta qo'shish yoki olib tashlash": ["Klientni boshqa marshrutga qo'ying"],
    "Klientni faollashtirish, yopish, ro'yxatdan chiqarish": ["Klient yopildi, nofaol qilib qo'ying", "Nofaol klientni qayta faollashtiring"],
    "Buyurtmani o'chirish": ["Zakazni o'chirib bering"],
    "Buyurtmaga tovar qo'shish, almashtirish yoki o'chirish": ["Zakazni noto'g'ri kiritdim, tahrirlang", "Zakazga tovar qo'shing yoki olib tashlang"],
    "Tovar miqdorini o'zgartirish": ["Zakazdagi tovar soni noto'g'ri"],
    "Klientga aksiya qo'shish yoki olib tashlash": [
        "Shu klientni aksiyaga qo'shing", "Klientni aksiyadan chiqaring", "Klientni boshqa aksiyaga o'tkazing"],
    "Muddati tugagan aksiya klientda qolgan": ["Aksiya muddati tugagan klientlarni tozalang"],
    "Dublikat klient (\"bunday klient mavjud\", ikki marta yaratilgan)": [
        "Bitta klient ikki marta ochilgan, birlashtiring", "Bitta STIR bilan ikkita kartochka bor", "Bitta telefon raqam bilan bir nechta klient bor"],
    "Tovar narxi, nomi yoki rasmi noto'g'ri": ["Tovar nomini o'zgartiring"],
    "1C yoki PRBC ga dostup ochish": ["Yangi xodim keldi, 1C ga dostup oching", "PRBC ga dostup oching"],
    "Botga kirish": ["Telegram botga dostup oching"],
    "Yangi agent yoki supervayzerga ProTarget dostupi va huquqlari": ["Agentga mobil ilovaga login bering"],
    "Hisobotga kirish huquqi kerak": ["Hisobotni ko'rishga huquq bering"],
    "Masofaviy xodimga VPN sozlash": ["VPN kerak"],
    "Umumiy papka va fayl serverga kirish huquqi": ["Umumiy papkaga (tarmoq diskiga) dostup bering"],
    "Ishdan ketgan agent dostupini yopish": ["Xodim ishdan ketdi, barcha dostuplarni yoping", "Agentlar almashdi, eski loginni yoping"],
    "Dostupni vaqtincha to'xtatish": ["Ta'tilga chiqdi, vaqtincha bloklang"],
    "Yo'qolgan telefondagi akkauntni bloklash": ["Agent telefonini yo'qotdi, akkauntni bloklang"],
    "Boshqa hududga o'tgan agentning eski hudud dostupini olib tashlash": ["Xodim boshqa bo'limga o'tdi, eski huquqlarni yoping"],
    "Parolni tiklash": ["Parolni unutdim", "Parol muddati tugadi", "Parolni almashtirib bering", "ProTarget login yoki paroli"],
    "Akkaunt bloklangan": ["Akkaunt bloklanib qoldi"],
    "\"Ruxsat yo'q\" yoki \"foydalanuvchi topilmadi\" xabari": ["Ilova \"login xato\" deyapti"],
    "Korporativ pochtaga kira olmayapman": ["Pochta paroli ishlamayapti"],
    "Email yubormayapti yoki qabul qilmayapti": ["Pochta kelmayapti yoki ketmayapti"],
    "1C sekin ishlayapti": ["1C juda sekin ishlayapti"],
    "Bot javob bermayapti yoki xabar yuborildi, natija qaytmadi": ["Bot javob bermayapti"],
    "Sinxronlash tugamayapti yoki xato beryapti": ["Agentda sinxronizatsiya bo'lmayapti, zakazlar ketmayapti"],
    "Yangi telefonda ilovani qayta sozlash": ["Mobil ilovani o'rnatib bering"],
    "Eski telefondan yangisiga akkauntni ko'chirish": ["Yangi telefonga ilovani ko'chirish kerak"],
    "Ilova ochilmayapti, oq ekran, o'z-o'zidan yopilyapti": ["ProTarget ilovasi ochilmayapti", "Mobil ilova yopilib qolyapti (crash)"],
    "Ma'lumotlar yangilanmayapti": ["ProTarget ilovasida ma'lumot ko'rinmayapti"],
    "Server ishlamayapti yoki javob bermayapti": ["Bot serveri ishlamayapti", "PRBC serveri ishlamayapti"],
    "1C, ProTarget yoki PRBC serveriga hamma foydalanuvchida ulanish yo'q": ["1C server ishlamayapti (hamma uchun)"],
    "Server disk va resurslari": ["Disk to'lib qoldi"],
    "Zaxira nusxa va tiklash": ["Backup olinmadi yoki backup tekshiruvi", "Bazani backupdan tiklash kerak"],
    "Ma'lumotlar bazasiga ulanish xatosi (infratuzilma)": ["SQL server muammosi"],
    "SSL sertifikat": ["Domen yoki SSL sertifikat muddati tugadi"],
    "Pochta serverida uzilish": ["Pochta serveri muammosi"],
    "Yangi filialni korporativ tarmoqqa ulash": ["Yangi filialni tarmoqqa ulash"],
    "Ruxsatsiz kirish urinishi": ["Shubhali kirishlar bor"],
    "Kompyuter yoqilmayapti, sekin, qizib ketmoqda yoki qayta yuklanmoqda": [
        "Kompyuter yoqilmayapti", "Kompyuter juda sekin", "Kompyuter o'zi o'chib qolyapti"],
    "Windows xatosi": ["Windows ochilmayapti yoki xato beryapti"],
    "Dastur o'rnatish, litsenziya, antivirus va virus ogohlantirishi": [
        "Dastur o'rnatib bering (Office, 1C klient, brauzer, arxivator)", "Virus bor shekilli"],
    "Yangi xodimga ish joyi tayyorlash": ["Yangi kompyuterni sozlab bering", "Yangi xodim uchun ish joyi tayyorlang"],
    "Printer chiqarmayapti, qog'oz tiqilyapti, toner tugagan": ["Printer chop etmayapti", "Kartrij tugadi, almashtiring", "Qog'oz tiqilib qoldi"],
    "Printer tarmoqda ko'rinmayapti; drayver": ["Printer drayverini o'rnating", "Printerni tarmoqqa ulang"],
    "Skaner hujjat yubormayapti": ["Skaner ishlamayapti"],
    "Shtrix-kod yoki etiketka printeri": ["Yorliq (termo) printer ishlamayapti"],
    "Chek printer": ["Chek printer ishlamayapti"],
    "Internet yo'q, sekin yoki uzilib qolyapti": ["Bir xonada internet yo'q", "Internet yo'q", "butun ofisda internet yo'q",
                                                 "internet umuman ishlamayapti", "нет интернета"],
    "Wi-Fi ulanmayapti, signal past": ["Wi-Fi ishlamayapti yoki signal past"],
    "Yangi LAN port": ["Yangi kabel tortish kerak", "Yangi ish joyiga tarmoq olib borish"],
    "LAN kabel va rozetka": ["Tarmoq rozetkasi ishlamayapti"],
    "Monitor, klaviatura, sichqoncha, USB ishlamayapti": ["Monitor ishlamayapti", "Klaviatura yoki sichqoncha buzildi"],
    "IP-telefon": ["IP telefon ishlamayapti"],
    "Videokuzatuv kamerasi": ["Kamera (CCTV) ko'rsatmayapti"],
    "Barcode skaner savdo jarayonida ishlamayapti": ["Planshet yoki TSD skaner ishlamayapti"],
    "Qurilmani ta'mirlash va almashtirish": ["Qurilmani ta'mirga topshirish"],
    "Texnikani boshqa xonaga yoki xodimga ko'chirish": ["Xodim boshqa xonaga ko'chdi"],
    "Texnika inventari, yo'qolgan yoki shikastlangan texnika": ["Qurilmalar ro'yxati (inventarizatsiya) kerak"],
    "Yangi aksiya yaratish va tizimga qo'shish": ["Yangi aksiya mexanikasini tizimga sozlash", "Yangi aksiya kerak",
                                                  "yangi aksiya qo'shish kerak", "новая акция"],
    "Aksiya shartlari, muddati va qoidalarini o'zgartirish": ["Aksiya shartini o'zgartirish (foiz, chegara, muddat)"],
    "Aksiya klientga qo'shilgan, lekin buyurtmada ishlamayapti": ["Aksiya biriktirilgan, lekin hisoblanmayapti"],
    "Almashinuv to'xtab qolgan yoki kechikmoqda": ["1C ↔ ProTarget ma'lumot almashinuvi to'xtadi"],
    "Bir tizimda tuzatilgan ma'lumot ikkinchisiga o'tmayapti": ["1C ↔ PRBC integratsiyasi xatosi"],
    "Botga yangi funksiya qo'shish": ["Botga yangi funksiya qo'shish"],
    "Hisobotdagi son tizim xatosi sabab mos kelmayapti": ["Hisobotda summa noto'g'ri chiqyapti (ma'lumot to'g'ri bo'lsa)"],
    "Hisobot ochilmayapti yoki yuklanmayapti": ["Hisobot ochilmayapti yoki xato beryapti"],
    "Hisobotga yangi ustun yoki ko'rsatkich qo'shish": ["Hisobotga yangi ustun yoki filtr qo'shish"],
    "Dastur yoki ilovaga yangi funksiya taklifi": ["Yangi funksiya yoki o'zgartirish so'rovi"],
    "Klient bazada bor, lekin agentda ko'rinmayapti": ["Klient ko'rinmayapti"],
    "Klient uchun maxsus narx so'rovi (tasdiq bilan)": ["maxsus narx kerak"],
    "Plan, tashrif soni yoki plan bajarilishining noto'g'ri hisoblanishi": ["plan noto'g'ri hisoblangan"],
}

# Chegaraviy holatlar: bazadagi savolga aniq qoida va navbat shartlari
EDGE_RULES = {
    "Bot javob bermayapti yoki xabar yuborildi, natija qaytmadi": (
        IT, [(OPS, "Bot serveri ishlamasa"), (DEV, "Bot ishlayapti, lekin noto'g'ri javob bersa")],
        "1) Xusniddin uzilish holatini tekshiradi (hammadami yoki bitta xodimda).\n2) Server ishlamasa — Abdulbosit.\n"
        "3) Bot ishlayapti, lekin noto'g'ri javob beradi — Dasturchilar."),
    "Internet yo'q, sekin yoki uzilib qolyapti": (
        TECH, [(OPS, "Butun ofis yoki filial internetsiz qolsa")],
        "Bitta xona yoki kompyuterda — Jahongir. Butun ofis yoki filial internetsiz bo'lsa — Abdulbosit (provayder, kanal)."),
    "Hisobotdagi son tizim xatosi sabab mos kelmayapti": (
        DEV, [(OP, "Avval ma'lumot to'g'ri kiritilganini tekshiradi")],
        "Ma'lumot noto'g'ri kiritilgan bo'lsa — Saidabror tuzatadi. Ma'lumot to'g'ri, hisob-kitob xato bo'lsa — Dasturchilar."),
}
EDGE_CASES = [
    ("Aksiya ko'rinmayapti", OP, "Biriktirilmagan bo'lsa — Saidabror; biriktirilgan, lekin ishlamasa — Dasturchilar; ProTarget tomonda — Pro-target"),
    ("1C ochilmayapti", IT, "Bitta xodimda, kompyuter muammosi — Jahongir; hammada — Xusniddin xabar beradi, Abdulbosit tuzatadi"),
    ("Hisobotda summa noto'g'ri", OP, "Ma'lumot to'g'ri, hisob-kitob xato bo'lsa — Dasturchilar"),
    ("Bot javob bermayapti", IT, "Server ishlamasa — Abdulbosit; bot ishlab, noto'g'ri javob bersa — Dasturchilar"),
    ("Agentda zakaz ketmayapti", SV, "Login — Xusniddin; klient/tovar ma'lumoti — Saidabror; crash yoki sinxronizatsiya — Dasturchilar; "
                                     "server yoki aloqa — Abdulbosit"),
    ("Internet yo'q", TECH, "Butun ofis yoki filial internetsiz bo'lsa — Abdulbosit"),
    ("Yangi xodim keldi", TECH, "Dasturlarga dostup — Xusniddin (supervayzer yoki rahbar tasdiqlagandan keyin)"),
]


RENAMES = {
    "Agentda zakaz o'tmayapti — birlamchi tekshiruv": "Agentda zakaz o'tmayapti yoki ketmayapti — birlamchi tekshiruv",
    "Agentda aksiya ko'rinmayapti": "Agentda aksiya ko'rinmayapti yoki chiqmayapti",
    "Router yoki Mikrotik muammosi": "Router yoki Mikrotik ishlamayapti",
}


@transaction.atomic
def apply(log=print):
    members = {m.name: m for m in Member.objects.all()}
    zones = {z.key: z for z in Zone.objects.all()}
    procs = {p.name: p for p in Process.objects.all()}
    stats = {"processes": 0, "questions": 0, "examples": 0, "edge": 0, "skipped": []}

    for name, (zkey, owner, desc) in NEW_PROCESSES.items():
        p = procs.get(name)
        if not p:
            last = Process.objects.order_by("-order").values_list("order", flat=True).first() or 0
            p = Process.objects.create(name=name, zone=zones.get(zkey), description=desc, order=last + 1)
            procs[name] = p
            stats["processes"] += 1
        if owner in members and not ProcessRole.objects.filter(process=p, role="owner").exists():
            ProcessRole.objects.create(process=p, member=members[owner], role="owner")

    for old, new in RENAMES.items():
        if not Task.objects.filter(title=new).exists():
            Task.objects.filter(title=old, is_custom=True).update(title=new)
    by_title = {sp["title"]: sp for sp in Q}
    for t in Task.objects.filter(title__in=list(by_title)):  # misollarni yangilash (qo'lda qo'shilganlari saqlanadi)
        extra = [e for e in by_title[t.title]["examples"] if e not in (t.examples or [])]
        if extra:
            Task.objects.filter(pk=t.pk).update(examples=(list(t.examples or []) + extra)[:30])
    existing = {t.title for t in Task.objects.only("title")}
    for spec in Q:
        if spec["title"] in existing:
            continue
        p = procs.get(spec["process"])
        if not p:
            stats["skipped"].append(f"{spec['title']} (jarayon topilmadi: {spec['process']})")
            continue
        owner = members.get(spec["owner"])
        last = Task.objects.filter(process=p).order_by("-order").values_list("order", flat=True).first() or 0
        t = Task.objects.create(title=spec["title"], process=p, owner=owner, rule=spec["rule"], examples=spec["examples"],
                                asker=spec["asker"], frequent=spec["frequent"], is_custom=True, order=last + 1)
        chain = [(members[n], c) for n, c in spec["fallbacks"] if n in members and members[n] != owner]
        for i, (m, cond) in enumerate(chain):
            TaskFallback.objects.create(task=t, member=m, condition=cond, order=i)
        # navbatdagi xodim jarayonda ishtirokchi sifatida ko'rinsin
        for m, _ in chain:
            ProcessRole.objects.get_or_create(process=p, member=m, role="contributor")
        existing.add(spec["title"])
        stats["questions"] += 1

    MISPLACED = {"Klientga aksiya qo'shish yoki olib tashlash": ["Klient aksiyada yo'q, agentda ko'rinmayapti"]}
    for title, bad in MISPLACED.items():
        for t in Task.objects.filter(title=title):
            keep = [e for e in (t.examples or []) if e not in bad]
            if keep != list(t.examples or []):
                Task.objects.filter(pk=t.pk).update(examples=keep)
    for title, phrases in EXAMPLES.items():
        t = Task.objects.filter(title=title).first()
        if not t:
            stats["skipped"].append(f"misol: {title}")
            continue
        cur = list(t.examples or [])
        add = [p for p in phrases if p not in cur and p != t.title]
        if add:
            Task.objects.filter(pk=t.pk).update(examples=(cur + add)[:30])
            stats["examples"] += len(add)

    for title, (owner, chain, rule) in EDGE_RULES.items():
        t = Task.objects.filter(title=title).first()
        if not t:
            stats["skipped"].append(f"qoida: {title}")
            continue
        if not t.rule:
            t.rule = rule
        if owner in members:
            t.owner = members[owner]
        t.save()
        have = set(t.fallbacks.values_list("member__name", flat=True))
        order = t.fallbacks.count()
        for n, cond in chain:
            if n in members and n not in have and members[n] != t.owner:
                TaskFallback.objects.create(task=t, member=members[n], condition=cond, order=order)
                order += 1
            elif n in have:
                t.fallbacks.filter(member__name=n, condition="").update(condition=cond)

    for situation, owner, then in EDGE_CASES:
        if not EdgeCase.objects.filter(situation=situation).exists():
            last = EdgeCase.objects.order_by("-order").values_list("order", flat=True).first() or 0
            EdgeCase.objects.create(situation=situation, first_owner=members.get(owner), then_text=then, order=last + 1)
            stats["edge"] += 1

    log(f"Katalog: yangi jarayon {stats['processes']}, yangi savol {stats['questions']}, "
        f"qo'shilgan misol {stats['examples']}, aralash holat {stats['edge']}")
    for s in stats["skipped"]:
        log(f"  o'tkazib yuborildi — {s}")
    return stats
