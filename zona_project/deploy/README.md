# Serverga o'rnatish (Ubuntu + gunicorn + nginx)

Bitta Ubuntu 22.04/24.04 server: **nginx** (80/443) → **Next.js** (127.0.0.1:3000) va **Django/Channels** (gunicorn + uvicorn worker, 127.0.0.1:8000). Baza — SQLite, `/var/lib/zona/db.sqlite3`.

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
| `/var/lib/zona/db.sqlite3` | Ishchi baza |
| `/var/lib/zona/backups/` | Kunlik zaxira (02:30, 14 kun saqlanadi) |
| `/opt/zona` | Loyiha papkasiga symlink |

**`ZONA_ENCRYPTION_KEY` ni alohida saqlab qo'ying.** AI kalitlari shu bilan shifrlanadi — yo'qolsa, admin panelda AI kalitlarini qaytadan kiritish kerak bo'ladi.

## Boshqaruv

```bash
systemctl status zona-backend zona-frontend
journalctl -u zona-backend -f            # backend jurnali
journalctl -u zona-frontend -f
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

## Eslatmalar

- Backend **1 ta worker** bilan ishlaydi: WebSocket kanal qatlami (InMemory), fon tarjima oqimi va qidiruv keshi bitta jarayonda. Bu o'nlab foydalanuvchiga bemalol yetadi. Kengaytirish kerak bo'lsa — Redis channel layer + PostgreSQL.
- Server faqat 22, 80, 443 portlarini ochiq qoldirsin: `sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable`.
- Bot API kaliti: `/etc/zona/zona.env` dagi `ZONA_BOT_API_KEY`.
