# Foydali (zona_project) — ishlash qoidalari

## Qo'llanma har o'zgarishda yangilanadi
- Tizimning to'liq yo'riqnomasi: `zona_project/docs/manual/*.md`. Panelda: chap menyu → **Qo'llanma** (`/docs`).
- Har funksiya, sozlama yoki oqim o'zgarganda **shu commit ichida**:
  1. tegishli bobni yangilang (support-bot, prbc, inventarizatsiya, zona, texnik);
  2. `07-ozgarishlar.md` ga sana bilan qisqa yozuv qo'shing (eng yangisi tepada).
- Yangi bob: `NN-slug.md`, birinchi qator `# Sarlavha`, ikkinchisi `> qisqa tavsif`; kerak bo'lsa `frontend/src/lib/nav.ts`
  dagi `DOCS_NAV` ga qo'shing.
- Qo'llanma o'zbek tilida, foydalanuvchi uchun: nima qiladi, qayerda sozlanadi, standart qiymat, muammo bo'lsa nima qilish kerak.

## Prod xavfsizligi (foydali.xisobchim.uz — ishlab turibdi)
- Deploydan va har ma'lumot o'zgarishidan oldin bazaning zaxirasi; migratsiyalar faqat qo'shuvchi; server bazasi qayta yaratilmaydi.
- bio-lab.uz ga tegilmaydi. Kalit/parollar repo'ga yozilmaydi.
- Tekshiruv: `manage.py test prbc inventory zona support`, `npx tsc --noEmit`, `npx eslint`, `makemigrations --check`.
