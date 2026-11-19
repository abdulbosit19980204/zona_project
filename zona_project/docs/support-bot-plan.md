# Support bot — avto-javob beruvchi yordamchi (REJA)

> Holat: **TASDIQLANGAN, 1–2-bosqich kodi PROD'da (soya rejimi).** Bot: @savolbopbot.
> Holat jadvali — 9-bo'limda. O'zgartirish kerak bo'lsa shu faylning o'zini tahrirlaymiz.
>
> Sana: 2026-11-19 · Loyiha: foydali.xisobchim.uz (PROD)

---

## 1. Maqsad

Telegramdagi support guruhlarida agent va xodimlardan doim bir xil savollar tushadi, ko'pincha
skrinshot bilan. Bot:

1. Guruhdagi **har bir savolni** (matn + rasm) o'qiydi.
2. Doimiy savollarga **odamdan tezroq** (bir necha soniyada) chiroyli, standart javob beradi.
3. Yangi turdagi savolni tushunib, javob berishga harakat qiladi. Ishonchi past bo'lsa **mas'ul odamga uzatadi**.
4. Support xodimlari bergan javoblardan **o'rganadi**: yangi savol-javoblar bazaga qo'shiladi.
5. **7/24 ishlaydi.** AI tokeni tugasa ham to'xtamaydi va Telegram tomonidan bloklanmaydi.

### Rasmlardagi uchta namunaviy holat

Bu uchta holat — birinchi standart javob shablonlari. Matnlarini siz tasdiqlaysiz.

| # | Rasmda nima bor | Botning taxminiy javobi (qoralama) |
|---|---|---|
| 1 | PRBC bosh sahifasi: rol **Employee**, Telegram bog'lanmagan (`—`), "Yangi klient" bo'limi ko'rinmaydi | "Sizda yangi klient qo'shish bo'limi yo'q, chunki rolingiz *Employee*. Agent/supervayzer roli kerak — {mas'ul}ga yozing. Telegram akkauntingiz ham PRBC'ga bog'lanmagan: …" |
| 2 | PRBC → 1C natijasi: **"1C da allaqachon bor"**, nuqta kodi `UZ-…`, marshrut **"Kunlarsiz"**, **"Boshqa bo'linma"** | "Bu klient 1C'da avvaldan bor (kod: {kod}), yangisi ochilmadi. U marshrutda, lekin tashrif kunlari qo'yilmagan va boshqa bo'linmaga biriktirilgan. Supervayzeringiz kunlarni belgilab, sizning bo'linmangizga o'tkazishi kerak." |
| 3 | ProTarget ilovasi: **"…отправлена на модерацию"** | "Nuqta ProTarget'da moderatsiyaga yuborilgan — bu normal holat. Odatda {muddat} ichida tasdiqlanadi, keyin buyurtma qilish mumkin. {muddat}dan oshsa {mas'ul}ga yozing." |

Javoblarda rasmdan o'qilgan qiymatlar (kod, nom, holat) avtomatik qo'yiladi.

---

## 2. Asosiy g'oya: tokenni tejaydigan "zinapoya"

Har bir savol eng arzon bosqichdan boshlab ko'riladi. Keyingi bosqichga faqat oldingisi javob topa olmasa o'tiladi.
Shu tufayli savollarning katta qismi AI'siz, bepul va bir zumda javob oladi. AI tokeni tugaganda
bot faqat yuqori bosqichlarni yo'qotadi, to'liq to'xtab qolmaydi.

```
Telegram guruh ─► [Qabul + navbat] ─► 0. Filtr: savolmi? (salom, rahmat, stiker → e'tiborsiz)
                                      │
                                      ▼
                     1. Rasm → mahalliy OCR (bepul, serverda)  ─┐
                                      │                        │ matn + rasm matni
                                      ▼                        ▼
                     2. Qoidalar/shablonlar (kalit so'z, regex) ── topildi ─► Standart javob (≈1 s)
                                      │ topilmadi
                                      ▼
                     3. Bilim bazasidan o'xshash savol qidirish
                        (mahalliy embedding, bepul)            ── juda o'xshash ─► Shu javob (≈1–2 s)
                                      │ ishonchsiz
                                      ▼
                     4. AI (rasmni ko'radigan model) + bazadan topilgan 5 ta o'xshash javob
                        Provayderlar zanjiri: asosiy → zaxira → bepul   ── ishonch yuqori ─► Javob (≈5–15 s)
                                      │ ishonch past / AI yo'q
                                      ▼
                     5. Odamga uzatish: zona → jarayon → mas'ul (mavjud route())
                        "Savolingiz qabul qilindi, {mas'ul} javob beradi" + mas'ulga xabar
```

### Bosqichlar tafsiloti

**1. Rasm o'qish, mahalliy OCR, bepul.**
- Skrinshotlar ma'lum ekranlardan (PRBC, ProTarget, 1C) olinadi va ulardagi matn qat'iy.
  "отправлена на модерацию", "1C da allaqachon bor", "Kunlarsiz" kabi so'zlarni OCR
  (Tesseract yoki PaddleOCR, uz/ru/en) yetarlicha ishonchli o'qiydi. Bunga AI kerak emas.
- Serverda RAM yetarli (12 GB, ~10 GB bo'sh), GPU kerak emas.
- OCR ishonchsiz bo'lsa (xira foto, qo'lda yozuv) rasm 4-bosqichdagi AI'ga ketadi.

**2. Qoidalar va shablonlar.**
- Admin panelda **"Standart holatlar"** ro'yxati yuritiladi. Har birida:
  - **shart:** kalit so'zlar/regex, matnda yoki rasm matnida;
  - **chiqarib olinadigan maydonlar:** kod, nom va hokazo;
  - **javob shabloni:** uz/ru, chiroyli Telegram-HTML formatida;
  - **mas'ul:** kerak bo'lsa.
- Yuqoridagi uchta holat shu yerga birinchi bo'lib kiritiladi.

**3. O'xshash savol qidirish.**
- Bilim bazasi: mavjud savollar bazasi (zona/jarayon/tasdiqlangan misollar) va support guruhlaridan
  o'rganilgan savol-javoblar.
- Ko'p tilli mahalliy embedding modeli (masalan `multilingual-e5-small`) CPU'da ishlaydi va bepul.
- O'xshashlik ≥ 0.90 bo'lsa, tasdiqlangan javob AI'siz beriladi.
- 0.75–0.90 bo'lsa, topilgan namunalar AI'ga kontekst sifatida beriladi.

**4. AI.**
- Mavjud `AIProvider` / `AITaskConfig` (asosiy va zaxira model) mexanizmidan foydalaniladi.
  Yangi vazifa turi qo'shiladi: `support`.
- Asosiy model: Claude (rasmni ko'radi, uz/ru yaxshi biladi). Zaxira: Gemini. Oxirgi zaxira: bepul/arzon model.
- AI javobi qat'iy JSON formatida qaytadi:
  - `javob`;
  - `ishonch` (0–1);
  - `zona`;
  - `odamga_kerakmi`;
  - `rasmdan_olingan_maydonlar`.
- `ishonch < 0.7` yoki `odamga_kerakmi = true` bo'lsa, javob guruhga chiqmaydi va 5-bosqichga o'tadi.

**5. Odamga uzatish.**
- Mavjud `route()` funksiyasi (zona → jarayon → vazifa → mas'ul va uning zaxirasi) mas'ulni topadi.
- Bot guruhda qisqa "qabul qilindi" deb javob beradi va mas'ulni tilga oladi yoki unga shaxsiy xabar yuboradi.
- Mas'ul javob bergach (savolga reply qilsa), bu juftlik 6-bandga — o'rganishga tushadi.

---

## 3. O'rganish (yangi savollardan va xodimlar javoblaridan)

1. Bot guruhdagi **support xodimining javobini** kuzatadi: savolga *reply* qilingan xabarni yoki
   savoldan keyin 30 daqiqa ichida o'sha mavzuda yozilgan xabarni.
   - Xodim kimligi bazadagi **xodimlar ro'yxatidan** aniqlanadi (`Member.telegram`, 3a-bo'limga qarang).
   - Ro'yxatda yo'q odamning javobidan o'rganilmaydi.
2. Savol + rasm matni + xodim javobi **"o'rganish navbati"**ga tushadi. Unda yana saqlanadi:
   - kim javob bergani;
   - qaysi guruh va zona.
3. Javoblar avtomatik nashr qilinmaydi: tasdiqlanmagan javob boshqalarga berilmaydi
   (tasdiqlash tartibi 3b-bo'limda).
   - Ixtiyoriy qoida keyin yoqilishi mumkin: "bir xil javob 2 xil xodimdan kelsa — avtomatik nomzod".
4. Har bir bot javobi ostida 👍 / 👎 tugmalari bo'ladi. 👎 bosilgan javob qayta ko'rib chiqishga tushadi.
5. Xodimning javobi bot javobidan farq qilsa (bot noto'g'ri javob berib, xodim tuzatsa),
   bu juftlik **ustuvor** bo'lib navbatga tushadi va bot o'sha savolga javob berishni vaqtincha to'xtatadi.

## 3a. Xodimlar ro'yxati (kim javob beradi va kimdan o'rganiladi)

Ikki xil yozuv bor:
- **Xodim** (`Member`) — alohida odam; ishlari hisobot va yuklamada alohida ko'rinadi.
- **Jamoa a'zosi** (`TeamContact`, jamoa kartasida) — jamoa (masalan Dasturchilar, Pro-target) ishlari **jamoada
  qoladi**, a'zolarga bo'linmaydi; ular vaziyatga qarab ishni o'zaro bo'lishadi. A'zolar faqat aloqa va bot uchun.

2026-11-19 da prod bazaga yozildi (zaxiralar: `pre-staff-20261119-133706`, `pre-support-20261119-142323`).
Mavjud yozuvlarda faqat bo'sh aloqa maydonlari to'ldirildi, ism va lavozimga tegilmadi.

| Turi | Kim | Lavozim / jamoa | Daraja | Telefon | Telegram |
|---|---|---|---|---|---|
| Xodim #11 | Saidabror (Fatxullayev Said Abror) | Ma'lumotlar operatori (bio: "Аналитик 1C") | L1 | +998 90 969 30 13 | @StargroupSaid |
| Xodim #12 | Xusniddin | IT operator (L1) | L1 | +998 92 045 36 46 | @ganiyevxusniddin |
| Xodim #14 | Jahongir (AKT) | IT texnik yordam | L1 | +998 99 831 99 71 | @Jo6777 |
| Xodim #17 | Abdulbosit Tuychiev | DevOps (admin) | LEAD | +998 90 006 66 39 | @uzdev7 |
| Jamoa a'zosi | Ulug'bek | Dasturchilar jamoasi · 1C dasturchi | L3 | +998 92 045 52 42 | @stargroupUlugbek |
| Jamoa a'zosi | Alisher Xidirov | Dasturchilar jamoasi · 1C dasturchi | L3 | — (yashirin) | @Alisher_1c_prog |
| Jamoa a'zosi | Guzel Taipova | Pro-target | EXT | — | @Guzel_Taipova |

- Ulug'bek va Alisher avval alohida xodim (#18, #19) qilib qo'shilgan edi; ularga hech narsa bog'lanmagani
  tekshirilib, Dasturchilar jamoasi a'zosiga ko'chirildi (tarixda yozilgan).
- Bot xabarni Telegram username yoki ID bo'yicha taniydi. Birinchi xabarda ID yozib qo'yiladi, keyin username
  o'zgarsa ham taniladi.
- Mas'ul jamoa bo'lsa, bot jamoa a'zolarining hammasini belgilaydi — kim bo'sh bo'lsa, o'sha oladi.
- Xodimlar **Xodimlar** sahifasida, jamoa a'zolari esa jamoa kartasidagi «Jamoa a'zolari» bo'limida tahrirlanadi.

## 3b. Savol-javoblarni boshqarish va tasdiqlash tizimi

Bilim bazasidagi har bir savol-javob ("yozuv") hayot sikliga ega:

```
 yangi (bot yig'di / xodim javobi) ─► ko'rib chiqilmoqda ─► tasdiqlangan (bot ishlatadi)
                │                          │                     │
                └──► rad etilgan ◄─────────┘          tahrir ─► yangi versiya ─► qayta tasdiq
                                                       arxiv (eskirgan, ishlatilmaydi)
```

**Kim nima qila oladi** (mavjud platforma rollari asosida):

| Harakat | L1 xodim | L2/L3 mutaxassis | Admin |
|---|---|---|---|
| Ochiq savolga javob yozish (panel yoki Telegram) | ✅ | ✅ | ✅ |
| O'z zonasidagi javobni tasdiqlash | — | ✅ | ✅ |
| Istalgan javobni tahrirlash yoki tasdiqlash | — | — | ✅ |
| Standart holat (shablon) yaratish yoki o'zgartirish | — | ✅ (o'z zonasida) | ✅ |
| Arxivlash / o'chirish | — | — | ✅ |

**Javoblarni o'zgartirish:**
- Har bir tasdiqlangan javobni panelda tahrirlash mumkin. Eski matn **versiya** sifatida saqlanadi:
  kim, qachon, nimani o'zgartirgani ko'rinadi va bir tugma bilan orqaga qaytariladi.
- Tahrir tasdiqlanmaguncha bot **eski tasdiqlangan versiyani** ishlatadi, ya'ni javob bo'shab qolmaydi.
- Bir savolning bir nechta ko'rinishi (turli so'zlar bilan, uz/ru) bitta yozuvga **sinonim savollar**
  sifatida bog'lanadi. Bot ularning hammasini taniydi.

**Tasdiqlashning turli ko'rinishlari** (panelda):
1. **Navbat (inbox):** yangi nomzodlar ro'yxati, filtrlar bilan (zona, guruh, kim javob bergan, sana, nechta takrorlangan).
   Har birida "Tasdiqlash / Tahrirlab tasdiqlash / Rad etish / Mavjud yozuvga birlashtirish" tugmalari bor.
2. **Kartochka rejimi:** bitta savol, rasm va bir nechta javob varianti
   (xodimlardan va AI'dan) yonma-yon chiqadi. Eng yaxshisi tanlanadi yoki birlashtiriladi. Tez ko'rib chiqish uchun.
3. **Guruhlangan ko'rinish:** AI o'xshash savollarni klasterlarga ajratadi
   ("ProTarget moderatsiyasi — 14 ta savol"). Butun klasterga bitta javob tasdiqlanadi, shablon taklif qilinadi.
4. **Telegramda tasdiqlash:** mas'ul xodimga botdan qisqa xabar keladi — savol, taklif qilingan javob va
   ✅ / ✏️ / ❌ tugmalari. Panelga kirmasdan tasdiqlash mumkin.
5. **Bilim bazasi ko'rinishi:** barcha tasdiqlangan yozuvlar zona bo'yicha jadvalda ko'rinadi:
   qidiruv, qancha marta ishlatilgani, 👍/👎 nisbati, oxirgi tahrir.

**Xodimlar savollarga javob berishi:**
- **Telegramda:** guruhda savolga reply qilib odatdagidek yozadi. Bot buni o'rganish navbatiga oladi.
- **Panelda:** "Ochiq savollar" bo'limida bot javob bera olmagan savollar ko'rinadi. Xodim javob yozadi,
  bot uni guruhga savol egasiga reply qilib yuboradi (xodim nomidan, "👤 Jahongir:" kabi).
  Javob avtomatik ravishda bazaga nomzod bo'ladi.
- Javob yozgan xodim o'z javobini "standart javob qilib saqlash" deb belgilasa, u tezroq tasdiqlash navbatiga tushadi.

**Hisobot:** kim nechta javob bergani, nechta tasdiqlangani, bot qancha savolni yopgani,
qaysi savollar eng ko'p tushayotgani (haftalik).

---

## 4. 7/24 ishlash: token tugashi va bloklanmaslik

### 4.1. AI tokeni yoki balansi tugasa

- **Zinapoya:** 1–3 bosqichlar AI'siz ishlaydi, shuning uchun bot to'liq to'xtamaydi.
- **Provayderlar zanjiri:** Claude → Gemini → bepul model (masalan OpenRouter/Groq bepul modellari).
  429 yoki "balans tugadi" xatosida keyingisiga o'tiladi. Bu mantiq mavjud `ai/service.py`'da bor.
- **Kunlik byudjet:** `support` uchun kunlik token/so'm limiti bo'ladi.
  - 80% ga yetganda adminga ogohlantirish yuboriladi.
  - 100% da AI faqat ochiq qolgan savollar uchun ishlatiladi, qolganlari odamga ketadi.
- **Kesh:** bir xil savol yoki rasm (hash) uchun AI qayta chaqirilmaydi.
- **Tejamkorlik:** prompt keshlash (bilim bazasi qismi keshlanadi), rasmlar kichraytiriladi,
  oddiy savollar arzonroq modelga, murakkablari kuchli modelga yuboriladi.
- **Kuzatuv:** Control markazi va admin panelda quyidagilar ko'rinadi:
  - provayder holati;
  - bugungi xarajat;
  - qaysi bosqichda nechta savol javob olgani;
  - "AI ishlamayapti" ogohlantirishi.
- **Ixtiyoriy:** serverda mahalliy kichik model (Ollama) eng oxirgi zaxira sifatida. CPU'da sekin
  (≈20–60 s), lekin bepul va internetsiz ishlaydi. Tavsiya: avval kerakligini ko'rib, keyin qo'shish.

### 4.2. Telegram bloklamasligi uchun

- Faqat **rasmiy bot** (Bot API, BotFather orqali) ishlatiladi. Shaxsiy akkaunt ("userbot", MTProto)
  ishlatilmaydi — avto-javob beruvchi oddiy akkauntlar spam deb bloklanadi.
  Rasmiy bot guruhda savollarga javob berish uchun mo'ljallangan va bu Telegram qoidalariga mos.
- Botni guruhga **admin** qilib qo'shamiz (yoki BotFather'da *privacy mode* o'chiriladi), shunda u barcha xabarlarni ko'radi.
- **Tezlik limitlari** navbat orqali ushlanadi:
  - bitta guruhga daqiqasiga ~20 xabardan oshmaydi;
  - umumiy oqim soniyasiga ~30 xabardan oshmaydi;
  - `429 retry_after` kelsa kutib, keyin qayta yuboriladi.
- **Spam qilmaslik:**
  - faqat savolga javob beriladi, reply shaklida (QR Drive botidagidek);
  - bitta savolga bitta javob;
  - kim boshlamagan bo'lsa, unga shaxsiy xabar yuborilmaydi.
- **Ishonchlilik:**
  - systemd xizmati sifatida yoki Restart=always;
  - xabarlar avval bazaga yoziladi, keyin qayta ishlanadi, shuning uchun bot qayta ishga tushsa ham savol yo'qolmaydi;
  - "savol 2 daqiqadan ko'p javobsiz qoldi" degan nazorat qo'yiladi.

---

## 5. Arxitektura (mavjud loyihaga qanday qo'shiladi)

**Amalda qilingan** (rejadan farqi: alohida servis o'rniga backend ichida alohida Django ilova `support` —
AI sozlamalari, xodimlar, qidiruv va rollar tayyor bo'lgani uchun kam kod va kam xavf).
Ilova faqat o'zining yangi jadvallarida (`support_*`) ishlaydi va alohida jarayonda turadi.

| Qism | Fayl | Izoh |
|---|---|---|
| Bot jarayoni | `backend/support/runner.py`, `manage.py support_bot` | Har bir yoqilgan bot — alohida oqim, long-polling; paneldagi o'zgarish ~10 s da kuchga kiradi |
| Javob tanlash | `backend/support/engine.py` | Shablon → bazadan o'xshash → mavjud qoidalar (`zona.search`) → AI (ixtiyoriy) → odamga |
| OCR | `backend/support/ocr.py` | Tesseract (rus, uzb, uzb_cyrl, eng) — serverda, bepul |
| Telegram | `backend/support/telegram.py` | Rasmiy Bot API; chatga ≥3 s oraliq, 429 da kutadi |
| Jadvallar | `support_bot`, `support_group`, `support_entry` (+versiyalar), `support_message`, `support_tguser`, `support_settings` | Token va API hash shifrlangan (Fernet) |
| Jamoa a'zolari | `zona_teamcontact` | Yangi jadval; hisobotlarga ta'sir qilmaydi |
| AI | `AITaskConfig` → `support` | Asosiy + zaxira model, kunlik limit, `AIUsage` jurnali |
| Panel | `/support`, `/support/review`, `/support/knowledge`, `/support/settings` | Savollar, tasdiqlash (3 ko'rinish), bilim bazasi (versiyalar), botlar va sozlamalar |
| Deploy | `foydali-support-bot.service` | `foydali-setup.sh` o'rnatadi, Control markazida ko'rinadi |

### Prod xavfsizligi (majburiy)

- Mavjud bazalar (`db.sqlite3`, `qrdrive.sqlite3`) **sxemasi o'zgartirilmaydi**.
  Backend'ga faqat **yangi qator** (`AITaskConfig` → `support` vazifasi) yoki faqat qo'shuvchi migratsiya qo'shiladi.
- Har bir deploydan oldin zaxira olinadi (`pre-deploy-*`), keyin health-check va bio-lab tekshiriladi.
- Yangi servis alohida baza va unitlarda ishlaydi. Uni o'chirish yoki to'xtatish boshqa hech narsaga ta'sir qilmaydi.
- **Shaxsiy ma'lumot:** skrinshotlarda ism, STIR, telefon bo'lishi mumkin.
  - AI'ga faqat kerakli qism yuboriladi;
  - rasmlar N kundan keyin o'chiriladi (sozlanadi);
  - bot tokeni va AI kalitlari faqat `/etc/foydali/*.env` da saqlanadi.

---

## 6. Bosqichlar (ish rejasi)

Har bir bosqich oxirida siz tekshirasiz, keyin keyingisiga o'tamiz.

**Bosqich 0 — Tayyorgarlik (siz bilan, kodsiz)**
- Quyidagi 7-bo'limdagi savollarga javob olish.
- Support guruhlaridan 2–4 haftalik savol-javob tarixini eksport qilish (Telegram Desktop → Export chat → JSON + rasmlar).
- Tarixdan eng ko'p uchraydigan 20–30 savol turini ajratib, ularni siz tasdiqlaysiz.

**Bosqich 1 — Asos: "soya rejimi"**
- Servis skeleti, alohida baza, bot, navbat, OCR, qoidalar va shablonlar (uchta namunaviy holat bilan).
- Bot guruhga **javob yozmaydi**: har bir savolga tayyorlagan javobini **faqat admin chatiga** yuboradi.
- Natija: xavfsiz sinov, aniqlik o'lchanadi.
- Qabul mezoni:
  - namunaviy holatlar 95%+ to'g'ri;
  - javob vaqti ≤ 3 s.

**Bosqich 2 — Bilim bazasi va o'xshash savol qidirish**
- Embedding qidiruv; tarixdan import; mavjud savollar bazasini ulash.
- Admin panelda "Standart holatlar", "Bilim bazasi" va "Tasdiqlash navbati" bo'limlari (3b):
  - versiyalar va tahrir tarixi;
  - sinonim savollar;
  - navbat, kartochka va guruhlangan ko'rinishlar;
  - Telegramda ✅/✏️/❌ bilan tasdiqlash.
- "Ochiq savollar": xodim paneldan javob yozadi, bot uni guruhga reply qilib yuboradi.
- Xodimlarni `Member.telegram` orqali tanib, ularning javoblaridan o'rganish (3, 3a).
- Qabul mezoni: soya rejimida doimiy savollarning 70%+ AI'siz to'g'ri javob oladi.

**Bosqich 3 — AI va odamga uzatish**
- `support` AI vazifasi, rasmni ko'radigan model, ishonch chegarasi, zaxira zanjiri,
  kunlik byudjet va ogohlantirishlar.
- Ishonch past bo'lsa `route()` orqali mas'ulga uzatiladi.
- Qabul mezoni:
  - noto'g'ri javob ≤ 5%;
  - AI o'chirilganda ham bot ishlayveradi (sinab ko'riladi).

**Bosqich 4 — Jonli ishga tushirish**
- Avval **bitta guruhda** javob yozish yoqiladi, keyin boshqalarida.
- 👍/👎, o'rganish navbati, statistika sahifasi.
- Control markaziga qo'shish; nazorat ("javobsiz qolgan savol").

**Bosqich 5 — Kengaytirish (ixtiyoriy, keyin)**
- PRBC/1C'dan **jonli holat** tekshirish. Masalan "klient qayerda turibdi?" savoliga
  STIR yoki nom bo'yicha arizaning haqiqiy holatini topib javob berish. Buning uchun PRBC/1C API'siga ruxsat kerak.
- Ovozli xabarlarni matnga aylantirish.
- Mahalliy zaxira model (Ollama).
- Takrorlanadigan muammolar bo'yicha haftalik hisobot: qaysi savol ko'p tushyapti va nimani tuzatish kerak.

---

## 7. Sizdan kerak bo'ladigan javoblar (tasdiqlashdan oldin)

1. **Guruhlar:** qaysi support guruhlarda ishlaydi? Nechta guruh, kunlik taxminiy savol soni qancha?
2. ~~**Support xodimlari**~~ — ✅ javob berildi (3a-bo'lim). Qolgan savol: Xusniddin (IT operator, L1),
   "Supervayzerlar" va "Pro-target" jamoasi a'zolarining Telegram username'lari ham kerakmi?
   Saidabrorning lavozimi "Аналитик 1C" ga o'zgartirilsinmi?
3. **Javob uslubi:** qaysi tilda javob beriladi — savol tilida (uz/ru) avtomatikmi?
   Bot o'zini bot deb tanishtiradimi?
4. **Rejim:** bot hamma savolga javob beradimi yoki faqat ishonchi yuqori bo'lganiga?
   (Tavsiya: faqat ishonchi yuqori bo'lganiga, qolganini odamga.)
5. **AI byudjeti:** oyiga taxminan qancha ajratiladi? Qaysi provayder kalitlari bor (Claude, Gemini, …)?
6. **Tarix:** guruhlar tarixini eksport qilib bera olasizmi (2–4 hafta)?
7. **Standart javoblar:** uchta namunaviy holatdagi muddat va mas'ullar
   (moderatsiya qancha davom etadi, kim tasdiqlaydi, rol kim beradi)?
8. **PRBC/1C API:** 5-bosqich uchun klient holatini dasturiy tekshirishga ruxsat bormi?
9. **Bot:** yangi bot ochamizmi (tavsiya: alohida, masalan `@..._support_bot`) yoki mavjud QR Drive botimi?

---

## 8. Taxminiy xarajat va tezlik

| Bosqich | Javoblarning taxminiy ulushi | Vaqt | Narx |
|---|---|---|---|
| Qoidalar va OCR | 40–60% (skrinshotli doimiy holatlar) | ≈1 s | 0 |
| O'xshash savol | 15–25% | ≈1–2 s | 0 |
| AI | 15–30% | ≈5–15 s | Savol boshiga bir necha sent (rasm bilan); kesh va kichik modellar bilan kamayadi |
| Odamga uzatish | 5–15% | Odam tezligida | 0 |

*Ulushlar taxminiy. Aniq raqamlar 1-bosqichdagi soya rejimida o'lchanadi.*

---

## 9. Keyingi qadam

Siz bu rejani o'qib, 7-bo'limdagi savollarga javob berasiz va "tasdiqlayman" deysiz.
Shundan keyin ish **Bosqich 0/1** dan boshlanadi. Har bosqichda shu fayldagi holat yangilanib boriladi:

- [x] Reja tasdiqlandi (2026-11-19, javoblarni tahrirlash va tasdiqlash tizimi bilan to'ldirildi)
- [ ] Bosqich 0 — tayyorgarlik *(jarayonda)*
  - [x] Xodimlar va jamoa a'zolari prod bazaga yozildi (3a-bo'lim)
  - [x] Bot tokeni (@savolbopbot) — bazada shifrlangan, soya rejimida
  - [ ] Botni support guruhlariga qo'shish va **admin qilish** (privacy mode yoqilgan — admin bo'lmasa xabarlarni ko'rmaydi)
  - [ ] Botga shaxsiy chatda `/start` (@uzdev7) — admin chat avtomatik belgilanadi
  - [x] Bilim bazasi boshlang'ich to'ldirildi (2026-11-19, `manage.py support_import_kb`): savollar bazasidan 335 yozuv —
        66 tasdiqlangan (51 yozma qoida + aralash holatlar), 269 ko'rib chiqishda (qoidasi yo'q, faqat mas'ul belgilangan).
        Agentlarning 210 ta savol turidagi haqiqiy so'rash misollari «savol ko'rinishlari» bo'ldi
  - [x] Distributsiya to'plami (2026-11-19, `support_import_kb --pack distribution`): agent va supervayzerlarning savdo
        savollari — plan, AKB, SKU, savdoni oshirish, yetkazish, qarz/limit, to'lov, vozvrat/srok, aksiya/narx,
        merchandayzing, tashrif, brendlar, jamoani boshqarish. 38 mavzu, 230+ savol ko'rinishi (uz/ru, agentlar
        so'zlashuvi). Kompaniyaga xos raqamlar o'ylab topilmagan; hammasi ko'rib chiqishda. Manba fayl:
        `backend/support/data/distribution_kb.py` (to'ldirib, qayta import qilsa — faqat tegilmagan yozuvlarga qo'shiladi)
  - [ ] Guruhlar tarixi eksporti (2–4 hafta) — haqiqiy guruh savol-javoblari bilan bazani kengaytirish uchun
  - [ ] Namunaviy 3 shablon matnini tekshirib tasdiqlash (`/support/knowledge`, holati «Ko'rib chiqilmoqda»)
- [x] Bosqich 1 — soya rejimi *(kod PROD'da, 2026-11-19)*
- [x] Bosqich 2 — bilim bazasi, tasdiqlash tizimi, versiyalar, paneldan javob *(kod PROD'da)*
- [x] Bot boshqaruvi *(2026-11-19)*: rejimlar — O'chiq / **Faqat yig'ish** (hech kimga yozmaydi, yig'adi va o'rganadi) /
      Soya / Jonli (bot va guruh bo'yicha); 7 ta yoqib-o'chiriladigan xatti-harakat (admin chatiga taklif, «qabul qilindi»,
      @mas'ul, 👍/👎, nomzodlar, aniqlashtirishni ajratish, avval ma'lumot so'rash)
- [x] Aniqlashtirish zanjiri: xodimning «STIR yuboring?» kabi savoli javob deb olinmaydi; savol → aniqlashtirish →
      ma'lumot → yakuniy javob zanjiri saqlanadi; yozuvga «javobdan oldin so'raladigan ma'lumot» (`ask_first`) o'rganiladi,
      jonli rejimda bot uni avval o'zi so'raydi. O'xshash nomzodlar bitta yozuvga birlashadi
- [x] Guruh tarixini o'rganish: egasining Telegram akkaunti orqali FAQAT O'QISH (Telethon, API ID/hash, seans shifrlangan),
      paneldan ulash (telefon → kod → 2FA), muddat (kun), rasmlar (OCR), fon vazifasi va jonli holat
- [x] Tahlil sahifasi (`/support/analytics`): xodimlar javoblari (soni, o'rtacha vaqt, aniqlashtirishlar, nomzod/tasdiqlangan),
      javobdan oldin eng ko'p so'raladigan ma'lumotlar, kunlar/guruhlar bo'yicha
- [x] Rasmlarni o'rganish (ML): savol rasmlari va videolari serverda saqlanadi (`support_media`, sha256 bo'yicha bir marta);
      har rasmdan vizual iz (dHash: butun + o'rta qism) olinadi va o'rgatilgan namunalarga eng yaqin qo'shni (kNN) bo'yicha
      solishtiriladi — bir xil ekran boshqa ism/o'lcham bilan 0–5, boshqa ekran 23–37 masofada (chegara 10). Tanilgan rasmga
      javob OCR'siz, bir zumda; OCR javobdan keyin. Namunalar: «Rasm turlari» sahifasida guruhni bir bosishda o'rgatish,
      yozuvga skrinshot yuklash, xodim javobi va ishonchli moslikdan avtomatik. O'rgatilgan rasmlar o'chirilmaydi
- [x] Javob biriktirmalari: rasm, video, hujjat (10 tagacha, albom bo'lib); Telegram `file_id` keshlanadi
- [x] Pro-target ko'rsatmalari (`--pack protarget`, tasdiqlangan): vizitni boshlab bo'lmasa, geoteg o'zgartirish,
      moderatsiya (9:00–18:00 da 5–10 daq, bosqichlar, navbat), bildirishnomalar (Profil → Bildirishnomalar);
      tahlilda Pro-target bo'limi
- [ ] Bosqich 3 — AI *(kod tayyor, o'chiq: Support → Sozlamalar → «AI javoblari»)*; mas'ulga uzatish ishlaydi
- [ ] Bosqich 4 — jonli ishga tushirish (soya rejimida aniqlik o'lchangach, guruh bo'yicha yoqiladi)
- [ ] Bosqich 5 — kengaytirish
