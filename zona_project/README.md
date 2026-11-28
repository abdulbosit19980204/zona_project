# Responsibility Intelligence Platform

**Clear Ownership. Better Execution.** — kim nimaga javob beradi.

Oddiy org chart emas: kompaniya → bo'lim → jamoa → xodim → biznes jarayon → vazifa zanjiri. Har bir jarayonda
kim **egasi**, kim **bajaradi**, kim **tasdiqlaydi**, kim **nazorat qiladi**, kim **yordam beradi**, kim **zaxira**.
Rahbar bitta xodimni tanlab, uning barcha vazifalari, vakolatlari, aloqalari va javobgarlik chegaralarini bitta
xaritada ko'radi. Egasiz jarayonlar, mas'ulsiz vazifalar va kesishgan mas'uliyat avtomatik topiladi.

## Arxitektura

```
Brauzer ──► Next.js (3000) ──/api/*──► Django + DRF (8000) ──► SQLite
   │                                        ▲
   └──────── WebSocket /ws/events/ ─────────┘  (Channels/Daphne: jonli yangilanish)
```

| Qism | Texnologiyalar |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript · Tailwind CSS 4, shadcn/ui, Lucide, Framer Motion · React Flow (XYFlow), Three.js + React Three Fiber · Zustand, TanStack Query, Axios · React Hook Form + Zod, Recharts, date-fns, Sonner, next-intl |
| Backend | Django, Django REST Framework, SimpleJWT (access 30 daq / refresh 14 kun, rotatsiya), Channels + Daphne (WebSocket), SQLite |
| AI | Claude (rasmiy SDK), Gemini, Grok, OpenAI, DeepSeek, Mistral, Groq, OpenRouter, Azure, Ollama, istalgan OpenAI-mos API |

## Loyiha tuzilmasi

```
zona_project/
├─ pyproject.toml          backend pip paketi (stargroup-zona)
├─ requirements.txt        pip install -r requirements.txt
│
├─ backend/                Django — API, WebSocket, ma'lumotlar bazasi
│  ├─ manage.py
│  ├─ config/              settings.py, urls.py, asgi.py (HTTP + WebSocket)
│  └─ zona/                asosiy ilova (boshqa Django loyihaga ham ulanadi)
│     ├─ models.py          Bo'lim, Jamoa, Xodim, Jarayon, Rol, Vazifa, Vakolat, Taklif, AI...
│     ├─ views*.py          API: tuzilma, kirish (JWT), tasdiqlashlar, admin, AI
│     ├─ realtime.py        WebSocket iste'molchisi va xabar tarqatish
│     ├─ search/            ko'p tilli qidiruv (lotin/kirill/rus, imlo xatolari, sinonimlar)
│     ├─ ai/                AI provayderlar va so'rovlar
│     └─ tests.py
│
└─ frontend/               Next.js ilova
   ├─ src/app/             sahifalar (har bir menyu bandi — alohida papka)
   ├─ src/components/
   │  ├─ layout/           chap menyu, yuqori panel, Ctrl+K buyruqlar oynasi
   │  ├─ views/            sahifa tarkibi (overview, organization-map, employee-360, ...)
   │  ├─ graph/            React Flow tugunlari va chiziqlari
   │  ├─ three/            3D mas'uliyat xaritasi (React Three Fiber)
   │  ├─ panels/ forms/ settings/ charts/ common/
   │  └─ ui/               shadcn/ui komponentlari
   ├─ src/lib/             API mijozi (axios + JWT yangilash), tiplar, hisoblash modeli
   ├─ src/hooks/           TanStack Query hooklari, WebSocket
   ├─ src/stores/          Zustand: sessiya va interfeys sozlamalari
   └─ src/i18n/messages/   uz.json · ru.json · en.json
```

## Ishga tushirish (ishlab chiqish)

**1. Backend** (Python 3.10+):

```bash
python -m venv .venv
.venv\Scripts\activate                  # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cd backend
python manage.py migrate
python manage.py zona_seed              # namuna ma'lumot (ixtiyoriy)
python manage.py createsuperuser        # birinchi administrator
python manage.py runserver              # http://127.0.0.1:8000  (Daphne: HTTP + WebSocket)
```

**2. Frontend** (Node.js 20+), alohida terminalda:

```bash
cd frontend
npm install
copy .env.example .env.local            # ixtiyoriy; standart sozlamalar ishlaydi
npm run dev                             # http://localhost:3000
```

Brauzerda `http://localhost:3000` ni oching va administrator bilan kiring.

## Sahifalar

| Bo'lim | Sahifa | Nima ko'rinadi |
|---|---|---|
| Asosiy | Umumiy ko'rinish | KPI, tashkiliy salomatlik (qamrov %), bo'lim va rol taqsimoti, e'tibor talab qiladiganlar, so'nggi faoliyat |
| | Tashkiliy xarita | React Flow: kompaniya → bo'lim → jamoa → xodim → jarayon. Qidiruv, rol filtri, faqat muammolar, o'ng panel |
| | Mas'uliyat xaritasi 3D | Three.js: bo'limlar halqasi, xodimlar va jarayonlar fazoda; tanlanganda bog'lanishlar yorishadi |
| | Bo'limlar · Xodimlar | Tuzilma, jamoalar, rollar soni; xodimni bosing → **Xodim 360°** |
| | Savol kimga? | Istalgan tilda erkin matn → kim javob beradi (qidiruv + AI) |
| Boshqaruv | Mas'uliyatlar | Jadval (ommaviy o'tkazish) yoki doska (sudrab o'tkazish) |
| | Biznes jarayonlar · Matritsa | Egasi, ijrochilar, nazorat, zaxira; jarayon × xodim rollar jadvali |
| | Tasdiqlashlar | Kuzatuvchi taklif beradi → muharrir/admin tasdiqlaydi |
| Tahlil | Tahlil · Yuklama · Bo'shliqlar · Hisobotlar | Rollar qamrovi, ortiqcha yuklama, egasiz/nazoratsiz/zaxirasiz jarayonlar, Excel, AI audit |
| Tizim | Tarix · Sozlamalar | O'zgarishlar jurnali (jonli); profil, foydalanuvchilar, AI, qidiruv lug'ati |

Yuqori panel: bo'lim doirasi, yo'l ko'rsatkichi, global qidiruv (`Ctrl K`), bildirishnomalar, kun/tun rejimi,
til (o'zbek / rus / ingliz), profil menyusi. Rollar rang bilan emas, **chiziq uslubi** bilan farqlanadi.

## Huquqlar

| Rol | Nima qila oladi |
|---|---|
| Administrator | hammasi + foydalanuvchilar, AI sozlamalari (Django superuser ham administrator) |
| Muharrir | tuzilma, vazifa, rol, vakolatni tahrirlash; takliflarni tasdiqlash; qidiruv lug'ati |
| Kuzatuvchi | ko'rish, qidirish, "Savol kimga?", o'zgarish taklif qilish |

## AI ni ulash

1. Administrator bo'lib kiring → **Sozlamalar → AI → Provayder qo'shish**. Turini tanlang va API kalitni kiriting
   (kalit serverda shifrlangan holda saqlanadi, brauzerga qaytarilmaydi).
2. **Sinash** — kalitni tekshiradi va modellar ro'yxatini yuklaydi.
3. **Vazifalar uchun modellar**: *Savolni yo'naltirish*, *Xodim tahlili*, *Tuzilma auditi* — har biriga provayder,
   model, fikrlash darajasi va zaxira model tanlang.
4. Sarf jadvalida har bir model bo'yicha so'rovlar va tokenlar ko'rinadi.

AI yoqilmagan bo'lsa ham "Savol kimga?" mahalliy ko'p tilli qidiruv bilan ishlaydi.

## QR Drive (ikkinchi loyiha — mikroservis)

Panelning chap menyusida ikki loyiha: **Masʼuliyat platformasi** va **QR Drive** (har biri ichki menyular bilan).
QR Drive — alohida servis (FastAPI + o'z bazasi + worker + Telegram bot): xodim botga fayl yuboradi → saqlash joyiga
tushadi → havola QR kod bilan qaytadi. Boshqa loyihalar uchun REST API, webhook, Python SDK va aiogram plagini bor.
Batafsil: **[services/qrdrive/README.md](services/qrdrive/README.md)**.

## IT inventarizatsiya (filiallar)

Mustaqil, mobilga moslangan sahifa: **`/inventory`** (platforma menyusisiz). Backend — `backend/inventory/`
(alohida `inventory_*` jadvallari), API — `/api/inventory/`. Katalog (30 qurilma turi va brendlari, 12 filial,
tashkilotlar, joylar) `StarGroup_IT_inventarizatsiya_shablon.xlsx` dan olingan va migratsiya bilan avtomatik to'ladi.

| Daraja | Kim | Nima qila oladi |
|---|---|---|
| Boshqaruvchi (IT) | platforma administratorlari avtomatik + tayinlanganlar | hammasi: loginlar, filiallar, katalog, import/eksport |
| Rahbar | direktorlar | barcha filiallar natijasi, analitika, eksport — o'zgartira olmaydi |
| Filial xodimi | `inv.sam`, `inv.and`... | faqat o'z filiali: qurilma (rasm bilan) va xodim qo'shadi |

Filial loginlari Zona'da `inventory` rolida bo'ladi: platformaning boshqa sahifalari, API'lari, WebSocket va QR Drive
ularga yopiq. Eksport: CSV, Excel va **asl shablon formatida** (formulalar, Xulosa, ochiluvchi ro'yxatlar bilan);
import — to'ldirilgan shablon yoki eksport qilingan jadval (avval tekshiruv, keyin tasdiq). Rasmlar baza yonidagi
`inventory-media/` da (`ZONA_INVENTORY_MEDIA`), siqilgan holda; havolalari imzolangan.

**Tillar:** o'zbek va rus (sarlavhadagi UZ/RU tugmasi; katalog ham ikki tilda). Tarjimalar —
`frontend/src/components/inventory/i18n-ru.ts`, to'liqligini tekshirish: `node frontend/scripts/inv-i18n-check.mjs`.

**Xodim tasdig'i (imzo):** qurilma kiritilganda xodimning telefoni va Telegrami yoziladi. «Tasdiqlash» bo'limida
xodimga shaxsiy havola (`/ack/<token>`, loginsiz) yaratiladi va Telegram/SMS orqali yuboriladi. Xodim o'zidagi
qurilmalarni rasmlari bilan ko'radi, har birini «menda bor / yo'q» deb belgilaydi, barmog'i bilan imzo chizadi.
Natija — imzolangan dalolatnoma (chop etish / PDF), e'tirozlar ro'yxati va analitikadagi «imzolagan xodimlar» ko'rsatkichi.
Qurilmalar keyin o'zgarsa, tasdiqnoma «eskirgan» deb belgilanadi va yangi havola yuboriladi.

```bash
python backend/manage.py inv_setup --logins --out /root/inventarizatsiya_loginlar.xlsx   # filial loginlari + fayl
```

## Hammasini bitta buyruq bilan ishga tushirish

```bash
start-all.cmd      # Windows        |   ./start-all.sh   # Linux/macOS
```

Barcha servislar (Zona backend, QR Drive API/worker/bot, panel) ishga tushadi; nazorat sahifasi http://127.0.0.1:8900 —
holat, start/stop/restart, loglar, yiqilganda avtomatik qayta ishga tushirish. Batafsil: [services/control/README.md](services/control/README.md).

## Ishlab chiqarish

Ubuntu server (gunicorn + nginx + systemd) uchun tayyor skriptlar va to'liq qo'llanma: **[deploy/README.md](deploy/README.md)**.

```bash
python backend/manage.py zona_snapshot                                 # joriy bazani deploy/data/ ga (repo private bo'lsin!)
sudo bash /opt/zona-src/zona_project/deploy/install.sh <domen>         # serverda birinchi marta
sudo bash /opt/zona/deploy/update.sh                                   # keyingi yangilashlar
```

Backend standart holatda bitta jarayonda ishlaydi (xotiradagi channel layer). Bir nechta worker uchun `ZONA_REDIS_URL`
(Redis) va `ZONA_WEB_WORKERS` ni bering — `CHANNEL_LAYERS` va kesh Redis'ga o'tadi (`deploy/gunicorn.conf.py`).

## Boshqa Django loyihaga ulash

```bash
pip install "/yo'l/zona_project[ai,server]"
```

```python
# settings.py
INSTALLED_APPS += ["daphne", "rest_framework", "rest_framework_simplejwt.token_blacklist", "channels", "zona"]
ASGI_APPLICATION = "config.asgi.application"   # asgi.py da zona.routing.websocket_urlpatterns ni ulang
ZONA = {"COMPANY_NAME": "StarGroup", "CORS_ORIGINS": ["https://ui.example.com"]}

# urls.py
path("", include("zona.urls")),                # /api/...
```

## Testlar

```bash
cd backend && python manage.py test zona          # backend
cd frontend && npx tsc --noEmit && npm run lint   # frontend
```

## API (qisqacha)

Hammasi `/api/` ostida, `Authorization: Bearer <access>`:
`auth/login|refresh|logout|me|password` · `state/` (butun tuzilma) · `events/` · `departments/ teams/ members/
authorities/ systems/ processes/ roles/ tasks/ edge-cases/ synonyms/` (CRUD) · `tasks/{id}/move/`,
`tasks/bulk-move/` · `approvals/` (+ `approve/ reject/ cancel/`) · `search/?q=` · `ai/route|person|audit/` ·
`admin/users/`, `admin/ai/providers|tasks|usage/` · `export.xlsx`. WebSocket: `/ws/events/?token=<access>`.
