# QR Drive — to'liq loyiha prompti (coding agent uchun)

> Ushbu matnni to'liqligicha coding agent'ga (Claude Code va h.k.) bering. Agent `kadrlar-bot/` papkasida ishlaydi.

---

## 0. Rol va asosiy qoida

Sen tajribali full-stack muhandissan. Vazifang — mavjud `kadrlar-bot` loyihasini to'liq mahsulotga aylantirish:
**Telegram bot + veb admin panel + bir nechta bulutli/NAS saqlash joylari + analitika + jurnal + tashqi API**.

**Muhim:**
- Mavjud fayllarni **O'CHIRMA** (`bot/main.py`, `bot/synology.py`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `README.md`). Ularni `legacy/` papkasiga ko'chir va yangi loyihada ularning mantiqidan (Synology login/upload/share, lokal Bot API, 100 MB limit, QR) qayta foydalan.
- Eski `.env` qiymatlari birinchi ishga tushishda avtomatik ravishda bazadagi sozlamalarga import qilinsin.
- Har bir bosqich oxirida ishlaydigan holat bo'lsin (testlar o'tadi, `docker compose up` ishlaydi).
- Admin — **texnik bo'lmagan oddiy foydalanuvchi**. Hamma narsa sodda, tushunarli, o'zbek tilida (lotin), zamonaviy UI'da bo'lsin. Hech qayerda xom JSON, stack trace yoki texnik xato kodi ko'rsatilmasin — doim "nima bo'ldi" va "nima qilish kerak" degan oddiy matn.

---

## 1. Mahsulot maqsadi

Kadrlar bo'limi xodimlari faylni Telegram botga yuboradi → tizim uni tanlangan saqlash joyiga (Synology, Google Drive, va h.k.) xodim papkasiga saqlaydi → ommaviy havola yaratadi → havolani **QR kod** ko'rinishida qaytaradi.
Admin veb-paneldan hamma narsani boshqaradi: sozlamalar, saqlash joylari, xodimlar, fayllar, xatolar, analitika.
Boshqa botlar va tizimlar bu funksiyani **API** yoki **plugin** orqali ishlatishi mumkin.

---

## 2. Texnologiyalar

| Qism | Texnologiya |
|---|---|
| Backend API | Python 3.12, **FastAPI**, Pydantic v2, SQLAlchemy 2 (async), Alembic |
| Baza | **PostgreSQL 16** |
| Navbat / kesh / pub-sub | **Redis 7** + **arq** (fon vazifalar, retry) |
| Telegram bot | **aiogram 3** + lokal `telegram-bot-api` server (2 GB gacha; limit sozlamadan, default 100 MB) |
| Frontend | **React 18 + TypeScript + Vite**, **Tailwind CSS**, **shadcn/ui**, TanStack Query, TanStack Table, React Router, **Recharts**, react-hook-form + zod, i18next (uz default, ru) |
| QR | `qrcode` + Pillow (logo, rang, matn qo'shish imkoni bilan) |
| Shifrlash | `cryptography.Fernet` (MASTER_KEY bilan), parollar — `argon2` |
| Deploy | Docker Compose (Synology Container Manager'da ishlashi shart) |
| Testlar | pytest, pytest-asyncio, respx, testcontainers (Postgres, MinIO), Playwright (e2e) |

Struktura (monorepo):
```
kadrlar-bot/
  legacy/            # eski kod, o'zgarishsiz
  backend/app/
    core/            # config, security, crypto, logging
    db/              # models, migrations
    storage/         # provider interfeysi + implementatsiyalar
    services/        # pipeline, qr, analytics, notifications
    api/admin/       # admin panel endpointlari
    api/v1/          # tashqi (public) API
    bot/             # aiogram bot
    worker/          # arq vazifalar
  frontend/
  sdk/python/qrdrive/        # Python SDK + aiogram plugin
  docker-compose.yml
  .env.example
  README.md
```

---

## 3. Bootstrap (.env) va sozlamalar

`.env` faqat ishga tushirish uchun minimal:
```
DATABASE_URL, REDIS_URL, MASTER_KEY, PUBLIC_BASE_URL,
INITIAL_ADMIN_LOGIN, INITIAL_ADMIN_PASSWORD, TZ=Asia/Tashkent,
TELEGRAM_API_ID, TELEGRAM_API_HASH   # lokal Bot API server uchun
```
**Qolgan barcha sozlamalar admin paneldan** boshqariladi va bazada saqlanadi. Maxfiy qiymatlar (token, parol, kalitlar) bazada **Fernet bilan shifrlangan** holda saqlanadi, UI'da `••••••` ko'rinishida, faqat "O'zgartirish" tugmasi bilan almashtiriladi, hech qachon API javobida yoki logda ochiq qaytmaydi.
Sozlama o'zgarsa — bot va worker **qayta ishga tushirmasdan** yangilanadi (Redis pub/sub orqali kesh invalidatsiyasi).

### Birinchi ishga tushirish ustasi (Setup Wizard)
1. Admin akkaunt yaratish (yoki INITIAL_ADMIN bilan kirish va parolni almashtirish).
2. Telegram bot tokenini kiritish → "Tekshirish" (getMe) → bot nomi va rasmi ko'rsatiladi. Kerak bo'lsa `logOut` ni avtomatik bajarish.
3. Birinchi saqlash joyini qo'shish → "Ulanishni tekshirish".
4. Birinchi xodimlarni qo'shish yoki taklif havolasini yaratish.
5. Test: "Menga sinov fayli yubor" → admin o'z Telegramida QR oladi.

---

## 4. Saqlash joylari (Storage providers)

Umumiy interfeys (`storage/base.py`):
```python
class StorageProvider(Protocol):
    async def test_connection(self) -> HealthResult          # ok, latency, xato matni
    async def get_quota(self) -> Quota | None               # used/total
    async def ensure_folder(self, path: str) -> None
    async def upload(self, stream, size, dest_path, filename) -> RemoteFile
    async def create_public_link(self, remote: RemoteFile, expire_at=None, password=None) -> PublicLink
    async def revoke_public_link(self, link_id: str) -> None
    async def list(self, path: str) -> list[RemoteEntry]
    async def open_stream(self, remote_id_or_path) -> AsyncIterator[bytes]   # web preview/yuklab olish
    async def thumbnail(self, remote) -> bytes | None
    async def move(self, src, dst) -> None
    async def rename(self, remote, new_name) -> None
    async def delete(self, remote) -> None
```
Implementatsiyalar (bosqichma-bosqich):
1. **Synology DSM** (File Station API: `SYNO.API.Auth`, `SYNO.FileStation.Upload/CreateFolder/List/Sharing/Download/Thumb/Delete/Rename/CopyMove`). Synology Drive team folder'larini ham qo'llab-quvvatlasin. Self-signed SSL uchun "SSL tekshirmaslik" katagi. QuickConnect emas, to'g'ridan-to'g'ri URL. `legacy/bot/synology.py` dagi mantiqni shu yerga ko'chir.
2. **Google Drive** — ikki usul: (a) Service Account JSON (ogohlantirish: service account'ning o'z kvotasi yo'q, **Shared Drive** tanlash majburiy), (b) OAuth "Google bilan ulash" tugmasi (refresh token shifrlangan saqlanadi). Ommaviy havola = `anyone with link: reader` ruxsati.
3. **S3-mos** (AWS S3, MinIO, Wasabi, Backblaze B2, Cloudflare R2): endpoint, region, bucket, key. Havola: presigned URL (maks 7 kun — UI'da ogohlantirish) yoki tizimning o'z qisqa havolasi orqali proksi (pastga qarang).
4. **WebDAV / Nextcloud** (Nextcloud OCS Share API bilan ommaviy havola).
5. **Lokal disk / tarmoq papkasi** (SMB mount) — havola tizimning o'zi orqali.
6. Keyinroq: **Yandex Disk**, **OneDrive/SharePoint** (MS Graph), **Dropbox**.

**Tizim ichidagi qisqa havola (fallback):** agar provayder ommaviy havola bera olmasa yoki admin xohlasa, `PUBLIC_BASE_URL/s/<token>` ko'rinishida tizimning o'z havolasi yaratilsin (muddat, parol, yuklab olishlar soni hisoblanadi, istalgan vaqtda bekor qilinadi). Admin har bir saqlash joyi uchun "Provayder havolasi" yoki "Tizim havolasi" ni tanlaydi.

Admin panelda saqlash joylari:
- Bir nechta saqlash joyi qo'shish, biri — **asosiy**. Bo'lim yoki xodim bo'yicha boshqa saqlash joyini biriktirish mumkin.
- Har biri uchun: nomi, turi (ikonka bilan), ulanish ma'lumotlari, asosiy papka, holat (🟢/🔴), oxirgi tekshiruv vaqti, kvota (progress bar), "Tekshirish" tugmasi.
- Har bir maydon yonida "Bu nima?" tooltip va qo'llanma havolasi (masalan "Google Service Account qanday olinadi" — qadamma-qadam rasmli yo'riqnoma modal oynada).
- Asosiy saqlash joyi ishlamay qolsa: zaxira saqlash joyiga avtomatik yuklash (ixtiyoriy sozlama).

---

## 5. Xodimlar va Telegram akkauntlar

**Asosiy tamoyil:** papka Telegram username'ga emas, **Xodim** (Employee) yozuviga bog'lanadi. Telegram akkaunt — xodimga biriktirilgan "kirish kaliti".

Modellar:
- `Employee`: id, F.I.Sh., bo'lim, lavozim, telefon, papka nomi (slug, admin o'zgartira oladi), saqlash joyi (ixtiyoriy override), holat (faol/bloklangan/arxiv), izoh.
- `TelegramAccount`: telegram_id (asosiy kalit — o'zgarmaydi), username, ism, til, employee_id, holat, birinchi/oxirgi faollik.
- `TelegramAccountHistory`: username/ism o'zgarishlari tarixi.

Holatlar:
- **Username o'zgardi** → bot avtomatik aniqlaydi, yozuvni yangilaydi, tarixga yozadi, papka **o'zgarmaydi**.
- **Xodim Telegram akkauntini almashtirdi** (yangi raqam/akkaunt) → admin xodim sahifasida "Yangi akkaunt biriktirish" bosadi → bir martalik taklif havolasi `t.me/<bot>?start=<kod>` (muddati 24 soat) yaratiladi (QR bilan) → xodim bossa, yangi akkaunt biriktiriladi, eskisi o'chiriladi, hamma fayllar va papka saqlanib qoladi.
- **Noma'lum odam yozdi** → "Kirish so'rovlari" bo'limida paydo bo'ladi (ism, username, ID, vaqt). Admin: "Yangi xodim sifatida tasdiqlash", "Mavjud xodimga biriktirish" yoki "Rad etish/bloklash".
- **Xodim ishdan ketdi** → "Arxivlash": kirish yopiladi, fayllar qoladi.
- Bir xodimga bir nechta Telegram akkaunt biriktirish mumkin (ixtiyoriy).
- Ommaviy import: Excel/CSV orqali xodimlar ro'yxati + har biriga taklif havolalari ro'yxatini chop etish.

---

## 6. Fayl jarayoni (pipeline)

Har bir fayl — `FileRecord` yozuvi va bosqichlar zanjiri. Har bir bosqich `FileEvent` sifatida vaqt va davomiylik bilan yoziladi:
```
received → downloading → uploading → sharing → qr_generated → delivered
                                ↘ failed (sabab, bosqich, urinishlar soni)
```
`FileRecord` maydonlari: id, employee_id, telegram_account_id, manba (telegram/web/api), api_key_id, saqlash joyi, masofaviy yo'l va id, asl nom, saqlangan nom, hajm, MIME, sha256, izoh (caption), havola, havola muddati, parol bormi, yuklab olishlar soni (tizim havolasi bo'lsa), holat, xato matni, har bosqich davomiyligi, yaratilgan vaqt, o'chirilgan (soft delete).

Qoidalar:
- Og'ir ishlar (yuklash, havola) **arq worker**da bajariladi; bot darhol "⏳ qabul qilindi" deb javob beradi va jarayon davomida xabarni yangilab boradi.
- Xatoda avtomatik qayta urinish: 3 marta, eksponensial kutish (10s, 60s, 5min). Hammasi muvaffaqiyatsiz bo'lsa — xodimga tushunarli xabar + adminga bildirishnoma.
- Papka shabloni sozlanadi: masalan `{bo'lim}/{xodim}/{yyyy}/{mm}`. Fayl nomi shabloni: `{sana}_{vaqt}_{asl_nom}`. Nomlar xavfsizlantiriladi (taqiqlangan belgilar, uzunlik), kirill va o'zbek harflari buzilmasligi shart.
- Ruxsat etilgan fayl turlari va maksimal hajm (default **100 MB**) sozlamadan.
- Bir xil sha256 bilan qayta yuborilsa — "Bu fayl allaqachon yuklangan, oldingi QR'ni yuboraymi?" (sozlanadi).
- Media group (bir nechta fayl birga) — har biriga alohida QR yoki bitta umumiy papka havolasi (sozlama).
- Vaqtinchalik fayllar har doim tozalanadi.

---

## 7. Telegram bot

Buyruqlar va funksiyalar:
- `/start` — salom; ro'yxatdan o'tmagan bo'lsa — so'rov yuborish; `start=<kod>` bo'lsa — akkaunt biriktirish.
- Fayl yuborish (hujjat, rasm, video, audio) → jarayon xabari → QR rasm + havola + saqlangan joy + muddat.
- `/myfiles` — oxirgi 10 ta fayl, inline tugmalar: "QR'ni qayta yuborish", "Havolani yangilash".
- `/id`, `/help`, `/lang` (uz/ru).
- Bot xabarlarining matnlari admin paneldan tahrirlanadi (uz/ru).
- QR dizayni sozlanadi: o'lcham, rang, markazda logo, pastida matn (masalan, fayl nomi yoki kompaniya nomi), PNG yoki PDF (chop etish uchun).

---

## 8. Veb admin panel (UI/UX)

Umumiy talablar: zamonaviy, toza dizayn (shadcn/ui), yorug'/qorong'i rejim, mobil qurilmada to'liq ishlaydi, o'zbek (lotin) default + rus tili, har bir bo'sh sahifada tushuntirish va "birinchi qadam" tugmasi, har bir xavfli amal tasdiq oynasi bilan, toast xabarlar, skeleton yuklanish holatlari, global qidiruv (Ctrl+K).

Chap menyu:
1. **Bosh sahifa (Dashboard)** — KPI kartochkalar: bugun/hafta/oy fayllar, umumiy hajm, faol xodimlar, muvaffaqiyat foizi, o'rtacha ishlov vaqti, **tejalgan vaqt** (fayl boshiga N daqiqa — sozlanadi). Grafiklar: kunlik yuklashlar, xatolar trendi, saqlash joylari bandligi. "Diqqat talab qiladi" bloki: kutilayotgan so'rovlar, xatolar, ishlamayotgan saqlash joyi, kvota > 90%, muddati tugayotgan havolalar.
2. **Fayllar** — ikki ko'rinish: (a) jadval (filtr: xodim, bo'lim, sana, tur, holat, saqlash joyi; qidiruv; ommaviy amallar), (b) **papka brauzeri** — xodim papkalari bo'yicha, xuddi Explorer kabi. Fayl ustida: oldindan ko'rish (rasm, PDF, video, audio — brauzer ichida), yuklab olish, QR ko'rsatish/chop etish/yuklab olish, havolani nusxalash, havolani yangilash/bekor qilish, muddat/parolni o'zgartirish, nomini o'zgartirish, boshqa papkaga ko'chirish, o'chirish (avval "Savat", 30 kundan keyin butunlay). Fayl tarixi (barcha bosqichlar va hodisalar vaqt chizig'ida). Admin vebdan ham drag-and-drop bilan fayl yuklay oladi — xuddi shu pipeline.
   - Saqlash joyida tizimdan tashqari qo'shilgan fayllarni ham ko'rsatish (provider `list` orqali), "tizimda ro'yxatga olinmagan" belgisi bilan.
3. **Xodimlar** — ro'yxat, kartochka: ma'lumotlar, Telegram akkauntlar va tarixi, fayllari, statistikasi, "Yangi akkaunt biriktirish", "Bloklash", "Arxivlash". Excel import/eksport.
4. **Kirish so'rovlari** — kutilayotganlar soni menyuda badge bilan.
5. **Xatolar markazi** — barcha muvaffaqiyatsiz jarayonlar, oddiy tilda sabab va tavsiya ("Synology paroli noto'g'ri — Saqlash joylari bo'limida yangilang"), "Qayta urinish" tugmasi (bittalab yoki ommaviy), xato turlari bo'yicha guruhlash.
6. **Jurnal (Audit)** — kim, qachon, nima qildi: admin amallari (sozlama o'zgarishi: eski → yangi qiymat, maxfiylar yashirilgan), bot hodisalari, API chaqiruvlari. Filtr va eksport.
7. **Analitika** — sana oralig'i filtri; grafiklar: kunlar bo'yicha yuklashlar, xodimlar va bo'limlar reytingi, fayl turlari (donut), hajm taqsimoti, faollik soatlari issiqlik xaritasi (hafta kuni × soat), saqlash joylari bo'yicha hajm, xatolar soni va turlari, o'rtacha ishlov vaqti bosqichlar bo'yicha, API kalitlari bo'yicha foydalanish. CSV/Excel eksport.
8. **Saqlash joylari** — 4-bo'limdagidek.
9. **Bot sozlamalari** — token, lokal API server, limitlar, fayl turlari, papka/fayl nomi shablonlari, havola muddati/paroli, QR dizayni (jonli ko'rinish bilan), bot matnlari, til, vaqt zonasi, bildirishnoma chati.
10. **API va integratsiyalar** — API kalitlar, webhooklar, Swagger havolasi, kod misollari (curl, Python, aiogram plugin) nusxalash tugmasi bilan.
11. **Administratorlar** — rollar: **Superadmin** (hammasi), **Admin** (sozlamalardan tashqari hammasi), **Kuzatuvchi** (faqat ko'rish). Parolni tiklash, ixtiyoriy 2FA (TOTP), sessiyalar ro'yxati.
12. **Tizim holati** — bot, lokal Telegram API, worker, navbat uzunligi, baza, Redis, har bir saqlash joyi (ping, kechikish), disk joyi, versiya. Zaxira nusxa (backup) yaratish/yuklab olish.

---

## 9. Bildirishnomalar

Admin(lar)ga Telegram orqali (va panelda qo'ng'iroqcha):
- jarayon 3 urinishdan keyin ham xato bo'ldi;
- saqlash joyi ishlamay qoldi / qayta tiklandi;
- kvota 90% dan oshdi;
- yangi kirish so'rovi;
- havolalar muddati 3 kundan keyin tugaydi (ixtiyoriy);
- kunlik/haftalik qisqa hisobot (ixtiyoriy, vaqti sozlanadi).
Har bir tur alohida yoqiladi/o'chiriladi.

---

## 10. Tashqi API va boshqa botlarga ulanish

### 10.1 REST API `v1`
- Autentifikatsiya: `Authorization: Bearer <api_key>`. Kalitlar admin panelda yaratiladi, **faqat bir marta** ko'rsatiladi, bazada hash holda saqlanadi. Har bir kalitda: nomi, ruxsatlar (scopes: `files:write`, `files:read`, `qr:generate`, `employees:read`), rate limit, ruxsat etilgan IP'lar (ixtiyoriy), standart saqlash joyi, amal qilish muddati, foydalanish statistikasi.
- `Idempotency-Key` header qo'llab-quvvatlansin.
- Endpointlar:
  - `POST /api/v1/files` — multipart fayl **yoki** `source_url` (yuklab olish uchun), parametrlar: `employee_id` | `telegram_id` | `external_user` (ixtiyoriy), `folder` (ixtiyoriy), `expire_days`, `password`, `qr_style`. Javob: `{id, status, url, qr_png_url, qr_base64, remote_path, expires_at}`. Katta fayllar uchun `?async=true` → `202` + keyin webhook.
  - `GET /api/v1/files/{id}`, `GET /api/v1/files?…` (filtrlar bilan)
  - `GET /api/v1/files/{id}/qr.png?size=&logo=` va `qr.pdf`
  - `POST /api/v1/files/{id}/link` (yangilash), `DELETE /api/v1/files/{id}/link` (bekor qilish)
  - `POST /api/v1/qr` — istalgan URL'dan QR (faqat QR xizmati)
  - `GET /api/v1/employees`, `GET /api/v1/health`
- Webhooklar: `file.completed`, `file.failed`, `link.revoked`; HMAC-SHA256 imzo (`X-QRDrive-Signature`), qayta urinish, panelda yetkazish jurnali va "Test yuborish" tugmasi.
- OpenAPI hujjat: `/api/docs` (Swagger) va `/api/redoc`.

### 10.2 Python SDK va aiogram plugin (`sdk/python/qrdrive`)
Boshqa aiogram botga bir necha qatorda ulash:
```python
from qrdrive.aiogram import create_router

dp.include_router(create_router(
    api_url="https://qr.firma.uz",
    api_key="qd_live_...",
    commands=["qr"],          # yoki barcha fayllarga javob berish
    reply_with_qr=True,
))
```
Plugin boshqa botdagi faylni qabul qiladi → `POST /api/v1/files` ga yuboradi → QR'ni o'sha botning foydalanuvchisiga qaytaradi. Shuningdek oddiy klient:
```python
from qrdrive import QRDriveClient
res = await QRDriveClient(url, key).upload("hujjat.pdf", telegram_id=123)
```
Paket `pip install` qilinadigan bo'lsin (pyproject.toml), README'da misollar bilan.

---

## 11. Xavfsizlik

- HTTPS (Synology reverse proxy yoki Caddy orqali, README'da yo'riqnoma).
- Admin sessiyasi: httpOnly + Secure cookie, CSRF himoyasi, login urinishlarini cheklash va vaqtincha bloklash.
- Barcha maxfiy ma'lumotlar shifrlangan; loglarda token/parol/kalit hech qachon chiqmasin (maskalash filtri).
- Fayl preview/yuklab olish faqat avtorizatsiyadan keyin, backend orqali stream qilinadi (saqlash joyi credential'lari brauzerga chiqmaydi).
- Tizim havolalari uchun taxmin qilib bo'lmaydigan token (≥ 128 bit).
- Faqat ruxsat etilgan Telegram akkauntlar fayl yuklay oladi.
- Bazaning kunlik avtomatik zaxira nusxasi (oxirgi 14 kun saqlanadi).

---

## 12. Loglar va kuzatuv

- Strukturaviy JSON loglar (structlog), har bir so'rov/jarayonda `trace_id`.
- Barcha hodisalar bazada ham saqlanadi (`file_events`, `audit_log`, `api_requests`, `bot_updates` — xom update emas, qisqa ma'lumot), saqlash muddati sozlanadi (default 365 kun).
- `/metrics` (Prometheus formatida, ixtiyoriy).

---

## 13. Deploy

`docker-compose.yml` servislari: `postgres`, `redis`, `telegram-bot-api`, `api` (FastAPI + yig'ilgan frontend statik fayllari), `worker`, `bot`. Healthcheck'lar, `restart: unless-stopped`, volume'lar, migratsiyalar avtomatik (`alembic upgrade head` ishga tushishda).
README (o'zbek tilida): Synology Container Manager'da qadamma-qadam o'rnatish (skrinshot o'rinlari bilan), reverse proxy va SSL sozlash, yangilash, zaxiradan tiklash, tez-tez uchraydigan muammolar.

---

## 14. Testlar va qabul mezonlari

Testlar:
- Har bir storage provider uchun unit testlar (HTTP mock — respx), S3 uchun MinIO testcontainer, Synology uchun soxta (fake) server.
- Pipeline: muvaffaqiyat, har bosqichdagi xato, retry, takroriy fayl.
- Telegram: username o'zgarishi, akkaunt almashtirish (taklif kodi), ruxsatsiz foydalanuvchi.
- API: auth, scopes, idempotency, webhook imzosi.
- Playwright e2e: login → setup wizard → saqlash joyi qo'shish → fayl yuklash → QR ko'rish → fayl o'chirish.

Qabul mezonlari (hammasi bajarilishi shart):
1. Xodim 100 MB gacha faylni botga yuborsa, 1 daqiqa ichida QR oladi; fayl xodim papkasida turadi.
2. Admin texnik bilimsiz setup wizard orqali tizimni 10 daqiqada sozlay oladi.
3. Admin paneldan Synology'dan Google Drive'ga asosiy saqlash joyini almashtirsa, keyingi fayllar Drive'ga tushadi, qayta ishga tushirish shart emas.
4. Xodim username'ini o'zgartirsa, papka o'zgarmaydi; yangi akkauntga taklif havolasi orqali o'tsa, barcha fayllari saqlanib qoladi.
5. Saqlash joyi ishlamay qolsa — xodimga tushunarli xabar, adminga bildirishnoma, Xatolar markazida yozuv; tiklangach "Qayta urinish" bilan fayl yuklanadi.
6. Vebda xodim papkasidagi fayllarni ko'rish, ochish, yuklab olish mumkin.
7. Boshqa aiogram bot SDK plugin orqali 5 qator kod bilan QR funksiyasini oladi.
8. Analitika sahifasidagi raqamlar bazadagi ma'lumotga mos keladi.
9. Hech bir maxfiy qiymat log, API javobi yoki UI'da ochiq ko'rinmaydi.

---

## 15. Bosqichlar (ish tartibi)

1. **Asos:** monorepo struktura, legacy'ni ko'chirish, baza modellari, migratsiyalar, auth, sozlamalar (shifrlangan), Synology provider, pipeline + worker, bot (hozirgi funksiya + xodim modeli), docker-compose.
2. **Admin panel asoslari:** setup wizard, dashboard, fayllar (jadval + papka brauzeri + preview), xodimlar, so'rovlar, saqlash joylari, bot sozlamalari.
3. **Ishonchlilik:** xatolar markazi, retry, bildirishnomalar, jurnal, tizim holati, backup.
4. **Qo'shimcha saqlash joylari:** Google Drive, S3, WebDAV/Nextcloud, lokal disk, tizim havolalari.
5. **Analitika** va eksport.
6. **Tashqi API**, webhooklar, Python SDK va aiogram plugin.
7. **Sayqal:** i18n (ru), mobil moslashuv, e2e testlar, README.

Har bosqich oxirida: qisqa hisobot (nima qilindi, qanday tekshirildi, nima qoldi).
Noaniq joy bo'lsa — eng oddiy va xavfsiz variantni tanla, qarorni README'ning "Qarorlar" bo'limiga yoz.
