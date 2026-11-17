"""Ishga tushirish sozlamalari (.env / muhit o'zgaruvchilari). Qolgan hamma sozlama bazada, admin paneldan."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # services/qrdrive


def _load_dotenv(path: Path) -> None:
    """Oddiy .env o'qiydi (muhitda bor qiymatlar ustun)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_dotenv(ROOT / ".env")

DEV_SECRET = "dev-only-change-me"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Config:
    debug: bool = field(default_factory=lambda: _env("QRDRIVE_DEBUG", "1") in ("1", "true", "yes"))
    data_dir: Path = field(default_factory=lambda: Path(_env("QRDRIVE_DATA_DIR") or ROOT / "data"))
    db_path: str = field(default_factory=lambda: _env("QRDRIVE_DB_PATH"))
    # Maxfiy qiymatlarni bazada shifrlash kaliti (yo'qolsa — tokenlar/parollarni qayta kiritish kerak)
    master_key: str = field(default_factory=lambda: _env("QRDRIVE_MASTER_KEY", DEV_SECRET))
    # Zona (asosiy platforma) JWT kaliti: panel foydalanuvchilari shu token bilan kiradi (SSO)
    sso_secret: str = field(default_factory=lambda: _env("QRDRIVE_SSO_SECRET") or _env("ZONA_JWT_SECRET", DEV_SECRET))
    public_base_url: str = field(default_factory=lambda: _env("QRDRIVE_PUBLIC_BASE_URL", "http://127.0.0.1:3000").rstrip("/"))
    prefix: str = "/qrdrive"
    tz: str = field(default_factory=lambda: _env("TZ", "Asia/Tashkent") or "Asia/Tashkent")
    host: str = field(default_factory=lambda: _env("QRDRIVE_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(_env("QRDRIVE_PORT", "8100")))
    log_level: str = field(default_factory=lambda: _env("QRDRIVE_LOG_LEVEL", "INFO"))
    # Eski kadrlar-bot .env fayli: birinchi ishga tushishda sozlamalar shundan import qilinadi
    legacy_env: str = field(default_factory=lambda: _env("QRDRIVE_LEGACY_ENV"))
    # Bo'sh bazada standart saqlash joyini (StarGroup NAS) yaratish
    seed_default_storage: bool = field(default_factory=lambda: _env("QRDRIVE_SEED_DEFAULT", "1") in ("1", "true", "yes"))

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        if not self.db_path:
            self.db_path = str(self.data_dir / "qrdrive.sqlite3")
        if not self.debug and DEV_SECRET in (self.master_key, self.sso_secret):
            raise SystemExit("QRDRIVE_MASTER_KEY va QRDRIVE_SSO_SECRET ni o'rnating (deploy/qrdrive.env.example).")

    @property
    def spool_dir(self) -> Path:
        return self.data_dir / "spool"

    @property
    def local_storage_default(self) -> Path:
        return self.data_dir / "files"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.spool_dir, self.backups_dir, self.assets_dir):
            d.mkdir(parents=True, exist_ok=True)


config = Config()
