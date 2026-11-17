"""Gunicorn: ASGI (HTTP + WebSocket) — uvicorn worker orqali.

Bitta worker: WebSocket xabarlari (Channels InMemoryChannelLayer), fondagi tarjima va qidiruv indeksi
jarayon ichida saqlanadi. Bir nechta worker kerak bo'lsa — avval Redis kanal qatlamini ulang (README).
Uvicorn worker bitta jarayonda yuzlab parallel so'rovni asinxron ko'taradi — ichki tizim uchun yetarli.
"""
bind = "127.0.0.1:8000"
workers = 1
worker_class = "uvicorn_worker.UvicornWorker"
timeout = 180            # AI so'rovlari (qayta urinish bilan) uzoq davom etishi mumkin
graceful_timeout = 30
keepalive = 5
forwarded_allow_ips = "127.0.0.1"   # nginx'dan kelgan X-Forwarded-* sarlavhalariga ishonish
accesslog = "-"
errorlog = "-"
loglevel = "info"
