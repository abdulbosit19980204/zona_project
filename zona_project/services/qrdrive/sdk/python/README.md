# qrdrive-sdk

QR Drive REST API (v1) uchun Python klient va aiogram 3 plagini.

```bash
pip install "qrdrive-sdk[aiogram] @ git+https://github.com/<user>/zona_project.git#subdirectory=zona_project/services/qrdrive/sdk/python"
# yoki lokal: pip install -e services/qrdrive/sdk/python[aiogram]
```

API kalit: QR Drive paneli → **API va integratsiyalar** → **Yangi API kalit** (kalit faqat bir marta ko'rsatiladi).

## Klient

```python
from qrdrive_sdk import QRDriveClient

async with QRDriveClient("https://qr.firma.uz", "qd_live_...") as qd:
    res = await qd.upload("hujjat.pdf", telegram_id=123456789)   # yoki employee_id=..., external_user="..."
    if res.ready:
        print(res.url)
        open("qr.png", "wb").write(res.qr_png)
    elif not res.failed:
        res = await qd.wait_ready(res.id)        # katta fayl — navbatda
    else:
        print(res.error["title"], res.error["hint"])

    png = await qd.make_qr("https://example.com")   # istalgan havoladan QR
```

## aiogram plagini (5 qator)

```python
from qrdrive_sdk.aiogram import create_router

dp.include_router(create_router(
    api_url="https://qr.firma.uz",
    api_key="qd_live_...",
    commands=["qr"],          # None — barcha fayllarga javob beradi
    reply_with_qr=True,
))
```

## Webhook

Kalitga webhook manzili berilsa, `file.completed`, `file.failed`, `link.revoked` hodisalari POST qilinadi.
Imzo: `X-QRDrive-Signature: sha256=<HMAC-SHA256(body, webhook_secret)>`.
