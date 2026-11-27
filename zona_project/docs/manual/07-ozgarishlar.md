# O'zgarishlar tarixi

> Tizimga kiritilgan o'zgarishlar — eng yangisi tepada. Har deploy bilan shu yerga yoziladi.

## 2026-11-27

- **PRBC vazifa to'g'riligi:** tashqi jamoa (Pro-target) mas'ul bo'lgan savolga vazifa ochilmaydi va boshqa xodimga
  tushirilmaydi (avval birinchi a'zoga — @Guzel_Taipova ga yoki keyingi xodimga — Saidabrorga ochilardi); Pro-target
  a'zolari ijrochi/kuzatuvchi bo'lmaydi. **Statistika:** Tahlil → xodimlar jadvalida @IT_StarGroup javoblari asosiy
  operatorga (Xusniddin) yoziladi; Pro-target a'zolari alohida qatorda.
- **Inventar: "Tasdiqnomalar" bo'limi olib tashlandi** (`/inv/acks` va mobil menyudagi tab). Havolani IT bo'limi
  ichki tizim orqali yuboradi: Import / Eksport → "Tasdiqlash havolalari (Excel)". Filial xodimi faqat egasining
  telefoni va Telegramini yozadi. Filial xodimlari uchun PDF va video qo'llanma (UZ/RU) tayyorlandi.
- **Bot salomlashuv va mazmunsiz savollardan o'rganmaydi.** «Assalomu alaykum», «Нукус к3», «Тут тоже самое»,
  «@Guzel_Taipova», «Почему так ?» kabi savollar va «Готово», «отвязала, переподключите», «Tuzatildi ✅», «Bu
  so'rovni … bajaradi» kabi javoblar endi bilim bazasiga nomzod bo'lmaydi (standartga qo'shishda ham). Navbatni
  yopish uchun server buyrug'i: `support_close_review` (--dry-run, --older-than, --only-same).
- **Toifa mas'uli — asosiy va zaxira.** Support sozlamalarida har toifaga ikkinchi ustun: zaxira mas'ul (aralash ishlar,
  masalan aksiya). Javobda asosiy bilan birga belgilanadi, PRBC vazifasida kuzatuvchi.
- **Dasturchilar jamoasi:** xodim kartochkasida yangi maydon «Jamoa a'zosi» — Kamoliddin va Timur «Dasturchilar
  jamoasi»ga (Ulug'bek, Alisher bilan) qo'shiladi: jamoa mas'ul bo'lgan savolda belgilanadi, hisobotda jamoa
  ostida, haftalik yuklamada jamoa ulushi.
- **Umumiy akkauntning asosiy operatori:** jamoa a'zolari ro'yxatida «Asosiy operator» — @IT_StarGroup uchun
  Xusniddin: bu akkauntdan yozilgan javoblar hisobotda va PRBC vazifalarida Xusniddinga yoziladi.
- **Toifa qoidalari kengaydi:** «ТТ / точка / tochka» → Klient, «доступ / dostup / ruxsat / позывной / pozivnoy» →
  Kirish.
- **«Bu raqam boshqa PRBC akkauntiga bog'langan» — bot aniqlaydi va ruxsat bilan hal qiladi.** Guruhda shu xato
  (matn yoki skrinshot) kelsa, bot 1C dagi eski akkaunt va Telegram orqali ochilgan yangi akkauntni topadi, 7 ta
  xavfsizlik shartini tekshiradi va javobda yozadi. Panelda amallar yoqilsa: xodimdan raqamini bot shaxsiy chatida
  tugma orqali so'raydi (faqat o'z kontakti), 1C xodimini eski akkauntdan uzib yangisiga bog'laydi, eski akkauntdagi
  raqamni bo'shatadi (buzmaydi); xato bo'lsa hammasini qaytaradi. Har amal jurnalda, ortga qaytariladi. Standart —
  amallar o'chiq. Panelda bitta odamni tekshirish, sinov rejimi va ikki akkauntli xodimlar ro'yxati.
- **Toifa mas'uli — butun jamoa:** Support sozlamalarida har jamoa ro'yxati boshida «Butun jamoa» varianti (masalan
  Pro-target — Guzel va Eldar); tanlansa javobda va vazifada jamoaning barcha a'zolari belgilanadi. Oldin backend
  qabul qilardi, lekin sozlamada tanlab bo'lmasdi.
- **Yangi bot amallari (har biri ruxsat bilan, standart o'chiq):** Telegram ma'lumotini yangilash; «Vazifalar» va
  «Chat» moduliga A'zo ruxsati («PRBC'da vazifalar ko'rinmayapti», «PRBC chat ochilmayapti»); mavjud nuqtani
  marshrutga qayta qo'shish (1C band bo'lgan bo'lsa). Panel sinovida savol turi tanlanadi. Hisobni tasdiqlashga bot
  tegmaydi — guruhga qo'shilganda PRBC o'zi tasdiqlaydi.
- **Bot amallari — har biri alohida ruxsat bilan.** Standart holatda bot «yangi tochka» muammosini faqat aniqlaydi va
  javobda yozadi (nima yetishmaydi, nima kerak) — PRBC'da hech narsa o'zgarmaydi, savol mutaxassisga o'tadi. Panelda
  amal yoqilsa (ruxsat, rol, guruh bo'limi, pozivnoy, ma'lumotnoma yangilash, arizani 1C ga qayta yuborish) — bot o'zi
  bajaradi va javobda nima qilinganini (oldin → keyin) yozadi. Doimiy nazorat endi faqat hisobot.
- **Pozivnoy to'liq yozilguncha so'raladi:** «sr1» kabi noto'liq javobga bot mos variantlarni ko'rsatib qayta so'raydi
  (3 martagacha). **Bo'lim — guruhga qarab:** xodim savol yozilgan guruhga mos PRBC bo'limiga qo'shiladi.
- **Sinab ko'rish va ortga qaytarish:** panelda xodim + savol + guruh bo'yicha bot javobini PRBC'ni o'zgartirmasdan
  ko'rish; jurnalda har o'zgarishning oldingi/keyingi holati va «Ortga qaytarish» tugmasi.
- **«Не удалось подключиться к серверу» / «Долго грузит и выдает ошибку»** — standart javob: «Перезайдите в
  приложение», mas'ul — Guzel.
- **«Yangi tochka qo'sha olmayapman» — bot o'zi hal qiladi.** Guruhda shu savol yoki «ни одно подключение к 1С»
  skrinshoti kelsa, bot xodimni PRBC'da tekshiradi: hisob faol, rol, asosiy bo'lim, «Integratsiyalar» ruxsati va 1C
  pozivnoy. Yetmaganini o'zi beradi, pozivnoyni xodimdan so'raydi va 1C ro'yxatidan topib biriktiradi, so'ng
  «ilovani yopib qayta oching» deydi. Hal qilib bo'lmasa — topganini yozib mutaxassisga uzatadi.
- **Doimiy nazorat:** PRBC worker har soatda barcha savdo vakillarini tekshiradi, ruxsat / rol / bo'limni o'zi beradi.
  Yangi sahifa **Yangi tochka ruxsatlari** (`/prbc/access`): kamchiligi bor xodimlar, bitta xodimni tekshirish,
  jurnal, sozlamalar.

## 2026-11-26

- **Moderatsiya skrinshoti + "qo'shib bering"** endi xodimga uzatilmaydi. "Торговая точка … отправлена на
  модерацию!" ekrani bilan "Кушиб беринг Навоий СР3" kabi iltimos kelsa, bot moderatsiya standart javobini beradi:
  nuqtani Pro-target tasdiqlaydi, u o'zi qo'shiladi. Oldin imzodagi so'zlar alohida savol deb olinib, xodim
  belgilanardi.
- **Rasm matni (OCR) aniqroq:** kirillcha qatordagi qisqa so'z lotin harflari bilan o'qilsa ("отправлена Ha
  модерацию"), u kirillchaga aylantiriladi. Shunda shartlar topiladi; lotincha nomlar o'zgarmaydi.
- **Vazifalar sahifasi qayta ishlandi:** jadvaldagi har raqam bosiladi — ro'yxat aynan shu xodim / guruh va holat
  (muddati o'tgan, bajarilgan, kech bajarilgan, ochiq, bekor) bo'yicha; statistika tanlangan tur va davrga mos (1C
  bo'shash vazifalari "Biz yaratgan"ga aralashmaydi); vazifalar chiroyli kartalarda — qancha qoldi / kechikdi / qancha
  vaqtda bajarildi.
- **Qo'llanma rasmlari ko'rish oynasida** — rasm yangi tabda emas, shu sahifadagi modal oynada ochiladi:
  kattalashtirish/kichraytirish (g'ildirak, +/−, ikki marta bosish), sudrab siljitish, ← → boshqa rasmlar, Esc — yopish.
- **Sozlamalar qo'llanmasi skrinshotlar bilan** — yangi bob: har sozlama qayerda va nima qiladi, 31 ta skrinshot
  (rasmlar faqat kirgan foydalanuvchiga ko'rinadi). Eski guruh kartasida "PRBC vazifa" kaliti endi bloklangan.
- **Logo va nom:** sayt endi **Foydali** — o'z logosi (ko'k-binafsha gradient, "F" va StarGroup yulduzchasi),
  favicon, iPhone belgisi; brauzer sarlavhasi "… · Foydali". Next.js standart belgisi olib tashlandi.
- **Qo'llanma moduli** — butun tizimning yo'riqnomasi (shu hujjat), qidiruv bilan; chap menyuda alohida bo'lim.
- **PRBC vazifalar Support bot menyusida** — Vazifalar nazorati, Vazifalar, 1C xodimlari, Jurnal, PRBC sozlamalari;
  har PRBC sahifasi tepasida bo'limlar paneli.
- **Vazifalar nazorati** sahifasiga xodimlar va guruhlar bo'yicha statistika (30 kun) va 1C xodimlari qisqacha.
- **Eski (yo'naltirilgan) guruhlardan** vazifa ochilmaydi.
- **Guruh qoidalari:** har guruhda "PRBC vazifa" kaliti (VAZIFALAR — o'chiq, ROP — yoqiq); har guruh o'z PRBC
  loyihasiga; ijrochi — vazifa kimga tegishli bo'lsa (javob yozgan xodim → mavzu mas'uli → toifa mas'uli → guruh
  ijrochisi → guruhda ko'p javob beradigan → standart).
- **Vazifa nazorati (SLA):** muddat 10 daqiqa (ish vaqtida), boshlanish, taxminiy vaqt, ustuvorlik; savol holati
  PRBC'ga (In Progress / Done / qayta ochish); muddat o'tsa ogohlantirish; odamga uzatilgan har savolga vazifa;
  vazifasiz savollarga bir bosishda vazifa; Vazifalar nazorati sahifasi.

## 2026-11-25

- **Mijoz holati PRBC'dan** — savolda STIR / JShShIR / 1C kodi bo'lsa, bot ariza holatini jonli tekshiradi;
  PRBC qo'llanmasi asosida 10 ta yangi bilim bazasi yozuvi (holatlar, 1C xatolari).
- **Inventar katalogi:** 35 yangi tur (videokuzatuv faol, qolgani nofaol); turlarni bir bosishda yoqish/o'chirish,
  guruhni birdan yoqish, filtr.
- **ProTarget:** "nuqta marshrutga qo'shildi" — moderatsiya va sinxronlashni kutish (5–10 daqiqa, qo'lda 1 soatgacha)
  standart javobi.
- **"Tasdiq kutilmoqda"** standart javobi; siyrak ekranlarda rasm o'xshashligidan matn ustun; standart javoblarni AI
  qayta yozmaydi.
- **Inventar:** filial direktorlari uchun faqat ko'rish loginlari; barcha loginlar bitta Excel faylda.
- **PRBC:** guruh → loyiha bog'lanishi, savol → vazifa oqimi (fayllar, qo'shimchalar, guruhga hisobot).
