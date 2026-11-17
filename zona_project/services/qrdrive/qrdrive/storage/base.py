"""Saqlash joyi interfeysi. Har bir provayder (Synology, lokal disk, keyinchalik Drive/S3/WebDAV) shuni bajaradi."""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


@dataclass
class HealthResult:
    ok: bool
    latency_ms: int | None = None
    error_kind: str = ""
    message: str = ""


@dataclass
class Quota:
    used: int
    total: int


@dataclass
class RemoteFile:
    path: str
    id: str = ""
    size: int | None = None


@dataclass
class PublicLink:
    url: str
    id: str = ""
    expires_at: datetime | None = None


@dataclass
class RemoteEntry:
    name: str
    path: str
    is_dir: bool
    size: int | None = None
    modified: datetime | None = None


class StorageProvider(Protocol):
    kind: str
    supports_links: bool

    async def test_connection(self) -> HealthResult: ...
    async def get_quota(self) -> Quota | None: ...
    async def ensure_folder(self, path: str) -> None: ...
    async def upload(self, local_path: Path, dest_folder: str, filename: str) -> RemoteFile: ...
    async def create_public_link(self, remote: RemoteFile, expire_at: datetime | None = None,
                                 password: str | None = None) -> PublicLink: ...
    async def revoke_public_link(self, link_id: str) -> None: ...
    async def list(self, path: str) -> list[RemoteEntry]: ...
    def open_stream(self, path: str) -> AsyncIterator[bytes]: ...
    async def thumbnail(self, path: str) -> bytes | None: ...
    async def move(self, src: str, dst_folder: str) -> str: ...
    async def rename(self, path: str, new_name: str) -> str: ...
    async def delete(self, path: str) -> None: ...
    async def close(self) -> None: ...


async def file_chunks(path: Path, size: int = 1024 * 1024) -> AsyncIterator[bytes]:
    """Katta faylni xotiraga to'liq yuklamasdan bo'laklab yuborish."""
    with open(path, "rb") as fh:
        while chunk := fh.read(size):
            yield chunk


def join(*parts: str) -> str:
    """Masofaviy yo'llarni '/' bilan birlashtiradi."""
    out = "/".join(p.strip("/") for p in parts if p and p.strip("/"))
    return "/" + out


def config_fields(kind: str) -> list[dict[str, Any]]:
    """Panel uchun forma maydonlari (yorliq, yordam matni, maxfiymi)."""
    return FIELDS.get(kind, [])


FIELDS: dict[str, list[dict[str, Any]]] = {
    "synology": [
        {"key": "url", "label": "DSM manzili", "placeholder": "https://file.stargroup.uz",
         "help": "NAS manzili (brauzerda DSM qaysi manzilda ochilsa, o'sha). QuickConnect emas."},
        {"key": "username", "label": "Foydalanuvchi", "placeholder": "qr-bot",
         "help": "Alohida foydalanuvchi oching: papkaga yozish huquqi bilan, 2 bosqichli tekshiruvi o'chirilgan."},
        {"key": "password", "label": "Parol", "secret": True, "help": "Shu foydalanuvchining paroli. Shifrlangan holda saqlanadi."},
        {"key": "drive_folder", "label": "Synology Drive papkasi (havola yoki ID)", "placeholder": "https://file.stargroup.uz/#file_id=984701843502314054",
         "help": "Synology Drive'da papkani oching va brauzerdagi manzilni shu yerga qo'ying. Asosiy papka avtomatik aniqlanadi. Bo'sh bo'lsa — pastdagi «Asosiy papka» ishlatiladi."},
        {"key": "verify_ssl", "label": "SSL sertifikatini tekshirish", "type": "bool", "default": True,
         "help": "NAS'da o'zi imzolagan sertifikat bo'lsa (brauzer «xavfsiz emas» desa) — o'chiring."},
    ],
    "local": [
        {"key": "root", "label": "Papka (serverda)", "placeholder": "/var/lib/zona/qrdrive/files",
         "help": "Fayllar shu papkaga yoziladi. Tarmoq papkasi (SMB) bo'lsa, avval serverga ulab (mount) qo'ying."},
    ],
    "webdav": [
        {"key": "url", "label": "WebDAV manzili", "placeholder": "https://cloud.firma.uz/remote.php/dav/files/qrbot",
         "help": "Nextcloud: Fayllar → pastki chapdagi «Sozlamalar» → WebDAV manzili. Boshqa WebDAV serverlar ham ishlaydi."},
        {"key": "username", "label": "Foydalanuvchi"},
        {"key": "password", "label": "Parol (ilova paroli)", "secret": True,
         "help": "Nextcloud: Shaxsiy sozlamalar → Xavfsizlik → «Yangi ilova paroli» yarating."},
        {"key": "nextcloud", "label": "Nextcloud (ommaviy havola yaratish)", "type": "bool", "default": True,
         "help": "Yoqilsa — Nextcloud'ning o'z ommaviy havolasi. O'chirilsa — tizim havolasi ishlatiladi."},
        {"key": "verify_ssl", "label": "SSL sertifikatini tekshirish", "type": "bool", "default": True},
    ],
    "s3": [
        {"key": "endpoint", "label": "Endpoint", "placeholder": "https://s3.amazonaws.com",
         "help": "AWS uchun bo'sh qoldiring. MinIO/Wasabi/Backblaze B2/Cloudflare R2 — provayder bergan S3 manzili."},
        {"key": "region", "label": "Region", "placeholder": "us-east-1"},
        {"key": "bucket", "label": "Bucket nomi"},
        {"key": "access_key", "label": "Access key"},
        {"key": "secret_key", "label": "Secret key", "secret": True},
        {"key": "path_style", "label": "Path-style manzil (MinIO uchun)", "type": "bool", "default": False},
    ],
    "gdrive": [
        {"key": "auth", "label": "Ulanish usuli", "type": "select", "default": "service_account",
         "options": [["service_account", "Service Account (JSON kalit)"], ["oauth", "Google bilan ulash (OAuth)"]],
         "help": "Service Account — tavsiya etiladi (Shared Drive bilan). OAuth — oddiy Google akkaunt Drive'i."},
        {"key": "service_account_json", "label": "Service Account JSON", "type": "textarea", "secret": True, "when": "service_account",
         "help": "Google Cloud Console → IAM → Service Accounts → Keys → «Add key» → JSON. Faylning to'liq matnini qo'ying. Service account'ning o'z joyi yo'q — Shared Drive tanlash majburiy va unga service account'ni «Content manager» qilib qo'shing."},
        {"key": "shared_drive_id", "label": "Shared Drive ID", "when": "service_account",
         "help": "Drive'da Shared Drive'ni oching: manzildagi /drive/folders/<ID> qismi."},
        {"key": "client_id", "label": "OAuth Client ID", "when": "oauth",
         "help": "Google Cloud Console → APIs & Services → Credentials → OAuth client (Web). Redirect URI: <sayt>/qrdrive/api/admin/storages/google/callback"},
        {"key": "client_secret", "label": "OAuth Client secret", "secret": True, "when": "oauth"},
        {"key": "root_folder_id", "label": "Asosiy papka ID (ixtiyoriy)",
         "help": "Fayllar shu papka ichiga tushadi. Bo'sh — Shared Drive (yoki My Drive) ildizi."},
    ],
}

KINDS = {
    "synology": {"label": "Synology NAS / Drive", "links": True},
    "gdrive": {"label": "Google Drive", "links": True},
    "s3": {"label": "S3 (AWS, MinIO, Wasabi, B2, R2)", "links": True},
    "webdav": {"label": "WebDAV / Nextcloud", "links": True},
    "local": {"label": "Lokal disk / tarmoq papkasi", "links": False},
}
