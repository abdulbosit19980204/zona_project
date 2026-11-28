"""Gunicorn: ASGI (HTTP + WebSocket) — uvicorn worker orqali.

Worker soni — ZONA_WEB_WORKERS (standart 1). Bir nechta worker FAQAT ZONA_REDIS_URL bo'lsa ishlatiladi: WebSocket
xabarlari va umumiy kesh (login urinishlari, tarjima qulfi) Redis orqali jarayonlar o'rtasida bo'lishiladi.
Redis'siz har doim 1 worker (InMemory kanal qatlami faqat bitta jarayon ichida ishlaydi).
Nega bir nechta: Django'ning sinxron view'lari bitta worker ichida navbat bilan bajariladi — bitta og'ir so'rov
(AI, rasm guruhlash) qolganlarini kutdiradi; N worker = N ta parallel so'rov.
"""
import os

_redis = bool(os.environ.get("ZONA_REDIS_URL", "").strip())
try:
    _want = int(os.environ.get("ZONA_WEB_WORKERS", "1") or 1)
except ValueError:
    _want = 1

bind = "127.0.0.1:8000"
workers = max(1, min(_want, 8)) if _redis else 1
worker_class = "uvicorn_worker.UvicornWorker"
timeout = 180            # AI so'rovlari (qayta urinish bilan) uzoq davom etishi mumkin
graceful_timeout = 30
keepalive = 5
forwarded_allow_ips = "127.0.0.1"   # nginx'dan kelgan X-Forwarded-* sarlavhalariga ishonish
accesslog = "-"
errorlog = "-"
loglevel = "info"
