# O'zgarishlar tarixi

> Tizimga kiritilgan o'zgarishlar — eng yangisi tepada. Har deploy bilan shu yerga yoziladi.

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
