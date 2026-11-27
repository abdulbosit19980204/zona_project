# PRBC va vazifalar

> PRBC (prbc.uz) bilan integratsiya: savollardan vazifa ochish, ijrochi va loyiha qanday tanlanadi, muddat (SLA),
> holat sinxroni, vazifalar nazorati, 1C xodimlari sinxroni, mijoz holatini tekshirish va barcha sozlamalar.

Menyu: **Support bot → PRBC vazifalar** (Vazifalar nazorati, Vazifalar, 1C xodimlari, Jurnal) va
**Support bot → Sozlash → PRBC sozlamalari**. Har PRBC sahifasining tepasida bo'limlar paneli bor.

## Qanday ishlaydi

- Ulanish — administratorning **o'z PRBC akkaunti** (telefon + parol, shifrlangan). Tizim PRBC'da shu odam nomidan
  ishlaydi va uning huquqlari bilan cheklanadi.
- Hamma ish alohida jarayonda — **foydali-prbc** worker'ida (bot PRBC'ni kutmaydi):
  - savol navbati → PRBC vazifasi (har ~10 soniyada);
  - savol holati → vazifa holati, muddat nazorati (har 30 soniyada);
  - vazifalar holatini o'qish va hisobot (har 2 daqiqada; PRBC'da webhook yo'q);
  - 1C xodimlari sinxroni (sozlamadagi har N daqiqada).

## Qaysi savolga vazifa ochiladi

1. Bot javob bera olmagan (odamga uzatilgan) **har savolga** — "Odamga uzatilgan har savolga vazifa" yoqiq bo'lsa.
2. Bilim bazasida **"Vazifa yaratiladi"** belgilangan mavzu — bot javob bergan bo'lsa ham.
3. **Ochilmaydi:**
   - guruhda **PRBC vazifa** o'chiq bo'lsa — VAZIFALAR (test guruhi);
   - **eski** (yangi guruhga yo'naltirilgan) yoki nofaol guruhda;
   - salomlashuv, suhbat, aniqlashtirish yoki takror xabar bo'lsa.
4. **Bitta mavzu — bitta vazifa:** shu odam 24 soat ichida shu mavzuda yana so'rasa, yangi vazifa ochilmaydi —
   savol mavjud vazifaga izoh bo'lib qo'shiladi.

> Qoida: **ROP guruhlaridan vazifa ochiladi, VAZIFALAR'dan — yo'q.** Yangi guruh qo'shilsa, standart holatda vazifa
> yoqiq bo'ladi — test guruhini o'chirib qo'ying (PRBC sozlamalari → Guruh → loyiha jadvali).

## Vazifa qanday ko'rinadi

- **Sarlavha:** savolning o'zi (salomlashuvsiz) yoki tanilgan holat nomi + nuqta kodi (UZ-…), zakaz raqami, kimdan.
- **Tavsif:** savol matni, kimdan va qaysi guruhdan, agent ma'lumotlari (kod, loyiha, hudud, supervayzer), guruhdagi
  xabar havolasi, bot javobi, savol egasining qo'shimchalari, **qaysi sababga ko'ra shu ijrochi tanlangani** va muddat.
- **Fayllar:** savoldagi rasm va fayllar vazifaga biriktiriladi; keyin yuborilganlari ham qo'shib boriladi.
- **Odamlar:** ijrochi + kuzatuvchilar (Kamoliddin aka va ulangan akkaunt egasi).

## Ijrochi: vazifa kimga tegishli

Tartib (birinchi topilgani):

1. Savolga **allaqachon javob yozgan xodim**.
2. **Mavzu mas'uli** (bilim bazasidagi yozuv mas'uli).
3. **Toifa mas'uli** — Support sozlamasidagi "toifa bo'yicha mas'ul": aksiya, to'lov, qoldiq → **Saidabror**;
   login → **Xusniddin**.
4. **Guruh ijrochisi** — PRBC sozlamalari → Guruh → loyiha jadvalida qo'lda tanlangan.
5. Shu guruhda **eng ko'p javob beradigan xodim** (oxirgi 30 kun).
6. **Standart ijrochi** (sozlamada; hozir Xusniddin).

- Umumiy **IT SUPPORT** akkaunti hech qachon ijrochi bo'lmaydi.
- Standart ijrochiga tushgan vazifaga boshqa xodim javob yozsa, vazifa avtomatik o'sha xodimga o'tadi
  (PRBC'da izoh qoldiriladi). Qo'lda o'zgartirilgan ijrochiga tegilmaydi.
- Telegram → PRBC moslash: xodim PRBC'dagi shaxsga bog'langan bo'lsa (1C xodimlari), sozlamadagi qo'lda moslash
  yoki zona xodimi ismi PRBC'da yagona bo'lsa.

## Loyiha: har guruh o'z loyihasiga

PRBC sozlamalari → **Guruh → loyiha** jadvali. Hozirgi bog'lanish:

| Guruh | PRBC loyiha |
|---|---|
| HEINZ ROP / LOREAL ROP / J&J-JOHNSON ROP / BIC-SILVER-СХЗ ROP / MDLZ ROP | o'z nomidagi ROP loyihasi |
| COSMOPROF-EVELIN ROP | COSMOPROF ROP |
| HEINZ, LOREAL, MDLZ, EVELIN REGION | o'z REGION loyihasi |
| Heinz .Vitana Pro target филиалы | HEINZ REGION |
| BIC, Silver, СХЗ - Protarget | BIC-SILVER-СХЗ ROP |
| Bic Sxz Silver Добавление Точек, Мерчендайзери, MR MDLZ TASHKENT, 1C ДОБАВЛЕНИЯ Т.Т | o'z loyihalari |
| Запуск новой базы MDLZ va bog'lanmaganlar | standart: **STAR GROUP \| IT Поддержка** |

PRBC guruh loyihasiga ruxsat bermasa — vazifa standart loyihada ochiladi.

> **Vazifa ochilmaydigan guruhlar (hozir):** VAZIFALAR (test guruhi, kalit o'chiq) va eski — yangi guruhga
> yo'naltirilgan guruhlar: BIC, Silver, СХЗ - Protarget; Bic Sxz Silver Добавление Точек; HEINZ REGION;
> Heinz .Vitana Pro target филиалы; LOREAL REGION. Jadvalda ular "eski guruh → …" deb belgilangan.

## Muddat (SLA)

- Har vazifaga: **boshlanish**, **muddat**, **taxminiy vaqt** va **ustuvorlik** (standart "High") qo'yiladi.
- Me'yor — **10 daqiqa**, faqat ish vaqtida (**Du–Sha 09:00–18:00**, Toshkent). Ish vaqtidan keyin kelgan savolning
  muddati — keyingi ish kuni 09:10. Kun oxirida boshlangani ertasiga davom etadi.
- Muddat o'tsa — PRBC'da bitta izoh ("⏰ Muddat o'tdi…") va ustuvorlik **shoshilinch** bo'ladi.

## Holat sinxroni

| Guruhdagi voqea | PRBC vazifasi |
|---|---|
| Xodim savolga javob yozdi / reaksiya qo'ydi / "jarayonda" bosdi | **In Progress** (+ izoh) |
| Savol **hal bo'ldi** (savol egasi, xodim yoki panel) | **Done** (+ izoh "savol hal bo'ldi — kim, qachon") |
| Vazifa yopilgandan keyin savol egasi "hal bo'lmadi" dedi | qayta **In Progress**, yangi muddat |
| PRBC'da xodim **Done** qildi | savol "hal bo'ldi", guruhga hisobot (kim, qancha vaqtda, izohlar) va "hal bo'ldimi?" tugmalari yopiladi |

PRBC "Done"ni rad etsa (masalan, Definition of Done bajarilmagan) — sababi Vazifalar nazoratida ⚠ bilan ko'rinadi.

## Vazifalar nazorati (sahifa)

- **Ko'rsatkichlar:** ochiq, muddati o'tgan, 5 daqiqada tugaydi, bugun bajarildi, muddatida bajarilgan % (7 kun),
  o'rtacha hal qilish vaqti.
- **Vazifasiz ochiq savollar** ogohlantirishi va **"Hammasiga vazifa ochish"** tugmasi (oxirgi 7 kun).
- **Ochiq vazifalar** muddat bo'yicha: har birida jonli taymer — yashil (vaqt bor), sariq (3 daqiqadan kam), qizil
  (+kechikish). Filtrlar: hammasi / muddati o'tgan / yangi / jarayonda; qidiruv; ijrochi bo'yicha.
  Tugmalar: **▶ Boshlash**, **✓ Bajarildi** (PRBC'da ham o'zgaradi), guruhdagi savol, PRBC'da ochish.
- **Bajarilganlar** — bugun va kecha, qancha vaqtda hal bo'lgani bilan ("avtomatik" — savol guruhda hal bo'lgani uchun).
- **Xodimlar bo'yicha** va **guruhlar bo'yicha** (30 kun): ochiq, muddati o'tgan, bajarilgan, jami, o'rtacha vaqt.
  Xodim qatorini bossangiz, ro'yxat shu xodim bo'yicha filtrlanadi.
- **1C xodimlari** qisqacha: jami, ishlayapti, bo'shayapti, bo'shagan, bog'lanmagan.

Sahifa har 15 soniyada yangilanadi; menyudagi raqam — ochiq vazifalar soni.

## Vazifalar (sahifa)

- **Tur:** Biz yaratgan / Ishdan bo'shash / Yangi xodim / Hammasi; **davr:** 7, 30, 90 kun yoki hammasi. Statistika ham,
  ro'yxat ham shu tanlov bo'yicha (bir xil sonlar).
- **Tepadagi kartalar:** Jami, Bajarilgan, Ochiq, Muddati o'tgan, Kech bajarilgan, Bekor qilingan — bossangiz, ro'yxat shu
  holat bo'yicha.
- **Xodimlar bo'yicha jadval:** har raqam bosiladi. Masalan, xodim qatoridagi "Muddati o'tgan 14" — aynan uning 14 ta
  muddati o'tgan vazifasi; "Bajarildi" — bajarganlari; "Kech bajarilgan" — muddatdan keyin yopilganlari. Ismni bossangiz —
  xodimning barcha vazifalari. Tanlangan katak ko'k bilan belgilanadi.
- **Guruhlar bo'yicha jadval** — xuddi shunday, guruh bo'yicha.
- **Ro'yxat:** sarlavhada nima tanlangani ("Said Abror · Muddati o'tgan · 3 ta vazifa"), holat tugmalari soni bilan va
  "Tanlovni tozalash". Har vazifa kartasida: rangli chiziq (qizil — muddati o'tgan, ko'k — ochiq, yashil — bajarilgan,
  sariq — kech bajarilgan, kulrang — bekor), ijrochi, savol egasi va guruh, loyiha, **qancha qoldi / qancha kechikdi** yoki
  **qancha vaqtda bajarildi**; PRBC'da ochish va guruhdagi savol tugmalari. Kartani bossangiz — tafsilot (izohlar,
  chek-list, sarflangan vaqt, tarix).
- O'ngda — paneldan **yangi vazifa** yaratish.

## 1C xodimlari

- PRBC HR modulidagi 1C vazifalari (loyiha 15): "Yangi xodim: …" va "Ishdan bo'shash: …" — tizim shulardan xodimlar
  ro'yxatini yuritadi.
- Xodim faqat **aniq signal** bilan bo'shagan deb belgilanadi (bo'shash vazifasi yoki HR'da nofaol) — ro'yxatda
  yo'qligi uchun emas.
- Bo'shaganda: kontaktlar sahifasidagi o'rni bo'shatiladi (tarix saqlanadi, qaytarsa bo'ladi), inventardagi xodim
  nofaol qilinadi, bo'shash vazifasiga undagi qurilmalar ro'yxati izoh bo'lib yoziladi.
- Har shaxsni zona kontakti, xodim, inventar xodimi va Telegram foydalanuvchisiga bog'lash mumkin; agent kodi
  ("Toshkent K1") qo'lda tuzatiladi.

## Mijoz holati (jonli tekshiruv)

- Savol yoki skrinshotda **STIR / JShShIR / 1C kodi** bo'lsa, bot PRBC → Integratsiyalar → Savdo nuqtalari'dan mijoz
  arizasini o'qiydi (faqat o'qish, 8 soniya kutadi, 2 daqiqa kesh) va karta qo'shadi.
- Kartada: ariza holati, 1C kodlari, **Marshrut**, **ProTarget**, **Bo'linma** holati (1C izohi bilan), 1C rad etgan
  bo'lsa — sababi tushunarli tilda va **nima qilish kerak**; "mavjud nuqtalarni marshrutga qo'shish" so'rovi holati.
- Telefon, aloqa shaxsi, koordinata guruhga chiqmaydi.
- Holatlar ma'nosi (PRBC qo'llanmasi 12-bob):

| Ustun | Qiymat | Ma'nosi |
|---|---|---|
| Holat | Qoralama / Tekshiruv kutilmoqda / 1C navbatida / Qayta urinish | yo'lda; kutish yoki yuborish kerak |
| Holat | 1C da yaratildi / 1C da allaqachon bor | tayyor / mavjud nuqta ishlatildi |
| Holat | 1C rad etdi | sababi kartada (ko'pincha bo'linma vakilga tegishli emas) |
| Marshrut | Marshrutda / Kunlarsiz / Hujjat faol emas / Marshrutda yo'q / Boshqa agentda | agent nuqtani ko'radimi |
| ProTarget | Yuborildi / **Qisman** / Xato | "Qisman" — odatiy (1C tomonidagi tur moslamasi); ko'rinmasa 5–10 daq, qo'lda 1 soatgacha |
| Bo'linma | To'g'ri / Boshqa bo'linma / Xato | |

- PRBC sozlamalarida kalit bilan o'chiriladi; **"Mijoz holatini tekshirish"** oynasida STIR yozib bot javobini oldindan
  ko'rish mumkin.

## Yangi tochka ruxsatlari (bot tekshiradi va ruxsat bilan tuzatadi)

Belgi: savdo vakili PRBC ilovasida **«Заявки на точки»**ni ochadi va «Заявок пока нет. Для вашей организации ещё не
включено ни одно подключение к 1С» yozuvini ko'radi, **«+» tugmasi yo'q**. Bu yozuv chalg'itadi: bazalar yoniq,
muammo xodimning sozlamalarida.

PRBC «+» tugmasini quyidagilar bajarilganda ko'rsatadi:

| # | Shart | PRBC'da qayerda | Bot |
|---|---|---|---|
| 1 | Hisob **faol** | Sozlamalar → Foydalanuvchilar | Faol emas — tegmaydi, mutaxassisga (HR qarori) |
| 2 | **Rol** (Employee) va **bo'lim** | xodim kartasi → Bo'lim va rollar | Rol yo'q — Employee. Bo'lim — **savol yozilgan guruhga mos bo'lim** (masalan «LOREAL ROP» guruhi → «LOREAL ROP» bo'limi); asosiy bo'limi bo'lmasa shu bo'lim asosiy bo'ladi, bor asosiy bo'lim o'zgarmaydi |
| 3 | **1C pozivnoy** kerakli bazada | Integratsiyalar → baza → Savdo vakillari | Pozivnoyni xodimdan so'raydi, 1C ro'yxatidan aniq topib biriktiradi. Baza — pozivnoy topilgan baza; ikkalasida bo'lsa — guruh / bo'lim (MDLZ, HEINZ → food; LOREAL, BIC, J&J, COSMOPROF → nonfood) yoki xodim yozgan «food» / «nonfood» |
| 4 | **«Integratsiyalar» ruxsati — Xodim** | Sozlamalar → Modullar → Integratsiyalar → Ruxsatlar | Ruxsat yo'q yoki Ko'ruvchi — Xodim (Ko'ruvchi yarata olmaydi) |

**Standart holat — faqat aniqlash.** Bot muammoni topadi va guruhdagi javobda har shartni yozadi: ✅ joyida,
❌ yetishmaydi («kerak: …, avtomatik o'zgartirish o'chiq — mutaxassis bajaradi»), ⚠️ ogohlantirish. Savol
mutaxassisga o'tadi (PRBC vazifasi ham ochiladi, unda bot topgani yoziladi). **PRBC'da hech narsa o'zgarmaydi.**

**Ruxsat berilgan amal — bot o'zi bajaradi.** Panelda qaysi amalni yoqsangiz, bot shu amalni o'zi qiladi va javobda
nima qilinganini batafsil yozadi (🔧), masalan:

```
🔎 PRBC «Yangi tochka» ruxsatlarini tekshirdim — ISMOILOV SHOHRUH:
✅ PRBC hisobi faol
✅ Rol: employee
🔧 Bo'lim: LOREAL ROP bo'limiga qo'shildi
🔧 «Integratsiyalar» ruxsati: yo'q → Xodim (berildi)
🔧 1C pozivnoy (savdo vakili): 2.1 Навои SR3 (food bazasi) biriktirildi

👉 PRBC ilovasini yopib qayta oching — «Заявки на точки»da baza tanlovi va «+» tugmasi chiqadi.
```

**Pozivnoyni so'rash.** Pozivnoy yo'q bo'lsa bot guruhda so'raydi: *«Pozivnoyingizni to'liq yozing — 1C dagi savdo
vakili nomi (masalan: 2.3 Карши К-3)»*. Xodim to'liq yozmasa (masalan faqat «sr1»), bot mos variantlarni ko'rsatib
qaytadan to'liq yozishni so'raydi; 1C ro'yxatida bo'lmasa — «topilmadi, aynan 1C dagidek yozing». Lotin yoki kirill,
«Qarshi K3» yoki «2.3 Карши К-3» — farqi yo'q. **3 marta** so'ralgandan keyin ham aniq bo'lmasa — mutaxassisga.
Boshqa xodimga biriktirilgan pozivnoyga bot tegmaydi.

**Qaysi savolda.** «yangi tochka qo'sha olmayapman», «new client qo'shish ishlamayapti», «не могу добавить новую
точку», «tochka qo'shish funksiyasi yo'q» yoki yuqoridagi skrinshot. Supervayzer boshqa xodim haqida yozib uni
**@username** bilan belgilasa — o'sha savdo vakili tekshiriladi. Ekran yozuvisiz savolda tugma shartlari joyida bo'lsa
(«tochka qo'shdim, ProTarget'da chiqmayapti») — bot odatdagidek javob beradi. Savolda STIR / 1C kodi bo'lsa — ariza
holati javob beradi.

### Avtomatik amallar (panel → Yangi tochka ruxsatlari)

Har amal alohida yoqiladi, standart — **o'chiq**. Avval «Sinab ko'rish» bilan tekshiring, keyin yoqing.

| Amal | Nima qiladi | Ortga qaytariladimi |
|---|---|---|
| «Integratsiyalar» ruxsati — Xodim | Ruxsati yo'q / Ko'ruvchi savdo vakiliga Xodim. Admin va tekshiruvchiga tegilmaydi | ha |
| Employee roli | Roli yo'q xodimga Employee (butun tashkilot bo'yicha) | ha |
| Guruh bo'limi | Savol yozilgan guruhga mos bo'limga qo'shadi; asosiy bo'lim bo'lmasa — asosiy | ha (asosiy belgisi — qo'lda) |
| 1C pozivnoy biriktirish | Xodim yozgan pozivnoyni aniq topib biriktiradi | ha |
| 1C ma'lumotnomalarini yangilash | Pozivnoy topilmasa — ma'lumotnomani bir marta yangilab qayta qidiradi (soatiga 1 marta) | yo'q (zararsiz) |
| Telegram ma'lumotini yangilash | Savol bergan xodimning Telegram username'i PRBC'dagidan farq qilsa — PRBC'dagi nusxani Telegram'dan qayta o'qitadi (faqat ism, username, rasm) | yo'q (zararsiz) |
| «Vazifalar» moduli — A'zo | «PRBC'da vazifalar ko'rinmayapti / ochilmayapti» — ruxsati yo'q xodimga A'zo | ha |
| «Chat» moduli — A'zo | «PRBC chat ochilmayapti» — ruxsati yo'q xodimga A'zo | ha |
| Arizani 1C ga qayta yuborish | «1C rad etdi» + sababi baza band / javob bermadi — arizani qayta yuboradi. Ma'lumot xatosida yubormaydi | yo'q |
| Mavjud nuqtani marshrutga qayta qo'shish | «Marshrutimga qo'shish» 1C da xato bergan + sababi baza band / javob bermadi — so'rovni qayta navbatga qo'yadi | yo'q |

**Modul savollari** («PRBC'da vazifalar ko'rinmayapti», «Задачи не открываются» + skrinshotda PRBC, «PRBC chat
ochilmayapti») — bot faqat savolda yoki skrinshotda **PRBC** bo'lsa aralashadi (ProTarget ilovasida ham «Задачи»
bor). Ruxsati bor bo'lsa — aralashmaydi; menejer / admin darajasiga tegilmaydi.

**Hisobni tasdiqlash** (pending) — bot tegmaydi: xodim PRBC'ga bog'langan guruhga qo'shilganda PRBC uni o'zi
tasdiqlaydi.

### Tarix va ortga qaytarish

Har tekshiruv va o'zgarish **jurnal**ga yoziladi: vaqt, manba (bot / nazorat / panel), xodim, oldingi va keyingi holat
(masalan «Integratsiyalar: yo'q → employee», pozivnoyning bazasi va 1C id'si, bo'lim yozuvi id'si). Ertaga ma'lumot
o'zgarsa yoki xato bo'lsa — jurnaldagi **«Ortga qaytarish»** shu o'zgarishni PRBC'da bekor qiladi (ruxsat avvalgi
darajaga, rol va bo'lim olib tashlanadi, pozivnoy ro'yxatdan chiqariladi — boshqa qatorlar tekshirilib saqlanadi).
Qaytarish ham jurnalga yoziladi, kim qaytargani bilan.

**Xavfsizlik.** Hech narsa o'chirilmaydi va pasaytirilmaydi. Pozivnoylar ro'yxati har gal PRBC'dan yangidan
o'qiladi, bitta qator qo'shiladi, saqlangach qolganlari o'zgarmagani tekshiriladi; farq bo'lsa — avvalgi ro'yxat
qaytariladi. `food_copy` (test baza) ishlatilmaydi.

### Panel: Support bot → Yangi tochka ruxsatlari (`/prbc/access`)

| Qism | Nima |
|---|---|
| Bot savolda tekshiradi | yoqiq — o'chirilsa bot bu savollarga odatdagidek javob beradi |
| Avtomatik amallar | har amal uchun kalit (standart o'chiq), nima qilishi va qaysi API |
| Sinab ko'rish | xodimni tanlang, savol turi (yangi tochka / PRBC vazifalar / PRBC chat), savol va guruhni yozing — bot javobi aynan qanday bo'lardi va qaysi amallarni bajarardi; PRBC o'zgarmaydi |
| Nazorat | har 60 daqiqada barcha faol savdo vakillari — **faqat hisobot** (o'zgarish faqat xodim savol berganda) |
| Kamchiligi bor xodimlar | nima yetishmaydi, shart bo'yicha filtr |
| Guruh → PRBC bo'limi | qaysi guruh qaysi bo'limga mos (guruh bo'limi amali shu bo'yicha) |
| Jurnal | har tekshiruv va o'zgarish, «Ortga qaytarish» tugmasi |

## Raqam boshqa akkauntga bog'langan (Telegram bog'lash)

**Belgi.** Xodim PRBC botida (yoki ilovadagi «Complete your profile» ekranida) «📱 Поделиться номером» ni bosadi va
oladi: *«⚠️ Этот номер привязан к другой учётной записи PRBC. Обратитесь к администратору.»* / *«This number belongs
to another PRBC account»* — va shu skrinshot yoki matnni support guruhiga yozadi.

**Sabab.** Xodim 1C ga kiritilgach PRBC Kadrlar moduli unga akkaunt ochadi (**A**: login `hr_…`, belgisi 1C,
«Kutilmoqda», Telegram bog'lanmagan, Kirish telefoni — 1C dagi raqam). Xodim keyin PRBC botiga o'zi kirsa — PRBC
yangi bo'sh akkaunt ochadi (**B**: login `tg_<telegram id>`). B ga raqam yozilmoqchi bo'lganda u A da band bo'ladi.

**Bot nima qiladi.**
1. Savolni taniydi (rus / ingliz / o'zbek matn yoki skrinshot). Bu savol «yangi tochka» savolidan oldin tekshiriladi.
2. B ni savol bergan xodimning Telegram ID si bo'yicha, A ni raqam (bo'lmasa F.I.Sh.) bo'yicha topadi, A ga
   bog'langan 1C xodimini `/hr/persons/` dan oladi.
3. Xavfsizlik shartlarini tekshiradi — **hammasi** bajarilsagina o'zgartiradi:

| # | Shart | Bajarilmasa |
|---|---|---|
| G1 | Raqam — xodimning o'zi (bot shaxsiy chatida «📱 Raqamni yuborish» tugmasi orqali o'z kontaktini yuborgan) | qayta so'raydi (3 martagacha), keyin mutaxassisga |
| G2 | A da Telegram bog'lanmagan | mutaxassisga |
| G3 | A — 1C dan kelgan va «Kutilmoqda» (ishlatilmagan) | mutaxassisga |
| G4 | A ga bog'langan 1C xodimi ishlaydi (bo'shatilmagan) | mutaxassisga — raqam boshqa odamga o'tgan bo'lishi mumkin |
| G5 | B bo'sh: 1C ga bog'lanmagan, 30 kundan yangi, faqat Employee roli | mutaxassisga |
| G6 | Raqam bo'yicha faqat bitta akkaunt | mutaxassisga |
| G7 | A va B dagi ism bir odamniki (sozlamada o'chirsa bo'ladi) | mutaxassisga |

4. Amallar yoqilgan bo'lsa (pastda), tartib bilan bajaradi va har qadamdan keyin PRBC'dan qayta o'qib tekshiradi:
   1C xodimini A dan uzish → A dagi Kirish telefonini **bo'shatish** (raqam buzilmaydi, eski qiymat jurnalda) → 1C
   xodimini B ga bog'lash → (ixtiyoriy) B ga raqamni yozish → (ixtiyoriy) bo'sh A ni bloklash. Biror qadam xato
   bersa — qilinganlari teskari tartibda qaytariladi, yarim holat qolmaydi, savol mutaxassisga o'tadi.
5. Javob guruhda (va bot shaxsiy chatida): «Akkauntingiz 1C ma'lumotlaringiz bilan bog'landi ✅ PRBC ilovasini to'liq
   yopib qayta oching» va nima qilingani. B ga raqam yozish o'chiq bo'lsa — «PRBC botida «📱 Поделиться номером» ni
   qayta bosing».

**Standart holat.** Hamma amallar **o'chiq**: bot A/B ni topadi, G2–G7 natijasini va admin nima qilishi kerakligini
yozadi, savol mutaxassisga o'tadi (kartochkada F.I.Sh., Telegram ID, raqam, A va B havolalari). Raqam so'ralmaydi —
xodimni ortiqcha bezovta qilmaslik uchun raqam faqat uchala asosiy amal yoqilganda so'raladi.

**Raqam qanday olinadi.** Guruhdagi javobda «📱 Raqamni yuborish» tugmasi bor — u bot shaxsiy chatini ochadi, u yerda
Telegram'ning «raqamni yuborish» tugmasi chiqadi (raqam Telegram'dan o'zi olinadi). Boshqa odamning kontakti
(forward) qabul qilinmaydi. Skrinshotdagi raqam faqat qidirish uchun — tasdiqlangan hisoblanmaydi.

### Amallar (panel → Yangi tochka ruxsatlari → «Raqam boshqa PRBC akkauntiga bog'langan»)

| Amal | Nima qiladi | Ortga qaytarish |
|---|---|---|
| 1C xodimini eski akkauntdan uzish | `/staff` dagi «Bog'lanishni uzish» | qayta bog'lanadi |
| Eski akkauntdagi raqamni bo'shatish | Kirish telefoni tozalanadi | eski raqam qaytariladi |
| 1C xodimini yangi akkauntga bog'lash | 1C ma'lumotlari B ga o'tadi | uziladi |
| Yangi akkauntga raqamni yozish (ixtiyoriy) | tasdiqlangan raqam B ga | eski qiymat |
| Bo'sh eski akkauntni bloklash (ixtiyoriy) | A bloklanadi (o'chirilmaydi) | qayta yoqiladi |

Asosiy uchta amal **birga** yoqilgandagina bot o'zgartiradi (bittasi o'chiq bo'lsa — faqat aniqlaydi). Ortga
qaytarishni teskari tartibda bajaring: avval «yangi akkauntga bog'lash», keyin «raqam», keyin «uzish».

**Sozlamalar:** «Bot shu savolni tekshiradi» (standart yoqiq — o'chirilsa odatdagi javob), «Ism tekshiruvi qat'iy (G7)»
(standart yoqiq).

**Panelda:** *Bitta odamni tekshirish* (F.I.Sh. / telefon / PRBC id → A, B va G2–G7), *Sinov rejimi* (Telegram ID yoki
F.I.Sh. + raqam → bot javobi va amallar, PRBC o'zgarmaydi), *Nazorat* — bir xil F.I.Sh. li «1C, Kutilmoqda,
Telegramsiz» va «tg_, 1C siz» akkauntlar ro'yxati (har nazoratda, faqat hisobot).

**Admin qo'lda (bot to'xtasa):** `prbc.uz/staff` → xodim → «Bog'lanishni uzish» (A dan) → `settings?tab=users` da A
ning Kirish telefonini tozalash → 1C xodimini B akkauntga bog'lash → xodim botda raqamni qayta yuboradi. Raqamni
«yarmini o'chirib» buzmang.

**Tekshirilmagan.** Amallar real PRBC'da hali sinalmagan (endpointlar prbc.uz sahifasi va API sxemasidan olingan).
Birinchi marta yoqishdan oldin «Sinov rejimi» da bitta xodimni tekshiring va jurnalni kuzating; ayniqsa PRBC Kirish
telefonini bo'sh qiymatga o'zgartirishga ruxsat beradimi — bermasa bot hammasini qaytaradi va mutaxassisga o'tadi.

## Sozlamalar

PRBC sozlamalari sahifasi:

| Sozlama | Hozir | Izoh |
|---|---|---|
| Telefon, parol, manzil | administrator akkaunti | Parol shifrlangan; "Ulanishni tekshirish" — qaysi manbalar ochiq |
| Sinxronlash (daqiqa) | 30 | 1C xodimlari |
| Standart loyiha | 36 «STAR GROUP \| IT Поддержка» | Guruhga bog'lanmagan savollar |
| Standart ijrochilar | 167 (Xusniddin) | Oxirgi zaxira |
| Kuzatuvchilar | 2 (Kamoliddin aka) | + "Meni kuzatuvchi qilish" |
| Telegram → PRBC moslash | `it_stargroup=167, stargroupsaid=51, jo6777=48, timurdoskabilov=49, ganiyevxusniddin=167` | |
| Bo'shaganni avtomatik belgilash, qurilmalar ro'yxati | yoqiq | |
| PRBC'da bajarildi — savol hal bo'ldi | yoqiq | |
| Guruhga "vazifa ochildi" / "bajarildi" javobi | o'chiq / yoqiq | |
| Savol fayllarini biriktirish | yoqiq | |
| Mijoz holatini PRBC'dan tekshirish | yoqiq | |
| **Vazifa nazorati:** muddat, ustuvorlik, ish soatlari va kunlari | 10 daq, High, 09–18, Du–Sha | |
| Odamga uzatilgan har savolga vazifa | yoqiq | Support sozlamasi bilan bir xil |
| Savol holati vazifaga o'tadi | yoqiq | |
| Muddat o'tsa — ogohlantirish | yoqiq | |
| **Guruh → loyiha** jadvali | har guruh | Vazifa (yoqiq/o'chiq), loyiha, ijrochi (avto yoki tanlangan); eski guruhlar belgilangan |

## Muammolar

| Belgi | Sabab va yechim |
|---|---|
| "Worker ishlamayapti" | `foydali-prbc` servisi to'xtagan — Servislar markazidan qayta ishga tushiring |
| Vazifa ochilmadi | Guruhda vazifa o'chiq / eski guruh / savol aniq emas; Vazifalar nazoratida "vazifasiz savollar" bo'lsa — "Hammasiga vazifa ochish" |
| Ijrochi noto'g'ri | Toifa mas'ulini (Support sozlamasi) yoki guruh ijrochisini (jadval) to'g'rilang |
| Status o'zgarmadi | PRBC rad etgan bo'lishi mumkin — nazoratda ⚠ sababi |
| Bot «yangi tochka» savoliga tekshiruv yozmadi | Panelda kalit o'chiq / PRBC javob bermadi (bot odatdagidek javob beradi) / xodimning Telegram'i PRBC'ga bog'lanmagan — bot «foydalanuvchi topilmadi» deb mutaxassisga uzatadi |
| «Raqam boshqa akkauntga bog'langan» — bot hal qilmadi | Javobda ❌ bo'lgan shart (G1–G7) sababi; amallar o'chiq bo'lsa — admin qo'lda (yuqoridagi bo'lim). Jurnalda xato bo'lsa — o'zgarishlar avtomatik qaytarilgan |
| Pozivnoy biriktirilmadi | Jurnalda sababi: boshqa xodimda (supervayzer bilan aniqlang), 1C ro'yxatida yo'q (Integratsiyalar → «Ma'lumotnomalarni yangilash», bo'lmasa 1C mas'uli) |
| PRBC "Request was throttled" | PRBC so'rovlarni vaqtincha cheklagan — tizim keyingi aylanishda qayta uradi |
