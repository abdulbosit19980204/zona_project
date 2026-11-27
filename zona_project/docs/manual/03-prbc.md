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
| Pozivnoy biriktirilmadi | Jurnalda sababi: boshqa xodimda (supervayzer bilan aniqlang), 1C ro'yxatida yo'q (Integratsiyalar → «Ma'lumotnomalarni yangilash», bo'lmasa 1C mas'uli) |
| PRBC "Request was throttled" | PRBC so'rovlarni vaqtincha cheklagan — tizim keyingi aylanishda qayta uradi |
