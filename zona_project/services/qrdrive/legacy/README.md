# Kadrlar bot — fayl → Synology → QR kod

Xodim botga fayl yuboradi → bot uni `SYNO_BASE_FOLDER/<username>/` ga saqlaydi →
ommaviy havola yaratadi → havolani QR kod rasmi bilan qaytaradi. Fayl hajmi 100 MB gacha.

## 1. Tayyorgarlik

1. **Bot**: @BotFather → `/newbot` → tokenni oling.
2. **API ID / HASH** (100 MB uchun kerak): https://my.telegram.org → *API development tools* →
   ilova yarating → `api_id` va `api_hash` ni oling.
3. **Synology foydalanuvchisi**: *Control Panel → User* → `qr-bot` yarating:
   - `Kadrlar` papkasiga **Read/Write** huquqi;
   - *Applications* bo'limida **File Station** ga ruxsat;
   - 2FA yoqilmagan bo'lsin.
4. **Papka**: `Kadrlar` umumiy papkasini (yoki Synology Drive team folder) yarating.
5. **Havola domeni**: *Control Panel → External Access* da tashqi manzil (DDNS/domen) sozlangan
   bo'lsin — aks holda QR'dagi havola faqat ichki tarmoqda ochiladi.

## 2. Botni lokal serverga o'tkazish (bir martalik)

Lokal Bot API serverdan foydalanishdan oldin botni rasmiy serverdan chiqarish kerak.
Brauzerda oching (TOKEN o'rniga o'z tokeningiz):

```
https://api.telegram.org/botTOKEN/logOut
```

`{"ok":true,"result":true}` chiqsa — tayyor.

## 3. Synology'da ishga tushirish (Container Manager)

1. Ushbu `kadrlar-bot` papkasini NAS'ga ko'chiring (masalan `/docker/kadrlar-bot`).
2. `.env.example` dan nusxa olib `.env` deb nomlang va to'ldiring.
3. *Container Manager → Project → Create* → yo'l: `/docker/kadrlar-bot` →
   "Use existing docker-compose.yml" → *Build/Start*.
4. Botga `/id` yozing, ID'ni `.env` dagi `ALLOWED_USER_IDS` ga qo'shing, loyihani qayta ishga tushiring.

Yoki SSH orqali:

```bash
cd /volume1/docker/kadrlar-bot && sudo docker compose up -d --build
```

Loglar: `sudo docker compose logs -f bot`

## Eslatmalar

- Bir xil nomli fayllar ustma-ust yozilmasligi uchun nomga sana-vaqt qo'shiladi.
- Username bo'lmagan xodim uchun papka `Ism_ID` ko'rinishida bo'ladi.
- Rasmlarni «Fayl sifatida» yuborish tavsiya etiladi — aks holda Telegram ularni siqadi.
