# Server va texnik

> Server, servislar, fayllar joylashuvi, zaxira, yangilash (deploy) tartibi, xavfsizlik qoidalari va kod tuzilishi.

## Arxitektura

```
Brauzer ──► nginx (HTTPS) ──► Next.js panel (pm2 foydali-frontend, 3020)
                         └──► /api/* ──► Django + DRF + Channels (foydali-backend, 8020) ──► SQLite
Telegram ◄──► foydali-support-bot (Support bot)        PRBC (prbc.uz) ◄──► foydali-prbc (worker)
```

| Qism | Texnologiya |
|---|---|
| Panel | Next.js 16, React 19, TypeScript, Tailwind, shadcn/ui, TanStack Query, next-intl (uz/ru/en) |
| Backend | Django 6, DRF, SimpleJWT, Channels (WebSocket), SQLite |
| AI | Anthropic Claude (asosiy), Gemini (zaxira); OCR — rasm matni |

## Servislar (foydali.xisobchim.uz)

| Servis | Vazifasi |
|---|---|
| `foydali-backend` | API va WebSocket |
| `foydali-frontend` (pm2) | Panel |
| `foydali-support-bot` | Telegram support boti |
| `foydali-prbc` | PRBC worker: vazifalar, holat sinxroni, 1C xodimlari |
| `foydali-qrdrive-api / worker / bot` | QR Drive |
| `foydali-control` | Servislar markazi (`/control/`) — ishga tushirish, to'xtatish, loglar |
| `foydali-backup.timer` | Har kuni 03:30 zaxira, 14 kun saqlanadi |
| `foydali-close-review.timer` | Yakshanba 03:45 (zaxiradan keyin): `support_close_review --older-than 7` — 7 kundan eski review navbatini yopadi; rad etilgan id'lar `/var/lib/foydali/backups/review_rejected_ids_YYYYMMDD.txt`. Natija: `journalctl -u foydali-close-review` |

Servis to'xtasa — panel chap pastidagi **Servislar markazi**dan qayta ishga tushiriladi.

## Fayllar

- Kod: `/root/zona_project/zona_project` (servislar `foydali` foydalanuvchisi nomidan ishlaydi).
- Sozlamalar va kalitlar: `/etc/foydali/` (`foydali.env` va boshqalar) — **hech qachon repo'ga yozilmaydi**.
- Baza: `/var/lib/foydali/db.sqlite3`; zaxiralar: `/var/lib/foydali/backups/`.
- Qo'llanma: `docs/manual/*.md` (shu hujjat).

## Yangilash (deploy) tartibi

1. Lokal: testlar (`manage.py test prbc inventory zona support`), `tsc`, `eslint`, `makemigrations --check`.
2. Commit → push (`main`).
3. Serverda **bazaning zaxirasi** (`sqlite3 .backup`) + `integrity_check` = ok.
4. `foydali-setup.sh` (git pull, paketlar, migratsiya, frontend yig'ish, servislarni qayta ishga tushirish).
5. Tekshiruv: sahifalar 200, servislar active, xatolar yo'q, **bio-lab.uz** ishlayapti.
6. **Semantik qidiruv modeli** (bir marta): `manage.py support_semantic --download` (~120 MB,
   `/var/lib/foydali/models/`), keyin `--build` (indeks), `--query "matn"` (sinov), `--tune` (chegara × farq:
   qamrov, aniqlik va «standarti yo'q savol»ga xato javob ulushi; oxirida tavsiya), `--eval 94` (AI'siz qamrov semantik
   bilan va usiz; savolning o'zi indeksda bo'lsa hisobga olinmaydi). Paketlar: `pip install .[semantic]` (onnxruntime,
   tokenizers, numpy — torch kerak emas). Model 2 ta CPU oqimida ishlaydi (bio-lab bilan bir server).
   O'lchov (2026-11-28): indeks 2125 qator — 35 s (keyin keshdan), savol ~45 ms (eng ko'pi 75 ms); xotira — model
   yuklangan jarayonga ~+450 MB (shundan tokenizer ~280 MB); serverda bo'sh xotira ~7.9 GB.
7. **Bot sinovi:** `manage.py support_smoke` — 3 ta asosiy savol (AI'siz, hech narsa yuborilmaydi): «lokatsiya uzoq
   deyapti» → geolokatsiya standarti, «aktiv vizit bor» → «User already has an active visit», «Assalomu alaykum» →
   javob yo'q. Biri o'tmasa — buyruq xato bilan tugaydi (chiqish kodi 1). Kengaytirilgan: `--standards 15` — eng ko'p
   ishlatiladigan 15 standart × 5 ta haqiqiy agent iborasi (Claude standartga qo'shgan savollar, bot o'shanda topa
   olmagan matnlar) AI'siz topiladimi; topilmaganlari ro'yxat bilan.

## Qat'iy qoidalar

- Tizim ishlab turibdi — **to'xtalish bo'lmasin**, xodimlar ma'lumoti o'zgarmasin.
- Migratsiyalar faqat **qo'shuvchi** (ustun/jadval qo'shish); server bazasi qayta yaratilmaydi, ma'lumot o'chirilmaydi.
- Har ma'lumot o'zgarishi va deploydan oldin zaxira.
- Kalitlar va parollar faqat env/shifrlangan holda; loglarga va fayllarga yozilmaydi.
- Shu serverdagi **bio-lab.uz** (portlar 3000, 8010) ga tegilmaydi.
- Shaxsiy ma'lumot tashqi xizmatlarga yuborilmaydi; Telegram'ga faqat bot yozadi.
- **Har o'zgarishda shu qo'llanma ham yangilanadi** (tegishli bob + O'zgarishlar tarixi).

## Kod tuzilishi (asosiy)

| Joy | Nima |
|---|---|
| `backend/support/` | Support bot: `engine.py` (javob tanlash), `runner.py` (Telegram oqimi), `tasks.py` (vazifa qarori), `resolution.py` (hal bo'ldimi), `ocr.py`, `vision.py` |
| `backend/prbc/` | PRBC: `client.py` (API), `tasks.py` (vazifa yaratish, kuzatish), `control.py` (SLA, holat sinxroni, ijrochi tanlash), `outlets.py` (mijoz holati), `people.py` (1C xodimlari), `management/commands/prbc_worker.py` |
| `backend/inventory/` | Inventarizatsiya: `views.py`, `io.py` (Excel), `acks.py` (tasdiqnoma), `catalog_extra.py` |
| `backend/zona/` | Platforma: modellar, qidiruv, AI, `docs.py` (qo'llanma API) |
| `frontend/src/components/` | `support/`, `views/prbc*.tsx`, `inventory/`, `docs/` |
| `frontend/src/lib/nav.ts` | Chap menyu |
