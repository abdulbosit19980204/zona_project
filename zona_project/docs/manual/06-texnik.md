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
