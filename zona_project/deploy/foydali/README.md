# Foydali — foydali.xisobchim.uz

Zona va QR Drive bu serverda **bio-lab.uz** bilan birga ishlaydi. Boshqa saytlarga tegmaslik uchun hamma narsa
`foydali` nomi bilan alohida qilingan.

| Qism | Qanday ishlaydi | Port |
|---|---|---|
| Backend (Django + WebSocket) | systemd `foydali-backend` (gunicorn + uvicorn, `ZONA_WEB_WORKERS` ta worker) | 127.0.0.1:8020 |
| Redis (WebSocket + kesh) | systemd `foydali-redis` — faqat unix socket `/run/foydali-redis/redis.sock` | — |
| QR Drive API | systemd `foydali-qrdrive-api` | 127.0.0.1:8120 |
| QR Drive worker / bot | systemd `foydali-qrdrive-worker`, `foydali-qrdrive-bot` | — |
| Frontend (Next.js) | **pm2** `foydali-frontend` | 127.0.0.1:3020 |
| Boshqaruv markazi | systemd `foydali-control` → `https://foydali.xisobchim.uz/control/` | 127.0.0.1:8920 |
| Zaxira | `foydali-backup.timer`, har kuni 03:30, 14 kun saqlanadi | — |

bio-lab.uz ishlatadigan portlar: **3000** (pm2 `biolab-frontend`) va **8010** (`biolab.service`). Bu portlar band qilinmaydi.

## Fayllar
- **Kod:** `/root/zona_project/zona_project`. Servislar uni faqat o'qiydi va `foydali` foydalanuvchisi nomidan ishlaydi.
- **Sozlamalar:** `/etc/foydali/`
  - `foydali.env`, `foydali-qrdrive.env`, `foydali-control.env` — kalitlar shu yerda, **zaxiralab qo'ying**;
  - `foydali-gunicorn.conf.py`, `foydali.ecosystem.config.cjs`, `foydali-control.services.json`.
- **Bazalar:** `/var/lib/foydali/db.sqlite3` va `/var/lib/foydali/qrdrive/qrdrive.sqlite3`.
- **Zaxiralar:** `/var/lib/foydali/backups/<sana>/`.
- **nginx:** `/etc/nginx/sites-available/foydali`, HTTPS certbot orqali va avtomatik yangilanadi.
- **Boshqaruv markazining pm2 wrapper'i:** `/usr/local/sbin/foydali-pm2`. U faqat `foydali-frontend`ni boshqaradi.

## Yangilash
```bash
cd /root/zona_project && git pull
bash zona_project/deploy/foydali/foydali-setup.sh
```
Skriptni qayta ishga tushirish xavfsiz: bazalar, kalitlar va sertifikat saqlanadi. Skript paketlarni o'rnatadi,
migratsiyani bajaradi, frontendni yig'adi va servislarni qayta ishga tushiradi.

## Foydali buyruqlar
```bash
systemctl status foydali-backend foydali-qrdrive-api foydali-qrdrive-worker foydali-qrdrive-bot
journalctl -u foydali-qrdrive-bot -f
pm2 logs foydali-frontend
pm2 restart foydali-frontend
```
