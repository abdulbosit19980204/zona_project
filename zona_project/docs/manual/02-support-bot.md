# Support bot

> Telegram guruhlaridagi savollarga avtomatik javob: savol qanday tushuniladi, bilim bazasi, guruh sozlamalari,
> "hal bo'ldimi?" oqimi va barcha sozlamalar.

## Menyu bo'limlari

| Bo'lim | Nima uchun |
|---|---|
| **Guruh savollari** | Barcha savollar: bot javobi, kim javob berdi, holati (javob berildi / odamga uzatildi / hal bo'ldi). Raqam — javob kutayotgan savollar |
| **Tasdiqlash navbati** | Bilim bazasiga yangi javob nomzodlari va tahrirlar — tasdiqlanmaguncha bot ularni ishlatmaydi |
| **Bilim bazasi** | Barcha javoblar (oddiy savol-javob va standart holatlar/shablonlar) |
| **Rasm turlari** | Skrinshot turlarini o'rgatish (masalan, ProTarget xato oynalari) |
| **Tahlil** | Savollar statistikasi: guruhlar, toifalar, javob tezligi, bot ulushi |
| **Konstruktor** | Savollarni turli kesimda o'rganish |
| **PRBC vazifalar** | Vazifalar nazorati, vazifalar, 1C xodimlari, jurnal — [PRBC qo'llanmasi](/docs/prbc) |
| **Botlar va sozlamalar** | Botlar, guruhlar, AI, vazifalar va boshqa sozlamalar |

## Savol qanday javob oladi (zinapoya)

Bot eng arzon va eng aniq bosqichdan boshlaydi:

1. **Shablon (standart holat)** — shartlar (kalit so'z yoki regex) matnda yoki rasm yozuvida topilsa. Javob bazadagi
   matn bilan **aynan** yuboriladi — AI qayta yozmaydi.
2. **Rasm turi** — skrinshot o'rgatilgan namunaga o'xshasa (rasm xeshi). Ekrandagi matn boshqa holatni aytsa — matn
   ustun (masalan, "Tasdiq kutilmoqda" "Request was throttled" bilan adashmaydi).
3. **Qizil xato yozuvi** — skrinshotdagi qizil matn eng aniq belgi; javob shu bo'yicha.
4. **Bilim bazasidan o'xshash savol** — savol ko'rinishlari bilan o'xshashlik chegarasidan (standart 72%) yuqori bo'lsa.
5. **AI** — bilim bazasidagi eng yaqin javoblar, xodimlarning o'xshash savollarga bergan javoblari va mas'ullar
   ro'yxatiga tayanib javob tuzadi. Ishonchi past bo'lsa — javob bermaydi.
6. **Odamga uzatish** — hech biri ishonchli bo'lmasa: "qabul qilindi", mas'ul @ bilan belgilanadi va
   [PRBC vazifasi](/docs/prbc) ochiladi.

Qo'shimcha:
- **Mijoz holati (PRBC):** savol yoki skrinshotda STIR (9 raqam), JShShIR (14 raqam) yoki 1C kodi (UZ-…) bo'lsa,
  bot PRBC'dan mijoz arizasining jonli holatini o'qib javob boshiga qo'shadi. Batafsil — [PRBC](/docs/prbc#mijoz-holati-jonli-tekshiruv).
- **Ma'lumot ekrani:** skrinshot "Торговая точка … отправлена на модерацию!" bo'lsa, ostidagi "Qo'shib bering, Navoiy
  SRZ" / "Tasdiqlab bering" kabi iltimos alohida savol hisoblanmaydi. Bot xodimga uzatmaydi, **moderatsiya standart
  javobini** beradi: nuqtani Pro-target tasdiqlaydi va u o'zi qo'shiladi. Matn bilim bazasidagi boshqa savolga aniq mos
  kelsa (masalan, "perechisleniya qo'shib bering"), shu javob beriladi. Qaysi yozuv ma'lumot ekrani hisoblanadi —
  bilim bazasida **Avto yopish (daqiqa)** 0 dan katta bo'lganlari (moderatsiya yozuvida 30).
- **OCR imlosi:** Tesseract ruscha qisqa so'zni ba'zan lotin harflari bilan o'qiydi ("Ha" — "На" o'rniga). Kirillcha so'z
  yonidagi bunday so'z avtomatik kirillchaga aylantiriladi.
- **Imlo:** "qóshb bómayapti", kirill/lotin, ruscha — bir xil tushuniladi (normalizatsiya va savol ko'rinishlari).
- **Albom va ketma-ket xabarlar** bitta savol sifatida olinadi (sozlamada soniya).
- **Takror savol** — shu odam shu savolni qisqa vaqtda qayta yuborsa, bot ikkinchi marta javob bermaydi.

## Bilim bazasi

Har yozuv — bitta mavzu.

| Maydon | Ma'nosi |
|---|---|
| **Turi** | *Savol-javob* (o'xshash savol bo'yicha) yoki *Standart holat / shablon* (shartlar bo'yicha, javob aynan yuboriladi) |
| **Sarlavha** | Mavzu nomi (vazifa sarlavhasida ham ishlatiladi) |
| **Savol ko'rinishlari** | Odamlar bu savolni qanday yozadi — qancha ko'p bo'lsa, shuncha yaxshi topadi |
| **Shartlar** | Shablon uchun: oddiy ibora, `a && b` (ikkalasi ham bo'lsin) yoki `re:regex` (masalan, `re:(?s)\A(?!.*отклонен).*добавлен\w* в маршрут`) |
| **Ajratib olinadigan maydonlar** | Regex nomli guruh bilan matndan qiymat olish (javobda `{nom}`) |
| **Javob (uz / ru)** | Savol tiliga qarab yuboriladi |
| **Mas'ul** | Mavzu egasi (xodim yoki jamoa). Javob topilmasa shu odam belgilanadi; vazifa ijrochisi ham shundan aniqlanadi |
| **Chatda javob** | Umumiy sozlama / har doim / faqat o'rganish |
| **Vazifa yaratiladi** | Bu turdagi savolga javob berilsa ham PRBC vazifasi ochiladi (odam harakati kerak bo'lgan holatlar) |
| **Vazifa ijrochisi** | Bo'sh bo'lsa — mas'ul |
| **Avval so'raladigan ma'lumot** | Javobdan oldin agentdan so'raladigan narsa (masalan, nuqta kodi) |
| **Fayllar** | Javob bilan birga yuboriladigan rasm/video |

Holatlar: **yangi → ko'rib chiqilmoqda → tasdiqlangan**. Bot faqat tasdiqlangan yozuvlarni ishlatadi (soya rejimida
ko'rib chiqilayotganlarini ham sinaydi). Har o'zgarish versiyada saqlanadi.

> Mavjud javob matnlari foydalanuvchi so'ramaguncha o'zgartirilmaydi. Standart holatlarda AI "ijod qilmaydi" — javob
> bazadagi matnning o'zi.

## Guruh sozlamalari

Botlar va sozlamalar → **Guruhlar**. Har guruh uchun:

| Sozlama | Ma'nosi |
|---|---|
| **Rejim** | *Bot rejimi* (botnikini oladi), *O'chiq*, *Faqat yig'ish* (hech kimga yozmaydi), *Soya* (javob taklifi faqat admin chatiga), *Jonli* (guruhga javob) |
| **Tahlilga qo'shish** | O'chiq bo'lsa — guruh savollari statistikaga kirmaydi (masalan, VAZIFALAR — test guruhi) |
| **PRBC vazifa** | O'chiq bo'lsa — bu guruh savollaridan vazifa ochilmaydi (VAZIFALAR — o'chiq; ROP guruhlari — yoqiq) |
| **Eski guruhni yo'naltirish** | Eski guruhda bot savolga javob bermaydi, yozgan odamni yangi guruh havolasiga yo'naltiradi. Eski guruhdan **vazifa ochilmaydi** |

Bot guruhda **admin** bo'lishi kerak (yoki BotFather'da privacy o'chiq) — aks holda barcha xabarlarni ko'rmaydi.

## "Hal bo'ldimi?" oqimi (savol yopilishi)

- Savol egasi "rahmat", "готово", "ishladi" yozsa — bot 👍 qo'yadi va savol **hal bo'ldi**.
- "ishlamadi", "не помогло" — savol yana xodimga qaytadi.
- Xodim javob yozgandan keyin (standart 10 daqiqa) bot savol egasidan "hal bo'ldimi?" deb so'raydi (tugmalar).
- Savol egasi javob bermasa — javob bergan xodimdan so'raladi; "hal bo'lmadi / jarayonda" — vaqt o'tib qayta so'raladi
  va xodim eslatiladi (ko'pi bilan 3 marta), keyin admin chatiga.
- Xodim savolga istalgan reaksiya qo'ysa — savol qabul qilingan hisoblanadi.
- Savol holati PRBC vazifasiga avtomatik o'tadi (hal bo'ldi → Done) — [PRBC](/docs/prbc#holat-sinxroni).

## O'z-o'zini o'qitish

- Bot xodimlarning javoblaridan o'rganadi: e'tirozsiz javoblardagi savol ko'rinishlari bazaga qo'shiladi, xodim
  tuzatishi AI orqali javobga kiritiladi (daraja sozlamada). Hammasi versiyada qoladi.
- Javob ostidagi **"⚠️ Xato javob"** tugmasi (xodimlar uchun) — noto'g'ri javob guruhda yashiriladi va tasdiqlash
  navbatiga tushadi.
- Rasm turlari xodim javobi va ishonchli moslikdan avtomatik o'rgatiladi.

## Barcha sozlamalar (Botlar va sozlamalar)

### Javob berish
| Sozlama | Standart | Izoh |
|---|---|---|
| Bot chatda javob beradigan savollar | hammasi | *hammasi* / *faqat bazadagi* / *faqat standart holatlar* |
| AI javoblari yoqilgan | yoqiq | AI kunlik limiti (200) va minimal ishonch (70%) bilan |
| AI asosiy javob beradi | yoqiq | Bazadan moslik 95% dan past bo'lsa javobni AI tuzadi |
| Bazadan javob: o'xshashlik chegarasi | 72% | |
| Qoida bo'yicha javob: ishonch chegarasi | 60% | |
| Javob imzosi | 🤖 Avto-javob | |
| Javob tagida test eslatmasi | yoqiq | "avto-javob, test rejimi, fikringiz muhim" |
| Javoblarni har safar biroz boshqacha yozish | — | Standart holatlarga ta'sir qilmaydi |
| Sekin javobda oraliq xabar | — | "ko'ryapman…" |
| Javobni yig'ish | 3 daqiqa | O'qilgach, javob bir qatorga yig'iladi |
| Toifa bo'yicha mas'ul | aksiya, to'lov, qoldiq → Saidabror; login → Xusniddin | Butun tizimda ustun; vazifa ijrochisi ham shundan |

### Jonli rejim
| Sozlama | Izoh |
|---|---|
| Javob topilmasa «qabul qilindi» | Guruhga yoziladi |
| Mas'ulni @ bilan belgilash / savol beruvchini belgilash / supervayzerni belgilash | |
| 👍/👎 tugmalari, «⚠️ Xato javob» tugmasi | |
| Kerakli ma'lumot yo'q bo'lsa avval so'rash | |
| Xodim reaksiyasi — savol qabul qilindi | |

### Rasm va OCR
| Sozlama | Standart |
|---|---|
| Rasmdagi matnni o'qish (OCR) | yoqiq |
| Rasm turini namunalar bo'yicha tanish / chegarasi | yoqiq / 10 |
| Rasmni avtomatik o'rgatish | yoqiq |
| Asl rasmni saqlash / eskiz | 3 kun |
| Bot javoblari skrinshotlari | 90 kun |

### Savol yopilishi
| Sozlama | Standart |
|---|---|
| "Hal bo'ldimi?" so'rash | yoqiq, 10 daqiqadan keyin |
| "Rahmat" — 👍 va yopish | yoqiq |
| Javob bergan xodimdan so'rash | sozlamada (daqiqa) |
| Qayta so'rash va eslatish | 120 daqiqa, ko'pi bilan 3 marta |
| Ish vaqti (eslatmalar uchun) | 09:00–19:00, Du–Ju |

### Xabarlarni birlashtirish
| Sozlama | Standart |
|---|---|
| Bir xodimning ketma-ket rasmlari bitta savol | 90 soniya |
| Bir muallifning ketma-ket xabarlari | 12 soniya |
| Bitta suhbat oynasi | 15 daqiqa |
| Bir vaqtda qayta ishlanadigan savollar | 10 |

### PRBC vazifalari (Support tomoni)
| Sozlama | Izoh |
|---|---|
| PRBC vazifalari yoqilgan, rejim | Rejim **api** — vazifani tizim o'zi PRBC API orqali ochadi |
| Odamga uzatilgan har bir savolga vazifa | Yoqiq — bot javob bera olmagan har savol vazifa bo'ladi |
| Vazifa yaratiladigan bo'limlar / xodimlar | Eski usul (mas'ul shu bo'limda bo'lsa) — hozir "har savolga" yoqiq |

Qolgan vazifa sozlamalari — [PRBC sozlamalari](/docs/prbc#sozlamalar).

### Tarix (eski xabarlardan o'rganish)
Telegram akkaunt orqali **faqat o'qish** rejimida guruh tarixi olinadi (API ID/hash). Necha kunlik (30), rasmlarni ham
o'qish, bitta guruhdan ko'pi bilan (5000), tungi oyna (22:00–07:00).
