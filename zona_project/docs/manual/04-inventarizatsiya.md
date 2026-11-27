# IT inventarizatsiya

> Filiallardagi IT qurilmalarini hisobga olish: kim nima qiladi, loginlar, qurilma qo'shish, katalog (faol/nofaol
> turlar), xodimlar va tasdiqnomalar, import/eksport.

Menyu: **IT inventarizatsiya** (faqat huquqi borlarga ko'rinadi). Filial xodimlari telefonda mobil ko'rinishda
ishlaydi (`/inventory`), boshqaruvchi — kompyuter ko'rinishida (`/inv`).

## Rollar

| Daraja | Nima qila oladi |
|---|---|
| **Boshqaruvchi (IT)** | Hamma narsa: barcha filiallar, katalog, loginlar, import/eksport, tarix |
| **Rahbar / filial direktori** (faqat ko'rish) | O'z filiali(lari)ni ko'radi, hech narsa o'zgartirmaydi. Filial biriktirilmagan rahbar hammasini ko'radi |
| **Filial xodimi** (to'plovchi) | O'z filialiga qurilma, xodim, rasm qo'shadi va tahrirlaydi |

## Loginlar

- Loginlar va huquqlar → **"Filiallarga login yaratish"** — har filialga `inv.<filial>` login (parol avtomatik).
- **"Direktorlarga login (faqat ko'rish)"** — har filialga `dir.<filial>`.
- **Loginlar fayli** (Excel): har filial qatorida xodim va direktor login/parollari yonma-yon + to'liq ro'yxat.
  Parollar faqat shu faylda — boshqa joyda ko'rsatilmaydi. Havolalarni IT shu fayl orqali yuboradi.
- Parolni tiklash, bloklash, filial biriktirish — "Tahrirlash" orqali.

## Qurilma qo'shish (filial xodimi)

1. Qurilma turini tanlang (faqat **faol** turlar ko'rinadi), brend, model, seriya raqami (qayerda yozilganini tur
   tavsifi aytadi), soni, holati (ishlayapti / ta'mirga muhtoj / ishlamaydi …), joyi, kimda turgani.
2. Turning **maxsus maydonlari** (masalan, kamerada: turi, megapiksel, joylashuvi; kompyuterda: protsessor, RAM, disk).
   Ro'yxatda yo'q qiymatni yozib qo'shish mumkin.
3. Rasm (telefonda siqib yuklanadi). Seriya raqami takrorlansa — ogohlantiradi.
4. Har qurilmaga inventar raqami beriladi; o'chirilgani tiklanadi; hamma o'zgarish **Tarix**da.

## Katalog (boshqaruvchi)

- **Qurilma turlari** guruhlar bo'yicha (Kompyuter, Periferiya, Printer, Tarmoq, Elektr, Xavfsizlik, Aloqa, Savdo,
  Multimedia, Videokuzatuv). Filtr: Hammasi / Faol / Nofaol.
- Har tur yonidagi **kalit** — bir bosishda yoqish/o'chirish (faqat holat o'zgaradi). Guruhda nofaol tur bo'lsa —
  **"Guruhni yoqish (n)"**.
- Nofaol tur xodimlar formasida ko'rinmaydi, lekin kiritilgan qurilmalar saqlanadi.
- Turni ochib: nomi (UZ/RU), guruh, tavsif, seriya raqami qayerda, brendlar, maxsus maydonlar, **Faol** belgisi.
- Hozir: 35 faol (asosiy 30 + videokuzatuv 5), 30 nofaol (server, NAS, planshet, telefoniya, savdo jihozlari va
  boshqalar — tekshirib yoqiladi). Tashkilotlar (loyihalar) va joylar ro'yxati ham shu yerda.

## Xodimlar va tasdiqnomalar

- Filial xodimlari ro'yxati (import/eksport, shablon, kontaktlardan olish). Bo'shagan xodim PRBC orqali avtomatik
  nofaol bo'ladi.
- **Tasdiqnoma:** xodim havolani ochib, o'ziga biriktirilgan qurilmalarni ko'radi va imzo bilan tasdiqlaydi yoki
  e'tiroz yozadi. Qurilmalar keyin o'zgarsa — tasdiqnoma "eskirgan" bo'ladi.
- **Havolani IT bo'limi yuboradi** (ichki tizim orqali), filial xodimi emas. Shuning uchun alohida "Tasdiqnomalar"
  bo'limi menyuda yo'q. Filial xodimining vazifasi — qurilma egasining **telefoni va Telegramini** to'g'ri yozish.
- Havolalar fayli: **Import / Eksport → "Tasdiqlash havolalari (Excel)"** (faqat boshqaruvchi). Qurilmasi bor har bir
  xodimning havolasi, telefoni, Telegrami va holati; yo'q havolalar avval avtomatik yaratiladi.
- Xodimlar ro'yxatida imzo holati (kutilmoqda / imzolangan / e'tiroz) va tasdiqnomani ko'rish qoladi.

## Filiallar, natijalar, eksport

- **Filiallar:** holati (rejada / jarayonda / yakunlandi), o'tkazuvchisi va loginlari.
- **Natijalar va analitika:** filiallar holati, sust filiallar, kunlik faollik, kim qancha ish qilgani — rahbarlarga.
- **Import / Eksport:** CSV, Excel va asl shablon formatida; to'ldirilgan fayldan yuklash (maxsus maydonlar ham).
- Interfeys ikki tilda (o'zbek / rus) — xodim o'zi tanlaydi.

## Filial xodimlari uchun qo'llanmalar

Tayyor fayllar (`D:\StarGroup\IT_inventarizatsiya\Qollanma\`), filiallarga yuborish uchun:

- **PDF / HTML** — o'zbek va rus tilida, skrinshotlar bilan: filial xodimi uchun (kirish → qurilma qo'shish →
  yakunlash) va qurilma egasi uchun (havolani ochish → tekshirish → imzo).
- **Video** (`video\`) — telefon uchun vertikal, ovozli, ~2,5 daqiqa: `IT_inventarizatsiya_video_UZ.mp4`,
  `IT_inventarizatsiya_video_RU.mp4`. Qayta yasash skriptlari `video\manba\` da.
- Interfeys o'zgarsa — skrinshot va videoni qayta yasash kerak (demo bazada, prod bazaga tegilmaydi).
