# Servislar boshqaruv markazi

Barcha servislarni **bitta buyruq** bilan ishga tushiradi va veb-sahifada nazorat qiladi:
holat, javob vaqti, ishlash vaqti, start / stop / restart (bittalab yoki hammasi), jonli loglar, so'nggi hodisalar.
Yiqilgan servisni avtomatik qayta ishga tushiradi (5 daqiqada 5 martagacha; undan keyin to'xtab, sababini ko'rsatadi).

Faqat Python standart kutubxonasi — boshqa servislardan va ularning paketlaridan to'liq mustaqil:
Zona yoki QR Drive yiqilsa ham sahifa ochiladi va ularni qayta ishga tushira oladi.

## Lokal kompyuterda

```bash
start-all.cmd            # Windows (loyiha papkasida)
./start-all.sh           # Linux / macOS
# yoki: python services/control/control.py [--no-autostart] [--port 8900]
```

Sahifa: http://127.0.0.1:8900. Birinchi ishga tushishda parol konsolga chiqadi va
`services/control/data/initial-password.txt` ga yoziladi (o'zgartirish: `CONTROL_PASSWORD` muhit o'zgaruvchisi).
Panelning chap menyusi pastida **«Servislar markazi»** havolasi bor.

Port band bo'lsa (masalan, siz o'zingiz `npm run dev` ni ishga tushirgansiz) — servis «Tashqi jarayon» deb ko'rsatiladi
va ikkinchi nusxa ochilmaydi. Servislar ro'yxati: `services/control/services.json`.

## Serverda (Ubuntu)

`deploy/install.sh` o'zi o'rnatadi (`deploy/control-setup.sh`):
- `zona-control` systemd servisi (127.0.0.1:8900), nginx: `https://<domen>/control/`;
- rejim **systemd**: `systemctl start/stop/restart` va `journalctl` orqali (`deploy/control.services.json`);
- `zona` foydalanuvchisiga faqat shu servislarni boshqarish ruxsati (`/etc/sudoers.d/zona-control`);
- parol: `sudo grep CONTROL_PASSWORD /etc/zona/control.env`.

Tavsiya: nginx'da `/control/` ni ishonchli IP'lar bilan cheklang (`deploy/nginx/zona.conf` dagi izohga qarang).

## Xavfsizlik

Parol PBKDF2 (200 000 iteratsiya) bilan saqlanadi; seans — imzolangan, HttpOnly + SameSite=Strict cookie (12 soat);
o'zgartiruvchi so'rovlar `X-Control` sarlavhasini talab qiladi (CSRF); 15 daqiqada 10 ta noto'g'ri urinishdan keyin bloklanadi.

## Testlar

```bash
python -m unittest discover -s services/control/tests
```
