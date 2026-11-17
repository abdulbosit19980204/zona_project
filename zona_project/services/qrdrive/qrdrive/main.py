"""QR Drive API servisi (FastAPI). Panel endpointlari, tashqi API v1, tizim havolalari, Swagger.
Mustaqil jarayon: Zona platformasi, worker yoki bot ishlamay qolsa ham API javob beradi."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api import public, v1
from .api.admin import analytics as admin_analytics
from .api.admin import config as admin_config
from .api.admin import files as admin_files
from .api.admin import ops as admin_ops
from .api.admin import people as admin_people
from .core.config import config
from .core.logging import setup_logging, trace_id
from .db.models import ApiRequest
from .db.session import session_scope
from .services import system

log = logging.getLogger("qrdrive.api")


async def _heartbeat_loop(started: datetime) -> None:
    while True:
        with suppress(Exception):
            await system.beat("api", started=started)
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await system.bootstrap()
    task = asyncio.create_task(_heartbeat_loop(datetime.now(timezone.utc)))
    log.info("QR Drive API ishga tushdi")
    yield
    task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(
        title="QR Drive API",
        version=system.VERSION,
        description=(
            "Fayl → saqlash joyi (Synology, lokal disk, ...) → ommaviy havola → **QR kod**.\n\n"
            "Autentifikatsiya: `Authorization: Bearer qd_live_...` (kalit admin panelda yaratiladi).\n"
            "Takroriy so'rovdan himoya: `Idempotency-Key` sarlavhasi.\n"
            "Webhook imzosi: `X-QRDrive-Signature: sha256=<HMAC-SHA256(body, secret)>`."
        ),
        lifespan=lifespan,
        docs_url=f"{config.prefix}/api/docs",
        redoc_url=f"{config.prefix}/api/redoc",
        openapi_url=f"{config.prefix}/api/openapi.json",
    )

    @app.middleware("http")
    async def trace(request: Request, call_next):
        tid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        trace_id.set(tid)
        start = time.perf_counter()
        response = await call_next(request)
        ms = int((time.perf_counter() - start) * 1000)
        response.headers["X-Request-Id"] = tid
        path = request.url.path
        if path.startswith(f"{config.prefix}/api/v1/") and not path.endswith("/health"):
            with suppress(Exception):
                async with session_scope() as s:
                    fwd = request.headers.get("x-forwarded-for", "")
                    s.add(ApiRequest(api_key_id=getattr(request.state, "api_key_id", None), method=request.method,
                                     path=path[:300], status_code=response.status_code, duration_ms=ms,
                                     ip=(fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else ""))))
                    await s.commit()
        return response

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        fields = sorted({".".join(str(p) for p in e.get("loc", [])[1:]) for e in exc.errors()})
        return JSONResponse({"detail": "Ma'lumot to'liq yoki to'g'ri emas" + (f": {', '.join(f for f in fields if f)}" if fields else ""),
                             "fields": fields}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        log.exception("kutilmagan xato")
        return JSONResponse({"detail": "Kutilmagan xato yuz berdi. Birozdan keyin qayta urinib ko'ring.",
                             "trace_id": trace_id.get()}, status_code=500)

    admin = APIRouter(prefix=f"{config.prefix}/api/admin", include_in_schema=False)
    for r in (admin_files.router, admin_people.router, admin_config.router, admin_ops.router, admin_analytics.router):
        admin.include_router(r)
    app.include_router(admin)
    app.include_router(v1.router, prefix=f"{config.prefix}/api")
    app.include_router(public.router, prefix=config.prefix)

    @app.get(f"{config.prefix}/health", include_in_schema=False)
    async def health():
        return {"ok": True}

    return app


app = create_app()


def run_api() -> None:
    import uvicorn

    setup_logging("api", config.log_level)
    uvicorn.run("qrdrive.main:app", host=config.host, port=config.port, proxy_headers=True,
                forwarded_allow_ips="127.0.0.1", log_config=None)


if __name__ == "__main__":
    run_api()
