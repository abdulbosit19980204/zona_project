# Umumiy ko'rinish

> Foydali paneli nimalardan iborat, qaysi modul nima qiladi va qo'llanmadan qanday foydalanish kerak.

**Foydali** (foydali.xisobchim.uz) — StarGroup IT bo'limining yagona paneli. U bir nechta mustaqil moduldan iborat va
chap menyuda har biri alohida bo'lim bo'lib ko'rinadi.

## Modullar

| Modul | Nima qiladi | Kim ishlatadi | Qo'llanma |
|---|---|---|---|
| **Support bot** | Telegram guruhlaridagi agent va supervayzerlar savollariga avtomatik javob beradi, bilim bazasini yuritadi, javob topilmasa xodimga uzatadi | IT support, administrator | [Support bot](/docs/support-bot) |
| **PRBC vazifalar** (Support bot ichida) | Savollardan PRBC'da vazifa ochadi, muddat va holatini nazorat qiladi, 1C xodimlarini sinxronlaydi, mijoz holatini PRBC'dan tekshiradi | IT rahbari, administrator | [PRBC va vazifalar](/docs/prbc) |
| **IT inventarizatsiya** | Filiallardagi IT qurilmalarini xodimlar telefondan kiritadi; boshqaruvchi nazorat qiladi, eksport qiladi | Filial xodimlari, direktorlar, IT | [IT inventarizatsiya](/docs/inventarizatsiya) |
| **Mas'uliyat platformasi (Zona)** | Kompaniya tuzilmasi: bo'limlar, xodimlar, jarayonlar, kim nimaga javobgar; savolga kim javob berishini topish | Rahbarlar, IT | [Mas'uliyat platformasi](/docs/zona) |
| **QR Drive** | Fayllarni QR orqali almashish xizmati (alohida servis) | IT | — |
| **Qo'llanma** | Shu hujjat — butun tizimning yo'riqnomasi | Hamma | — |

## Asosiy oqim: savoldan yechimgacha

1. Agent Telegram guruhida savol yozadi (matn, skrinshot yoki ikkalasi).
2. **Support bot** savolni tushunadi: matn, rasm turi, rasmdagi yozuv (OCR), qizil xato yozuvi.
3. Javob bilim bazasida bo'lsa — darhol javob beradi (standart holat aynan bazadagi matn bilan).
4. Savolda mijozning STIR, JShShIR yoki 1C kodi bo'lsa — PRBC'dan mijoz arizasining **jonli holatini** o'qib qo'shadi.
5. Javob topilmasa — savol xodimga uzatiladi va **PRBC vazifasi** ochiladi (kimga tegishli bo'lsa — o'shanga,
   o'z guruhining loyihasida, 10 daqiqalik muddat bilan).
6. Xodim javob yozsa — vazifa «In Progress», savol hal bo'lsa — «Done». Hammasi avtomatik.
7. **Vazifalar nazorati** sahifasida rahbar ochiq vazifalarni, muddati o'tganlarni va xodimlar statistikasini ko'radi.

## Kirish va huquqlar

- Panelga login va parol bilan kiriladi. Rollar: **ko'ruvchi**, **muharrir**, **administrator**.
- PRBC bo'limlari, Support sozlamalari va inventar boshqaruvi faqat **administrator**ga ko'rinadi.
- Inventarizatsiya alohida loginlarga ega (filial xodimi, direktor — faqat ko'rish, boshqaruvchi).

## Qo'llanmadan foydalanish

- Chap menyu → **Qo'llanma**. Har bob alohida; yuqoridagi qidiruv barcha boblardan so'z qidiradi.
- O'ng tomonda bob mundarijasi bor (katta ekranda).
- Qayerda nima sozlanishi skrinshotlar bilan — [Sozlamalar qo'llanmasi](/docs/sozlamalar). Rasmni bossangiz, shu
  sahifada kattalashtirib ko'rish oynasi ochiladi.
- Qo'llanma kod bilan birga yangilanadi: tizimga har o'zgarish kiritilganda tegishli bob ham yangilanadi va
  [O'zgarishlar tarixi](/docs/ozgarishlar)ga yoziladi. Fayllar: `docs/manual/*.md`.

## Muhim qoidalar (har doim)

> Tizim ishlab turibdi — xodimlar ma'lumot kiritmoqda. Har deploy va ma'lumot o'zgarishidan oldin bazaning zaxirasi
> olinadi, migratsiyalar faqat **qo'shuvchi** (hech narsa o'chirilmaydi), server bazalari hech qachon qayta
> yaratilmaydi. Shu serverdagi **bio-lab.uz** saytiga tegilmaydi.
