"""Namuna ma'lumot (StarGroup IT): bo'limlar, xodimlar, jarayonlar va vazifalar.

`python manage.py zona_seed` shu fayldan bazani to'ldiradi.
Vazifa = agent yoki supervayzer bergan savol turi; jarayon = vazifalar yo'nalishi.
"""

DEPARTMENTS = [
    ("sales", "Savdo", "Agentlar va supervayzerlar: savol shu yerdan keladi"),
    ("ops", "Savdo operatsiyalari", "Savdo ma'lumotlarini yuritish"),
    ("it", "IT xizmati", "Dostup, qurilma, tarmoq va serverlar"),
    ("dev", "Dasturlash", "Dasturiy o'zgarishlar va integratsiya"),
]

# Jamoalar: (kalit, bo'lim kaliti, nomi, tavsif, rahbar xodim kaliti)
TEAMS = [
    ("field", "sales", "Dala nazorati", "Agentlar ishini kuzatish va so'rovlarni tasdiqlash", "supervisors"),
    ("data", "ops", "Ma'lumotlar operatorlari", "Klient, buyurtma, narx va marshrut ma'lumotlari", "operator"),
    ("access", "it", "Dostup va ilovalar", "Akkauntlar, huquqlar, ilova va pochta muammolari", "it_admin"),
    ("infra", "it", "Infratuzilma", "Qurilmalar, tarmoq, serverlar, ofis", "sysadmin"),
    ("core", "dev", "Platforma va integratsiya", "Aksiyalar, hisob-kitob, 1C va ProTarget integratsiyasi", "dev"),
]

# xodim kaliti -> jamoa kaliti
MEMBER_TEAM = {"supervisors": "field", "operator": "data", "it_admin": "access", "sysadmin": "infra", "dev": "core"}

# xodim kaliti -> bo'lim kaliti
MEMBER_DEPARTMENT = {
    "operator": "ops",
    "it_admin": "it",
    "sysadmin": "it",
    "dev": "dev",
    "supervisors": "sales",
}

SYSTEMS = [
    "ProTarget", "1C", "1C bot", "Integratsiya", "Mobil ilova", "Hisobot", "Pochta",
    "Xavfsizlik", "Qurilma", "Tarmoq", "Server", "Ofis", "Umumiy",
]

# Vazifa olmaydigan, lekin jarayonda rol bajaradigan xodimlar.
EXTRA_MEMBERS = [
    {
        "key": "supervisors",
        "name": "Supervayzerlar",
        "role": "Savdo supervayzeri",
        "is_team": True,
        "does": "Agentlar ishini nazorat qiladi; ma'lumotni o'zgartirish so'rovini tasdiqlaydi.",
        "excludes": "Ma'lumotni o'zi kiritmaydi: tasdiqlangan so'rovni Operator bajaradi.",
    },
]

# Vakolatlar: (xodim kaliti, vakolat, doirasi). Faqat mavjud tavsiflardan olingan.
AUTHORITIES = [
    ("supervisors", "Ma'lumotni o'zgartirish so'rovini tasdiqlash", "Operator faqat tasdiqlangan so'rovni bajaradi"),
    ("it_admin", "Akkaunt va dostupni bloklash", "Yo'qolgan telefon, ishdan ketgan xodim"),
    ("it_admin", "Login, parol va huquqlarni berish", "ProTarget, 1C, PRBC, email"),
    ("dev", "Yangi aksiya va uning qoidalarini yaratish", "Operator faqat mavjud aksiyani klientga qo'shadi"),
    ("sysadmin", "Qurilma berish va ish joyini tayyorlash", "Kompyuter, printer, telefon, tarmoq"),
]

# Jarayon rollari: (xodim kaliti, rol, qaysi xodim jarayonlariga).
# "Ma'lumotni o'zgartirish so'rovini Supervayzer tasdiqlaydi, Operator bajaradi."
PROCESS_ROLES = [
    ("supervisors", "approver", "operator"),
]

MEMBERS = [
    {
        "key": "operator",
        "name": "Saidabror",
        "role": "Operator",
        "is_team": False,
        "does": (
            "Savdoga ta'sir qiladigan ma'lumotni kiritadi, o'zgartiradi, o'chiradi: klient, "
            "savdo nuqtasi, buyurtma, tovar, narx, klientga aksiya qo'shish, marshrut va "
            "tashrif kuni, agent profili."
        ),
        "excludes": (
            "Login, parol, dostup va ilovaning texnik xatosi (Xusniddin); yangi aksiya yaratish, "
            "hisoblash xatosi, integratsiya va 1C dastur xatosi (dasturchilar); "
            "qurilma, internet, server (Jahongir)."
        ),
    },
    {
        "key": "it_admin",
        "name": "Xusniddin",
        "role": "IT administrator",
        "is_team": False,
        "does": (
            "Dostup va akkauntlar: login, parol, bloklanish, huquqlar (ProTarget, 1C, PRBC, email); "
            "ilova va pochtadagi texnik muammolar; yo'qolgan telefondagi akkauntni bloklash."
        ),
        "excludes": (
            "Klient, buyurtma, aksiya, marshrut, profil ma'lumotini o'zgartirish (Operator); "
            "yangi aksiya, yangi funksiya, integratsiya va bot xatolari (dasturchilar); "
            "qurilma, internet, VPN (Jahongir)."
        ),
    },
    {
        "key": "dev",
        "name": "Dasturchilar jamoasi",
        "role": "Dasturchilar",
        "is_team": True,
        "does": (
            "Aksiya yaratish va uning qoidalari; dasturiy o'zgarishlar va yangi funksiya; "
            "hisobotga yangi ustun; 1C va ProTarget o'rtasidagi integratsiya, bot va hisoblash xatolari."
        ),
        "excludes": (
            "Kundalik ma'lumot kiritish va tuzatish (Operator); dostup va parol (Xusniddin); "
            "qurilma, internet va server (Jahongir)."
        ),
    },
    {
        "key": "sysadmin",
        "name": "Jahongir",
        "role": "Texnik / Sysadmin",
        "is_team": False,
        "does": (
            "Jismoniy ishlar: kompyuter, monitor, printer, skaner, telefon, yangi ish joyi; "
            "internet, Wi-Fi, LAN, VPN; serverlar; ofisdagi texnik muammolar."
        ),
        "excludes": (
            "Dostup, parol va akkaunt (Xusniddin); ma'lumot o'zgartirish (Operator); "
            "aksiya, integratsiya, bot va dastur xatolari (dasturchilar)."
        ),
    },
]

# member_key -> [(yo'nalish, tizim, [vazifalar])]
TASKS = {
    "operator": [
        ("ProTarget: klient", "ProTarget", [
            "Yangi klient qo'shish",
            "Klient nomi, manzili, STIR yoki identifikatsiya ma'lumoti noto'g'ri",
            "Dublikat klient (\"bunday klient mavjud\", ikki marta yaratilgan)",
            "Klient tasdiqlanmayapti yoki tasdiqlash so'rovi kelmagan",
            "Klientni faollashtirish, yopish, ro'yxatdan chiqarish",
            "Klient kartochkasidagi ma'lumot yangilanmagan",
        ]),
        ("ProTarget: klientga ulanish", "ProTarget", [
            "Klientga ulanish (podklyucheniya) qilish",
            "Klient agent ro'yxatidan yo'qolgan yoki tashrif ro'yxatida chiqmayapti",
            "Klientni boshqa agentga o'tkazish yoki vaqtincha biriktirish",
            "Klientni bir nechta agentga ko'rinadigan qilish",
            "Ulanishni bekor qilish yoki qayta ulash",
        ]),
        ("ProTarget: savdo nuqtalari va hudud", "ProTarget", [
            "Savdo nuqtasi (torgoviy tochka) almashib qolgan yoki noto'g'ri biriktirilgan",
            "Yangi nuqtani biriktirish yoki olib tashlash",
            "Yopilgan nuqta hali ro'yxatda",
            "Nuqta nomi yoki manzili noto'g'ri",
            "Xaritadagi joylashuv yoki GPS koordinatasi noto'g'ri kiritilgan",
            "Yangi hudud qo'shish",
            "Agent boshqa hudud nuqtalarini ko'ryapti",
        ]),
        ("ProTarget: marshrut, plan, tashrif", "ProTarget", [
            "Yangi marshrut qo'shish",
            "Marshrutga nuqta qo'shish yoki olib tashlash",
            "Tashrif kunini o'zgartirish, shanba yoki bayram kunini olib tashlash",
            "Haftalik jadval noto'g'ri tuzilgan",
            "Marshrutlar agentlar o'rtasida almashib qolgan",
            "Plan ko'rsatkichini kiritish yoki to'g'rilash",
        ]),
        ("ProTarget: agent profili", "ProTarget", [
            "Ism-familiya, telefon, lavozim, bo'lim, filial, savdo guruhini o'zgartirish",
            "Agentni boshqa supervayzerga biriktirish",
            "Hududni to'g'rilash",
            "Ishga kirgan sana va faol holatni to'g'rilash",
            "Ishdan ketgan agent profilini nofaol qilish",
            "Qayta ishga qabul qilingan agent profilini tiklash",
            "Bir xil ismli ikki profil",
            "Noto'g'ri o'zgarishni qaytarish",
        ]),
        ("ProTarget: aksiya va chegirma", "ProTarget", [
            "Klientga aksiya qo'shish yoki olib tashlash",
            "Klientga skidka yoqish",
            "Klientga noto'g'ri chegirma biriktirilgan",
            "Chegirma foizi yoki limiti klientda noto'g'ri",
            "Muddati tugagan aksiya klientda qolgan",
            "Klient uchun maxsus narx so'rovi (tasdiq bilan)",
        ]),
        ("ProTarget: buyurtma va tovar", "ProTarget", [
            "Buyurtmani o'chirish",
            "Buyurtmaga tovar qo'shish, almashtirish yoki o'chirish",
            "Tovar miqdorini o'zgartirish",
            "Buyurtmani bekor qilish yoki qaytarish",
            "Kerakli tovar ro'yxatda chiqmayapti",
            "Tovar narxi, nomi yoki rasmi noto'g'ri",
            "Buyurtma summasi 1C dagi summadan farq qiladi",
        ]),
        ("1C: ma'lumot", "1C", [
            "1C da ma'lumot kiritish yoki tahrirlash",
            "1C dagi hujjat yoki ma'lumotni o'chirish",
            "Noto'g'ri kiritilgan ma'lumotni tuzatish",
            "1C dagi klient kartochkasi ProTarget bilan mos kelmayapti (avval ma'lumotni to'g'rilaydi)",
        ]),
        ("1C bot: klient qo'shish", "1C bot", [
            "Bot orqali klient qo'shish va uning holatini kuzatish",
            "Botda qo'shilgan klientni qo'lda tuzatish yoki tasdiqlash",
        ]),
    ],
    "it_admin": [
        ("ProTarget: dostup ochish", "ProTarget", [
            "Yangi agent yoki supervayzerga ProTarget dostupi va huquqlari",
            "Agentga boshqa hudud yoki filial ma'lumotini ko'rish huquqi",
            "Vaqtincha qo'shimcha nuqtalarni ko'rish huquqi",
            "Huquq muddatini uzaytirish",
        ]),
        ("ProTarget: dostupni o'zgartirish va yopish", "ProTarget", [
            "Dostupni vaqtincha to'xtatish",
            "Ishdan ketgan agent dostupini yopish",
            "Boshqa hududga o'tgan agentning eski hudud dostupini olib tashlash",
            "Login yoki foydalanuvchi nomini o'zgartirish",
            "Ikkinchi (ortiqcha) akkaunt ochilib qolgan",
        ]),
        ("ProTarget: kirish muammolari", "ProTarget", [
            "Parolni tiklash",
            "Akkaunt bloklangan",
            "\"Ruxsat yo'q\" yoki \"foydalanuvchi topilmadi\" xabari",
            "Akkaunt bor, lekin kerakli menyular ko'rinmayapti",
            "Supervayzer yangi agentni ko'ra olmayapti",
            "Akkauntga noto'g'ri telefon raqami biriktirilgan",
            "Bir akkauntga ikki qurilmadan kirish",
        ]),
        ("ProTarget: telefon va akkaunt", "ProTarget", [
            "Eski telefondan yangisiga akkauntni ko'chirish",
            "Ilovani qayta ulash",
            "Yo'qolgan telefondagi akkauntni bloklash",
            "Yangi telefonda ilovani qayta sozlash",
        ]),
        ("ProTarget: mobil ilovaning texnik xatolari", "Mobil ilova", [
            "Ilova ochilmayapti, oq ekran, o'z-o'zidan yopilyapti",
            "Sinxronlash tugamayapti yoki xato beryapti",
            "Ma'lumotlar yangilanmayapti",
            "Yangilanishdan keyin ishlamay qoldi",
            "Internet bor, lekin serverga ulanmayapti",
            "Faqat Wi-Fi da ishlaydi",
            "Kamera, geolokatsiya va boshqa ruxsatlar o'chib qolgan",
            "Bildirishnomalar kelmayapti",
            "Internet uzilganda kiritilgan buyurtma keyin yuborilmayapti",
            "Buyurtma yuborishda texnik xato chiqyapti (diagnostika)",
        ]),
        ("1C va PRBC: dostup", "1C", [
            "1C yoki PRBC ga dostup ochish",
            "1C da yangi foydalanuvchi yaratish",
            "1C parolini tiklash",
            "Dostuplar ko'rinmayapti yoki menyular yo'qolgan",
            "Hamkasbda bor dostup menda yo'q",
        ]),
        ("1C bot: kirish", "1C bot", [
            "Botga kirish",
            "Botda klient qo'shish tugmasi yoki menyusi chiqmayapti (huquq masalasi)",
        ]),
        ("Hisobotlarga ruxsat", "Hisobot", [
            "Supervayzer jamoa hisobotini yoki barcha agent ma'lumotini ko'ra olmayapti",
            "Hisobotga kirish huquqi kerak",
        ]),
        ("Pochta", "Pochta", [
            "Korporativ pochtaga kira olmayapman",
            "Email yubormayapti yoki qabul qilmayapti",
            "Email spamga tushyapti",
            "Pochta qutisi to'lgan",
            "Emailni telefonga sozlash",
            "Pochta serverida uzilish",
        ]),
        ("Xavfsizlik", "Xavfsizlik", [
            "Shubhali xat yoki havola",
            "Akkauntdan men yubormagan xabar ketgan",
            "Parol boshqa odamga ma'lum bo'lgan",
            "Ruxsatsiz kirish urinishi",
            "Administrator huquqini olish",
            "Umumiy papka va fayl serverga kirish huquqi",
        ]),
    ],
    "dev": [
        ("Aksiya yaratish", "ProTarget", [
            "Yangi aksiya yaratish va tizimga qo'shish",
            "Aksiya shartlari, muddati va qoidalarini o'zgartirish",
            "Yangi aksiya ProTargetga qachon tushishi",
            "Aksiya va narx shartlari ProTarget bilan 1C da bir xil bo'lishi",
        ]),
        ("Aksiya va chegirma ishlamayapti", "ProTarget", [
            "Aksiya klientga qo'shilgan, lekin buyurtmada ishlamayapti",
            "Chegirma hisoblanmayapti yoki noto'g'ri hisoblanyapti",
            "Aksiya faqat ayrim mahsulotlarda ishlamayapti",
            "Yakuniy narx o'zgarmayapti",
            "Aksiya tanlash imkoniyati chiqmayapti",
            "Bir buyurtmada bir nechta aksiya qoidasi",
            "ProTargetda aksiya bor, 1C da yo'q (yoki aksincha)",
        ]),
        ("Integratsiya: 1C va ProTarget", "Integratsiya", [
            "Almashinuv to'xtab qolgan yoki kechikmoqda",
            "ProTargetdagi buyurtma 1C ga o'tmayapti (yoki 1C dagi buyurtma ProTargetda yo'q)",
            "1C dagi o'zgarish ProTargetda yangilanmayapti",
            "Klient integratsiya sababli dublikat bo'lib chiqyapti",
            "1C yangilanishidan keyin bog'lanish ishlamay qoldi",
            "Buyurtma summasi tizimlar o'rtasida farq qiladi (tizim sababli)",
        ]),
        ("Integratsiya: PRBC", "Integratsiya", [
            "PRBC dagi ma'lumot ProTarget bilan mos kelmayapti",
            "Bir tizimda tuzatilgan ma'lumot ikkinchisiga o'tmayapti",
            "Integratsiya xatosi log va vaqtini tahlil qilish",
        ]),
        ("1C bot", "1C bot", [
            "Bot javob bermayapti yoki xabar yuborildi, natija qaytmadi",
            "Botda klient qo'shish funksiyasi ishlamayapti",
            "Bot orqali qo'shilgan klient ProTargetga kelmayapti",
            "Botga yangi funksiya qo'shish",
        ]),
        ("ProTarget dasturi", "ProTarget", [
            "Dasturdagi xato (bug)",
            "Yangilanishdan keyingi tizim xatosi",
            "Plan, tashrif soni yoki plan bajarilishining noto'g'ri hisoblanishi",
            "Tasdiqlangan marshrut yoki jadval tizimdan ilovaga uzatilmayapti",
            "Xarita va GPS funksiyasidagi xato",
            "Bildirishnoma funksiyasi ishlamayapti",
            "Ma'lumotlar bir necha soatdan beri sinxronlanmayapti (ko'p agentda)",
        ]),
        ("Hisobotlar", "Hisobot", [
            "Hisobot ochilmayapti yoki yuklanmayapti",
            "Hisobot yangilanmagan, eski sana turibdi",
            "Hisoblash formulasi noto'g'ri",
            "Excelga eksportda ustun yoki ma'lumot yo'qolmoqda",
            "Hisobotga yangi ustun yoki ko'rsatkich qo'shish",
            "Filial yoki hudud bo'yicha hisobot olish imkoniyati",
            "Hisobotdagi son tizim xatosi sabab mos kelmayapti",
        ]),
        ("1C dasturi", "1C", [
            "1C sekin ishlayapti",
            "Yangilanishdan keyin funksiya ishlamayapti",
            "1C da hujjat ochilmayapti, chop etish shakli yoki Excelga eksport xato",
            "Ma'lumotlar kechikib ko'rinmoqda",
            "1C bilan boshqa dastur o'rtasida almashinuv",
            "1C dagi biznes jarayonni o'zgartirish taklifi",
        ]),
        ("Yangi funksiya va tarix", "Umumiy", [
            "Dastur yoki ilovaga yangi funksiya taklifi",
            "Noto'g'ri ma'lumotni kim o'zgartirganini ko'rish",
            "Agent profili va harakatlar tarixi",
            "O'zgarishlar jurnali",
        ]),
    ],
    "sysadmin": [
        ("Kompyuter va ish joyi", "Qurilma", [
            "Kompyuter yoqilmayapti, sekin, qizib ketmoqda yoki qayta yuklanmoqda",
            "Windows xatosi",
            "Monitor, klaviatura, sichqoncha, USB ishlamayapti",
            "Disk to'lgan; xotirani oshirish",
            "Yangi xodimga ish joyi tayyorlash",
            "Texnikani boshqa xonaga yoki xodimga ko'chirish",
            "Vaqtincha qurilma berish",
        ]),
        ("Printer, skaner, ofis qurilmalari", "Qurilma", [
            "Printer chiqarmayapti, qog'oz tiqilyapti, toner tugagan",
            "Printer tarmoqda ko'rinmayapti; drayver",
            "Chek printer",
            "Shtrix-kod yoki etiketka printeri",
            "Skaner hujjat yubormayapti",
            "Nusxa ko'chirish apparati",
        ]),
        ("Agentning telefoni va jihozi", "Qurilma", [
            "Yangi agent uchun telefon va dasturni tayyorlash",
            "Telefon batareyasi, zaryad qurilmasi",
            "Telefon xotirasi to'lgan",
            "Telefonda sana yoki vaqt noto'g'ri",
            "Android yangilanishidan keyingi qurilma muammosi",
            "Barcode skaner savdo jarayonida ishlamayapti",
            "GPS qurilma yoki transport kuzatuvi",
            "Qurilmani ta'mirlash va almashtirish",
        ]),
        ("Internet va tarmoq", "Tarmoq", [
            "Internet yo'q, sekin yoki uzilib qolyapti",
            "Ayrim saytlar ochilmayapti",
            "Wi-Fi ulanmayapti, signal past",
            "LAN kabel va rozetka",
            "IP manzil to'qnashuvi",
            "Yangi LAN port",
            "Mehmonlar uchun Wi-Fi",
            "Filial interneti",
            "Yangi filialni korporativ tarmoqqa ulash",
        ]),
        ("VPN va masofaviy kirish", "Tarmoq", [
            "VPN ulanmayapti yoki xatolik kodi chiqyapti",
            "VPN ulanadi, lekin ichki resurslar ochilmayapti",
            "Masofaviy xodimga VPN sozlash",
        ]),
        ("Serverlar (sysadmin)", "Server", [
            "Server ishlamayapti yoki javob bermayapti",
            "1C, ProTarget yoki PRBC serveriga hamma foydalanuvchida ulanish yo'q",
            "Ma'lumotlar bazasiga ulanish xatosi (infratuzilma)",
            "Server disk va resurslari",
            "Rejalashtirilgan texnik ishlar",
            "Zaxira nusxa va tiklash",
            "SSL sertifikat",
            "Ichki sayt va portal ochilmayapti",
            "Server vaqti noto'g'ri",
        ]),
        ("Ofis va filial", "Ofis", [
            "IP-telefon",
            "Videokuzatuv kamerasi",
            "Face terminal va turniketning qurilma tomoni",
            "Yangi filial uchun IT tayyorgarligi",
            "Texnika inventari, yo'qolgan yoki shikastlangan texnika",
            "Dastur o'rnatish, litsenziya, antivirus va virus ogohlantirishi",
        ]),
    ],
}

# Navbatli mas'uliyat: (vazifa, 1-navbat xodim kaliti, [(navbatdagi xodim kaliti, qachon unga o'tadi)]).
# Masalan: avval Supervayzer o'zi o'zgartiradi; qila olmasa — Operator (Saidabror).
FALLBACKS = [
    ("Klientni boshqa agentga o'tkazish yoki vaqtincha biriktirish", "supervisors",
     [("operator", "Supervayzer o'zi o'zgartira olmasa")]),
    ("Marshrutga nuqta qo'shish yoki olib tashlash", "supervisors",
     [("operator", "Supervayzer o'zi o'zgartira olmasa")]),
    ("Tashrif kunini o'zgartirish, shanba yoki bayram kunini olib tashlash", "supervisors",
     [("operator", "Supervayzer o'zi o'zgartira olmasa")]),
    ("Klient agent ro'yxatidan yo'qolgan yoki tashrif ro'yxatida chiqmayapti", "operator",
     [("it_admin", "Klient bor, lekin ilova ochilmasa yoki sinxronlanmasa")]),
    ("Aksiya klientga qo'shilgan, lekin buyurtmada ishlamayapti", "dev",
     [("operator", "Aksiya klientga umuman qo'shilmagan bo'lsa")]),
]

# Qaror sxemasi: savol turi -> zona
TRIGGERS = {
    "operator": "Ma'lumotni kiritish, tuzatish yoki o'chirish kerak",
    "it_admin": "Kira olmayapman, parol yoki dostup muammosi",
    "dev": "Yangi aksiya yoki dastur o'zgarishi kerak",
    "sysadmin": "Qurilma, internet, tarmoq yoki ofis muammosi",
}

# Aralash holatlar: (vaziyat, avval kim, keyin kim / qachon)
EDGE_CASES = [
    ("Klient ko'rinmayapti", "operator", "Klient bor, lekin ilova ochilmasa yoki sinxronlanmasa: Xusniddin"),
    ("Aksiya klientda ko'rinmayapti", "operator", "Aksiya qo'shilgan, lekin buyurtmada ishlamasa: dasturchilar"),
    ("Yangi aksiya kerak", "dev", "Operator faqat mavjud aksiyani klientga qo'shadi"),
    ("Buyurtma 1C da ko'rinmayapti", "operator", "Buyurtma tasdiqlangan, lekin 1C ga uzatilmasa: dasturchilar"),
    ("Buyurtma yuborilmayapti, xato chiqyapti", "it_admin", "Sabab dastur yoki integratsiyada bo'lsa: dasturchilar"),
    ("Marshrut tasdiqlangan, ilovada ko'rinmayapti", "it_admin", "Plan yoki hisoblashda xato bo'lsa: dasturchilar"),
    ("Hisobotdagi raqam noto'g'ri", "operator", "Ma'lumot to'g'ri, hisoblash xato bo'lsa: dasturchilar"),
    ("Ilova ochilmayapti", "it_admin", "Telefonning o'zi nosoz bo'lsa: Jahongir"),
    ("Internet yo'q, ilova ishlamayapti", "sysadmin", "Internet bor, ilova ochilmasa: Xusniddin"),
]
