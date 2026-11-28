# Serverga o'rnatish (Ubuntu + gunicorn + nginx)

Bitta Ubuntu 22.04/24.04 server, har bir servis — alohida systemd jarayon (bittasi to'xtasa, qolganlari ishlayveradi):

| Servis | Manzil | Baza |
|---|---|---|
| `zona-frontend` — Next.js panel | 127.0.0.1:3000 | — |
| `zona-backend` — Django/Channels (gunicorn + uvicorn) | 127.0.0.1:8000 | `/var/lib/zona/db.sqlite3` |
| `qrdrive-api` — QR Drive API (FastAPI) | 127.0.0.1:8100 | `/var/lib/zona/qrdrive/qrdrive.sqlite3` |
| `qrdrive-worker`, `qrdrive-bot` | — | o'sha QR Drive bazasi |

| `zona-control` — servislar boshqaruv markazi | 127.0.0.1:8900 | — |

**nginx** (80/443): `/` → frontend, `/api/` `/ws/` → Zona, `/qrdrive/` → QR Drive, `/control/` → boshqaruv markazi.
Batafsil: [services/qrdrive/README.md](../services/qrdrive/README.md), [services/control/README.md](../services/control/README.md).

**Servislar markazi** (`https://<domen>/control/`): hamma servisni bitta tugma bilan ishga tushirish/to'xtatish,
holati, loglari. Parol: `sudo grep CONTROL_PASSWORD /etc/zona/control.env`.

## 0. Bazani tayyorlash (lokal kompyuterda)

Hozirgi ish bazangiz serverga `deploy/data/zona.sqlite3` snapshot orqali boradi:

```bash
cd zona_project/backend
python manage.py zona_snapshot          # -> deploy/data/zona.sqlite3 (sessiyalar/tokenlar tozalanadi)
git add ../deploy/data/zona.sqlite3
git commit -m "DB snapshot" && git push
```

> **Repo private bo'lishi shart.** Snapshot ichida xodimlar telefonlari va foydalanuvchi parol xeshlari bor.

Snapshot faqat **birinchi o'rnatishda** ko'chiriladi. Keyingi `update.sh` lar serverdagi ishchi bazaga tegmaydi (faqat migratsiyalar) — serverda kiritilgan ma'lumotlar yo'qolmaydi.

## 1. Birinchi o'rnatish

```bash
sudo git clone https://github.com/<user>/zona_project.git /opt/zona-src
sudo bash /opt/zona-src/zona_project/deploy/install.sh zona.example.uz     # domen yoki server IP
```

Skript: paketlar (python3-venv, nginx, Node 22) → `zona` tizim foydalanuvchisi → `/etc/zona/zona.env` (kalitlar avtomatik yaratiladi) → baza → venv + pip → migrate/collectstatic → `npm ci && npm run build` → systemd servislar → nginx.

Kirish: bazadagi mavjud foydalanuvchilar (admin, uzdev) — parollar o'zgarmaydi.

## 2. HTTPS (domen bo'lsa)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d zona.example.uz
sudo sed -i 's/^DJANGO_SECURE_COOKIES=0/DJANGO_SECURE_COOKIES=1/' /etc/zona/zona.env
sudo systemctl restart zona-backend
```

## 3. Yangilash

```bash
sudo bash /opt/zona/deploy/update.sh
```

Avval zaxira → `git pull` → pip → migrate → collectstatic → frontend build → restart.

## Muhim fayllar

| Yo'l | Nima |
|---|---|
| `/etc/zona/zona.env` | Sozlamalar va kalitlar (namuna: `deploy/env.example`) |
| `/etc/zona/qrdrive.env` | QR Drive kalitlari (namuna: `deploy/qrdrive.env.example`) |
| `/var/lib/zona/qrdrive/` | QR Drive bazasi, vaqtinchalik fayllar, logo, o'z zaxiralari |
| `/var/lib/zona/db.sqlite3` | Ishchi baza |
| `/var/lib/zona/backups/` | Kunlik zaxira (02:30, 14 kun saqlanadi) |
| `/opt/zona` | Loyiha papkasiga symlink |

**`ZONA_ENCRYPTION_KEY` va `QRDRIVE_MASTER_KEY` ni alohida saqlab qo'ying.** AI kalitlari, bot tokeni va NAS parollari shular bilan shifrlanadi — yo'qolsa, ularni panelda qaytadan kiritish kerak bo'ladi.
`ZONA_JWT_SECRET` (zona.env) va `QRDRIVE_SSO_SECRET` (qrdrive.env) bir xil bo'lishi shart — `qrdrive-setup.sh` buni o'zi ta'minlaydi.

## Boshqaruv

```bash
systemctl status zona-backend zona-frontend
journalctl -u zona-backend -f            # backend jurnali
journalctl -u zona-frontend -f
journalctl -u qrdrive-api -u qrdrive-worker -u qrdrive-bot -f   # QR Drive (JSON loglar)
sudo -u zona bash /opt/zona/deploy/backup.sh     # qo'lda zaxira
systemctl list-timers zona-backup.timer
```

Zaxiradan tiklash:

```bash
sudo systemctl stop zona-backend
gunzip -c /var/lib/zona/backups/db-YYYYmmdd-HHMMSS.sqlite3.gz | sudo -u zona tee /var/lib/zona/db.sqlite3 >/dev/null
sudo rm -f /var/lib/zona/db.sqlite3-wal /var/lib/zona/db.sqlite3-shm
sudo systemctl start zona-backend
```

## QR Drive

O'rnatilgach: panel → chap menyu **QR Drive → Sozlash ustasi** (bot tokeni → StarGroup NAS login/paroli → xodimlar → sinov QR).
Barcha sozlamalar panelda. Eski kadrlar-bot `.env` fayli: QR Drive → Tizim holati → «Eski bot sozlamalarini import qilish».

### 20 MB dan katta fayllar

Rasmiy `api.telegram.org` botlarga 20 MB dan katta faylni bermaydi. Shuning uchun ikki yo'l bor:

1. **Hech narsa o'rnatmasdan (standart).** Bot katta fayl uchun bir martalik **veb-yuklash havolasi** beradi
   (`/qrdrive/u/<token>`, 24 soat amal qiladi). Fayl brauzerda yuklanadi, QR odatdagidek Telegramga keladi.
   Havola telefondan ochilishi uchun panelda **Sozlamalar → Umumiy → Tashqi manzil** to'g'ri bo'lishi kerak
   (masalan `https://zona.stargroup.uz`).
2. **Lokal Bot API server — 2000 MB gacha to'g'ridan-to'g'ri botga yuborish:**
   ```bash
   sudo bash deploy/telegram-bot-api-setup.sh   # 1-marta: /etc/zona/telegram-bot-api.env yaratadi
   sudo nano /etc/zona/telegram-bot-api.env     # TELEGRAM_API_ID / TELEGRAM_API_HASH (https://my.telegram.org)
   sudo bash deploy/telegram-bot-api-setup.sh   # yig'adi (10–30 daqiqa) va servisni yoqadi
   ```
   Keyin panelda **Bot** bo'limida quyidagilarni bajaring:
   - «Rasmiy serverdan chiqish» tugmasini bosing;
   - Bot API server sifatida `http://127.0.0.1:8081` ni kiriting;
   - «Lokal rejim»ni yoqing;
   - «Maksimal fayl hajmi»ni oshiring (masalan, 2000 MB).

   Bot va worker yangi sozlamani o'zi sezadi.

## Eslatmalar

- Backend standart holatda **1 ta worker** bilan ishlaydi (WebSocket kanal qatlami InMemory). Bir nechta worker: Redis o'rnating va `ZONA_REDIS_URL` + `ZONA_WEB_WORKERS` ni env'ga yozing — kanal qatlami va kesh Redis'ga o'tadi, tarjima bir vaqtda bitta jarayonda (foydali'da `foydali-redis` servisi, `deploy/foydali/foydali-setup.sh`).
- Server faqat 22, 80, 443 portlarini ochiq qoldirsin: `sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable`.
- Bot API kaliti: `/etc/zona/zona.env` dagi `ZONA_BOT_API_KEY`.
