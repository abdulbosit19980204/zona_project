# QR Drive — mikroservis

Xodim Telegram botga fayl yuboradi → fayl tanlangan saqlash joyiga (Synology, lokal disk, ...) xodim papkasiga tushadi →
ommaviy havola yaratiladi → havola **QR kod** bilan qaytariladi. Admin hammasini Masʼuliyat platformasi panelidagi
**«QR Drive»** menyusidan boshqaradi. Boshqa botlar va tizimlar xuddi shu funksiyani **REST API** yoki **Python SDK / aiogram plagini** orqali ishlatadi.

## Arxitektura

```
              ┌──────────── nginx (80/443) ─────────────┐
              │  /            → Next.js panel (:3000)    │
              │  /api/ /ws/   → Zona backend (:8000)     │
              │  /qrdrive/    → QR Drive API (:8100)     │
              └──────────────────────────────────────────┘
Zona backend (Django)      QR Drive API (FastAPI)   QR Drive worker      QR Drive bot (aiogram)
   o'z bazasi                 └──────── o'z bazasi: /var/lib/zona/qrdrive/qrdrive.sqlite3 ────────┘
```

Har bir jarayon — alohida systemd servis. **Bittasi to'xtasa, qolganlari ishlayveradi** (sinab ko'rilgan):

| To'xtagan servis | Natija |
|---|---|
| Zona backend | QR Drive paneli, bot, API, ommaviy havolalar ishlaydi. Token QR Drive'da mahalliy tekshiriladi (SSO, tarmoqsiz). |
| QR Drive API | Zona to'liq ishlaydi; QR Drive sahifalarida «servis vaqtincha ishlamayapti» paneli. Bot fayl qabul qiladi, worker navbatni davom ettiradi. |
| Worker | Bot fayllarni qabul qilib navbatga qo'yadi; worker qaytgach hammasi ishlanadi. «Tizim holati» va bosh sahifada ogohlantirish. |
| Bot | Panel, API, worker ishlaydi. |

## Tuzilma

```
services/qrdrive/
  legacy/                 eski kadrlar-bot (o'zgarishsiz nusxa)
  qrdrive/core/           config, crypto (Fernet + argon2), security (SSO), logging (JSON + maskalash), errors (oddiy tildagi xatolar)
  qrdrive/db/             modellar, SQLite WAL, yengil migratsiya
  qrdrive/storage/        provayder interfeysi: Synology (DSM + Drive papka ID), Google Drive, S3, WebDAV/Nextcloud, lokal disk
  qrdrive/services/       pipeline, qr, accounts, files, telegram, audit, system
  qrdrive/api/admin/      panel endpointlari (rollar: superadmin / admin / kuzatuvchi)
  qrdrive/api/v1.py       tashqi API (API kalit, scope, idempotency, rate limit, IP cheklov)
  qrdrive/worker/         navbat, retry, webhook, bildirishnoma, saqlash joyi tekshiruvi, savat, zaxira
  qrdrive/bot/            Telegram bot
  sdk/python/             qrdrive-sdk (klient + aiogram plagini)
  tests/                  pytest (56 ta)
```

## Saqlash joylari

| Turi | Ulanish | Ommaviy havola |
|---|---|---|
| **Synology NAS / Drive** (standart) | DSM manzili + login/parol; Synology Drive papka havolasi (`#file_id=...`) — asosiy papka avtomatik aniqlanadi | Synology'ning o'z havolasi (muddat, parol) |
| Google Drive | Service Account JSON + Shared Drive **yoki** «Google bilan ulash» (OAuth) | «anyone with link: reader» |
| S3 (AWS, MinIO, Wasabi, B2, R2) | endpoint, region, bucket, kalitlar | presigned URL (≤ 7 kun), aks holda tizim havolasi |
| WebDAV / Nextcloud | WebDAV manzili + ilova paroli | Nextcloud OCS havolasi |
| Lokal disk / SMB | serverdagi papka | tizim havolasi |

To'liq qo'llanma, diagnostika va barcha xato kodlari: **[docs/saqlash-joylari.md](docs/saqlash-joylari.md)**.

**Standart:** bo'sh bazada **StarGroup NAS** (`https://file.stargroup.uz`, Synology Drive papkasi
`#file_id=984701843502314054`) avtomatik yaratiladi va asosiy qilinadi. Admin faqat login/parolni kiritadi
(Sozlash ustasi → 3-qadam yoki «Saqlash joylari» → «Login va parolni kiritish»).

## Lokal ishga tushirish

Eng oson: loyiha papkasida `start-all.cmd` (yoki `./start-all.sh`) — hamma servis birdan, nazorat sahifasi
http://127.0.0.1:8900 ([services/control](../control/README.md)). Alohida-alohida:

```bash
cd services/qrdrive
python -m venv .venv && .venv/Scripts/pip install -e ".[test]"     # Linux: .venv/bin/pip
.venv/Scripts/python -m qrdrive.main          # API  → http://127.0.0.1:8100/qrdrive/api/docs
.venv/Scripts/python -m qrdrive.worker.main   # worker (alohida terminalda)
.venv/Scripts/python -m qrdrive.bot.main      # bot (token panelda kiritilgach ulanadi)
.venv/Scripts/python -m pytest                # testlar
```

Frontend (`npm run dev`) `/qrdrive/...` so'rovlarini `QRDRIVE_URL` (standart `http://127.0.0.1:8100`) ga yo'naltiradi.
Lokal rejimda Zona va QR Drive bir xil standart kalit bilan ishlaydi; ishlab chiqarishda `ZONA_JWT_SECRET` = `QRDRIVE_SSO_SECRET`.

Birinchi marta: panel → **QR Drive → Sozlash ustasi** (bot tokeni → saqlash joyi → xodimlar → sinov QR).

## Sozlamalar — panelda

Hamma sozlama panelda (bazada, maxfiylari shifrlangan): bot tokeni va lokal Bot API, saqlash joylari va ularning
login/parollari, sayt manzili (ommaviy havolalar uchun), limitlar, papka/fayl shablonlari, havola muddati/paroli,
QR dizayni (logo, rang, matn, jonli ko'rinish), bot matnlari (uz/ru), bildirishnomalar, vaqt zonasi, saqlash muddatlari.
Eski bot `.env` fayli ham panelda import qilinadi (Tizim holati → «Eski bot sozlamalarini import qilish»).

Serverdagi `/etc/zona/qrdrive.env` da faqat **ishga tushirish** parametrlari qoladi — ular bazadan oldin kerak yoki
xavfsizlik sababli bazada saqlanmasligi kerak: `QRDRIVE_MASTER_KEY` (bazani shifrlash kaliti — uni bazaning o'zida
saqlab bo'lmaydi), `QRDRIVE_SSO_SECRET`, `QRDRIVE_DATA_DIR`, port. Ular «Tizim holati» sahifasida faqat ko'rish uchun ko'rsatiladi.
Maxfiylar shifrlangan; API javobi, jurnal va loglarda ochiq ko'rinmaydi.

Eski bot `.env` fayli: `QRDRIVE_LEGACY_ENV=/yo'l/.env` — birinchi ishga tushishda token, Synology ulanishi, ruxsat berilgan ID'lar import qilinadi.

## Tashqi API (v1)

Swagger: `/qrdrive/api/docs`, ReDoc: `/qrdrive/api/redoc`. Kalit: panel → **API va integratsiyalar**.

| Endpoint | Scope | Nima |
|---|---|---|
| `POST /qrdrive/api/v1/files` | files:write | fayl yoki `source_url` → havola + QR (`?async=true` → 202 + webhook) |
| `GET /qrdrive/api/v1/files/{id}`, `GET /files` | files:read | holat, ro'yxat |
| `GET /files/{id}/qr.png`, `qr.pdf` | files:read | QR rasm / chop etish uchun PDF |
| `POST/DELETE /files/{id}/link` | files:write | havolani yangilash / bekor qilish |
| `POST /qrdrive/api/v1/qr` | qr:generate | istalgan havoladan QR |
| `GET /qrdrive/api/v1/employees` | employees:read | xodimlar |
| `GET /qrdrive/api/v1/health` | — | holat |

Webhook: `file.completed`, `file.failed`, `link.revoked`; imzo `X-QRDrive-Signature: sha256=HMAC(body, secret)`; 4 marta qayta urinish.
SDK va aiogram plagini: [sdk/python/README.md](sdk/python/README.md).

## Qarorlar

1. **Alohida servis, Zona ichida emas.** QR Drive o'z jarayonlari va bazasi bilan ishlaydi; Zona bilan faqat JWT kaliti umumiy (tokenni QR Drive tarmoqsiz tekshiradi). Panel — Zona'ning Next.js ilovasidagi «QR Drive» menyusi (alohida React/Vite panel o'rniga): bitta kirish, bitta interfeys.
2. **SQLite (WAL) + bazadagi navbat, Redis'siz** (foydalanuvchi tanlovi). Worker navbatni bazadan oladi (`locked_until` bilan band qiladi), sozlamalar har jarayonda 3 soniyalik kesh bilan o'qiladi — o'zgarish qayta ishga tushirishsiz kuchga kiradi. Bot tokeni o'zgarsa, bot 5 soniyada yangi token bilan qayta ulanadi.
3. **Docker o'rniga systemd** — Zona deploy uslubiga mos (Ubuntu + nginx). Lokal Telegram Bot API server ixtiyoriy: o'rnatilsa, panelda manzili kiritiladi (20 MB dan katta fayllar uchun kerak).
4. **Rollar Zona'dan:** Zona *admin* → QR Drive *Superadmin*, *editor* → *Admin*, *viewer* → *Kuzatuvchi*. Parol, 2FA, sessiyalar Zona'da boshqariladi.
5. **Takroriy fayl:** sozlamada «oldingi QR'ni yuborish» (standart) yoki «baribir yuklash». Botda alohida savol berilmaydi.
6. **Media group:** har bir faylga alohida QR.
7. **Vebdan yuklangan fayl** xato bilan tugasa, vaqtinchalik nusxa «Qayta urinish» uchun saqlanadi (2 kundan keyin tozalanadi). Telegram fayllari qayta urinishda Telegram'dan qayta olinadi.
8. **Lokal disk** o'z havolasini bera olmaydi — har doim tizim havolasi (`/qrdrive/s/<token>`, 192 bit) ishlatiladi.
9. **SDK paket nomi `qrdrive_sdk`** (PROMPT'dagi `qrdrive` emas) — servis paketi bilan nomi to'qnashmasligi uchun.
10. **Synology Drive papkasi** brauzer manzilidagi `#file_id=` orqali beriladi: `SYNO.SynologyDrive.Files.get` bilan yo'l aniqlanadi
    (jamoa papkasi `/team-folders/X` → File Station `/X`, My Drive → `/home`). Aniqlab bo'lmasa — «Asosiy papka» qo'lda yoziladi.
11. **Login/parolsiz saqlash joyi** serverga ulanib tekshirilmaydi — «kirish ma'lumotlari kiritilmagan» holatida turadi.
12. **S3 havolasi** — presigned URL (S3 cheklovi 7 kun). Muddatsiz yoki parolli havola kerak bo'lsa avtomatik tizim havolasi.
    Google Drive havolasiga parol qo'yib bo'lmaydi — parol so'ralsa tizim havolasi.
13. **2FA va sessiyalar** — Zona'da (QR Drive alohida login yuritmaydi). **Brauzer e2e testlari** o'rniga API darajasidagi
    oqim testlari va jonli QA (Next.js proksi orqali) ishlatildi.
