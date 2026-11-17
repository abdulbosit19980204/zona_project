# Saqlash joylari: ulash, tekshirish va xatolarni tuzatish

Panel: **QR Drive → Saqlash joylari**. Har bir saqlash joyi kartasida **«Diagnostika»** tugmasi bor.
U quyidagi bosqichlarni ketma-ket tekshiradi va qaysi bosqichda, nima uchun to'xtaganini hamda yechimini ko'rsatadi
(sinov fayli yaratiladi va darhol o'chiriladi):

| # | Bosqich | Nima tekshiriladi |
|---|---|---|
| 1 | Sozlama to'liqligi | login, parol, kalitlar kiritilganmi |
| 2 | Ulanish va login | server javob beradimi, login/parol to'g'rimi |
| 3 | Asosiy papka | papka bormi (Synology Drive havolasi bo'lsa — yo'l avtomatik aniqlanadi; yo'q papka yaratiladi) |
| 4 | Yozish | sinov fayli yuklanadimi |
| 5 | Ommaviy havola | havola yaratiladimi (keyin bekor qilinadi) |
| 6 | Bo'sh joy | kvota (ma'lumot bo'lsa) |

Xato bilan tugagan fayllar **Xatolar markazi**da turadi. Muammo tuzatilgach **«Qayta urinish»** bosing.

---

## Synology NAS / Synology Drive (standart: file.stargroup.uz)

1. DSM → **Boshqaruv paneli → Foydalanuvchi va guruh** → bot uchun foydalanuvchi (masalan `qr-bot`) oching yoki mavjudini ishlating.
2. Shu foydalanuvchining **«Ilovalar»** bo'limida **Synology Drive** (yoki File Station) ruxsat etilgan bo'lsin — bittasi yetarli.
   QR Drive DSM'ga avval Synology Drive sessiyasi, keyin File Station sessiyasi bilan kirib ko'radi.
3. Fayllar tushadigan jamoa papkasiga **O'qish/Yozish** huquqi.
4. Shu foydalanuvchida **2 bosqichli tekshiruv o'chiq** bo'lsin.
5. Synology Drive'da papkani oching, manzil satridagi havolani (`https://file.stargroup.uz/#file_id=...`) **«Synology Drive papkasi»** maydoniga qo'ying.
6. **Diagnostika** → hamma bosqich yashil bo'lishi kerak.

Tekshirilgan holat (file.stargroup.uz, 2026-11-17): `#file_id=984701843502314054` → `/team-folders/Timur/qrable` →
File Station yo'li `/Timur/qrable`. `caspar` foydalanuvchisiga File Station ilovasi yopiq (sessiya `FileStation` → kod 405),
Synology Drive ochiq — QR Drive avtomatik Drive sessiyasiga o'tadi. Ommaviy havolalar `gofile.me` (Synology QuickConnect) domenida beriladi;
o'z domeningizda havola kerak bo'lsa, saqlash joyida **Havola turi → «Tizim havolasi»** ni tanlang.

### DSM login xato kodlari

| Kod | Panelda | Sabab | Yechim |
|---|---|---|---|
| 400 | Login yoki parol noto'g'ri | foydalanuvchi nomi yoki parol xato | Saqlash joylari → Tahrirlash → to'g'ri login/parol |
| 401 | Foydalanuvchi o'chirilgan | akkaunt disabled | DSM → Foydalanuvchi → akkauntni yoqing |
| 402, 405 | Fayl ilovalariga ruxsat yo'q | foydalanuvchiga Synology Drive ham, File Station ham ruxsat etilmagan | DSM → Foydalanuvchi → Ilovalar → Synology Drive'ga ruxsat |
| 403, 404, 406 | 2 bosqichli tekshiruv yoqilgan | bot 2FA kodini kirita olmaydi | 2FA'siz alohida foydalanuvchi oching |
| 407 | Server IP bloklangan | ko'p noto'g'ri urinishdan keyin avtomatik blok | DSM → Xavfsizlik → Hisob → Avtomatik bloklash → IP'ni olib tashlang |
| 408–410 | Parol muddati tugagan | DSM parolni almashtirishni talab qiladi | DSM'ga shu foydalanuvchi bilan kirib parolni yangilang |

### Fayl amallari xatolari

| Kod | Panelda | Yechim |
|---|---|---|
| 105, 407 (amal) | Papkaga yozish uchun ruxsat yo'q | jamoa papkasiga O'qish/Yozish huquqi bering |
| 408 | Papka topilmadi | Synology Drive havolasini yoki «Asosiy papka»ni tekshiring |
| 415, 416 | Joy qolmagan | keraksiz fayllarni o'chiring yoki boshqa saqlash joyini asosiy qiling |
| ulanib bo'lmaydi | Saqlash joyi javob bermayapti | NAS yoqilganini, internetni, manzil va portni tekshiring; o'z sertifikati bo'lsa «SSL tekshirish»ni o'chiring |

---

## Google Drive

**Service Account (tavsiya):**
1. console.cloud.google.com → loyiha → **Google Drive API** ni yoqing.
2. IAM → Service Accounts → Create → Keys → Add key → **JSON**. Fayl matnini «Service Account JSON» maydoniga qo'ying.
3. Google Drive'da **Shared Drive** oching → Manage members → service account email'ini **Content manager** qiling.
4. Shared Drive manzilidagi `/folders/<ID>` qismini «Shared Drive ID» ga yozing → Diagnostika.

**OAuth («Google bilan ulash»):** Credentials → OAuth client (Web), Redirect URI:
`<sayt manzili>/qrdrive/api/admin/storages/google/callback`. Client ID/secret → Saqlash → **«Google bilan ulash»**.

| Panelda | Sabab | Yechim |
|---|---|---|
| Login noto'g'ri | JSON noto'g'ri/to'liq emas, kalit o'chirilgan, OAuth bekor qilingan | yangi JSON kalit yoki qayta «Google bilan ulash» |
| Yozish uchun ruxsat yo'q | service account Shared Drive'ga qo'shilmagan | Shared Drive → Manage members → Content manager |
| Joy qolmagan | Drive kvotasi tugagan (service account'ning o'z joyi yo'q) | Shared Drive ishlating |
| Havolaga parol qo'yib bo'lmaydi | Google cheklovi | parol kerak bo'lsa — «Tizim havolasi» |

---

## S3 (AWS, MinIO, Wasabi, Backblaze B2, Cloudflare R2)

1. Bucket yarating (ommaviy bo'lishi shart emas).
2. Faqat shu bucket uchun `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, `s3:ListBucket` ruxsatli kalit.
3. AWS: Endpoint bo'sh, Region — bucket regioni. Boshqalar: provayder endpoint'i; MinIO — «Path-style» yoqilgan.
4. S3 havolasi maksimal **7 kun**. Muddatsiz yoki parolli havola kerak bo'lsa — QR Drive avtomatik tizim havolasini beradi.

| Panelda | Sabab | Yechim |
|---|---|---|
| Login noto'g'ri | `InvalidAccessKeyId` / `SignatureDoesNotMatch` | kalitlarni va regionni tekshiring |
| Ruxsat yo'q | `AccessDenied` | kalit siyosatiga yuqoridagi ruxsatlarni qo'shing |
| Topilmadi | `NoSuchBucket` | bucket nomi va endpoint'ni tekshiring |

---

## WebDAV / Nextcloud

1. Nextcloud → Shaxsiy sozlamalar → Xavfsizlik → **yangi ilova paroli** (asosiy parol emas).
2. Fayllar → pastki chapda «Sozlamalar» → **WebDAV manzili** (`.../remote.php/dav/files/<foydalanuvchi>`).
3. Ommaviy havola uchun Nextcloud'da «Share via link» yoqilgan bo'lsin.

| Panelda | HTTP | Yechim |
|---|---|---|
| Login noto'g'ri | 401 | ilova parolini qayta yarating |
| Ruxsat yo'q | 403 | papkaga yozish huquqi |
| Topilmadi | 404 | WebDAV manzilini tekshiring |
| Joy qolmagan | 507 | kvotani oshiring |

---

## Lokal disk / tarmoq papkasi

Serverda papka yarating, xizmat foydalanuvchisiga yozish huquqi bering (`sudo chown -R zona:zona <papka>`).
SMB bo'lsa — avval `/etc/fstab` orqali mount qiling. Havolalar tizim orqali (`/qrdrive/s/...`).

---

## Yangi turdagi saqlash joyini qo'shish (dasturchilar uchun)

1. `qrdrive/storage/<nom>.py` — `StorageProvider` interfeysini bajaradigan klass (`storage/base.py`).
   Xatolarni `core/errors.py` dagi turlarga aylantiring (`StorageAuthError`, `StoragePermission`, `StorageNotFound`, `StorageQuota`, `StorageUnavailable`) —
   shunda panel avtomatik ravishda sabab va yechimni ko'rsatadi.
2. `storage/base.py`: `FIELDS[<nom>]` (forma maydonlari, `help` matnlari) va `KINDS[<nom>]` (`label`, `links`, `guide` — qadamma-qadam qo'llanma).
3. `storage/registry.py`: `build()` ga qo'shing, `REQUIRED` ga majburiy maydonlarni yozing.
4. `tests/test_providers.py` ga soxta server (respx) bilan test.
