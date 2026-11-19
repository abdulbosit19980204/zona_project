"""QR Drive bazasi (o'z bazasi — Zona bazasidan mustaqil)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def now() -> datetime:
    return datetime.now(timezone.utc)


class UTC(TypeDecorator):
    """SQLite vaqt zonasini saqlamaydi — bazada UTC, o'qishda tz qo'shiladi."""
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


class Base(DeclarativeBase):
    type_annotation_map = {datetime: UTC, dict[str, Any]: JSON, list[Any]: JSON}


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    secret_enc: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)


class Storage(Base):
    __tablename__ = "storages"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(32))  # synology | local
    config_enc: Mapped[str] = mapped_column(Text, default="")
    base_folder: Mapped[str] = mapped_column(String(500), default="/")
    link_mode: Mapped[str] = mapped_column(String(16), default="provider")  # provider | system
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="unknown")  # unknown | ok | down
    last_check_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quota_used: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    quota_total: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now)


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    department: Mapped[str] = mapped_column(String(200), default="")
    position: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    # Papka nomi. Bo'sh bo'lsa — birinchi faylda Telegram username'dan olinadi va keyin o'zgarmaydi (eski bot kabi)
    folder: Mapped[str] = mapped_column(String(120), default="")
    storage_id: Mapped[int | None] = mapped_column(ForeignKey("storages.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | blocked | archived
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=now)

    accounts: Mapped[list[TgAccount]] = relationship(back_populates="employee", lazy="selectin")


class TgAccount(Base):
    __tablename__ = "tg_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[str] = mapped_column(String(128), default="")
    lang: Mapped[str] = mapped_column(String(4), default="uz")
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    # registering (botda ro'yxatdan o'tmoqda) | pending (kirish so'rovi) | active | blocked | rejected | detached
    status: Mapped[str] = mapped_column(String(16), default="pending")
    first_seen: Mapped[datetime] = mapped_column(default=now)
    last_seen: Mapped[datetime] = mapped_column(default=now)
    # Telegram ma'lumotlari (to'liq): telefon (kontakt orqali tasdiqlangan), premium, profil rasmi, getChat natijasi
    phone: Mapped[str] = mapped_column(String(32), default="")
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    photo: Mapped[str] = mapped_column(String(200), default="")  # data/assets/avatars/<fayl>
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=True)
    # Ro'yxatdan o'tish: joriy qadam va kiritilgan ma'lumotlar (F.I.Sh., bo'lim, lavozim)
    reg_state: Mapped[str] = mapped_column(String(16), default="")
    reg_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=True)
    registered_at: Mapped[datetime | None] = mapped_column(nullable=True)

    employee: Mapped[Employee | None] = relationship(back_populates="accounts", lazy="selectin")

    @property
    def display(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name or (f"@{self.username}" if self.username else str(self.telegram_id))


class TgAccountHistory(Base):
    __tablename__ = "tg_account_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("tg_accounts.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String(32))
    old: Mapped[str] = mapped_column(String(200), default="")
    new: Mapped[str] = mapped_column(String(200), default="")
    at: Mapped[datetime] = mapped_column(default=now)


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    replace: Mapped[bool] = mapped_column(Boolean, default=True)  # eski akkauntlarni uzish
    created_at: Mapped[datetime] = mapped_column(default=now)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    used_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class FileRecord(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("tg_accounts.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="telegram")  # telegram | web | api
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    external_user: Mapped[str] = mapped_column(String(120), default="")
    actor: Mapped[str] = mapped_column(String(120), default="")
    storage_id: Mapped[int | None] = mapped_column(ForeignKey("storages.id", ondelete="SET NULL"), nullable=True)
    remote_path: Mapped[str] = mapped_column(Text, default="")
    remote_id: Mapped[str] = mapped_column(Text, default="")
    original_name: Mapped[str] = mapped_column(String(300), default="")
    stored_name: Mapped[str] = mapped_column(String(300), default="")
    size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime: Mapped[str] = mapped_column(String(120), default="")
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    caption: Mapped[str] = mapped_column(Text, default="")
    link_url: Mapped[str] = mapped_column(Text, default="")
    link_id: Mapped[str] = mapped_column(String(200), default="")
    link_kind: Mapped[str] = mapped_column(String(16), default="")  # provider | system
    link_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    link_has_password: Mapped[bool] = mapped_column(Boolean, default=False)
    # public — havola bilan istalgan odam; private — faqat saqlash joyida ruxsati borlar (Synology Drive /d/f/...)
    link_visibility: Mapped[str] = mapped_column(String(8), default="")
    downloads: Mapped[int] = mapped_column(Integer, default=0)
    # awaiting (botda havola turi tanlanishi kutilmoqda) | queued | processing | retrying | delivered | failed
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(24), default="received")
    error_kind: Mapped[str] = mapped_column(String(32), default="")
    error_text: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)
    durations: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # folder, expire_days, password_enc, qr_style
    duplicate_of: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # file | folder (arxiv ochilib papka qilib saqlangan — bitta QR bilan ichidagi fayllar ko'rinadi)
    kind: Mapped[str] = mapped_column(String(8), default="file")
    items: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=True)  # papka: [{name, size}]
    # Versiyalar: fayl yangilansa (ustidan yozilsa) eski yozuv yangisiga ishora qiladi, havola/QR o'zgarmaydi
    version: Mapped[int] = mapped_column(Integer, default=1)
    replaced_by: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    tg_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tg_file_id: Mapped[str] = mapped_column(Text, default="")
    tg_status_msg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    temp_path: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)

    employee: Mapped[Employee | None] = relationship(lazy="selectin")
    storage: Mapped[Storage | None] = relationship(lazy="selectin")


class FileEvent(Base):
    __tablename__ = "file_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(24))
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    message: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    at: Mapped[datetime] = mapped_column(default=now)


class SystemLink(Base):
    """Tizimning o'z qisqa havolasi: /qrdrive/s/<token>."""
    __tablename__ = "system_links"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, default="")
    downloads: Mapped[int] = mapped_column(Integer, default=0)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(default=now, index=True)
    actor: Mapped[str] = mapped_column(String(120), default="")
    actor_kind: Mapped[str] = mapped_column(String(16), default="admin")  # admin | bot | api | system
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(300), default="")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(default=now, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    level: Mapped[str] = mapped_column(String(12), default="info")  # info | warning | error | success
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(300), default="")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)  # Telegram'ga yuborildimi
    # all — panel + Telegram; bot — faqat bot adminlariga (masalan har bir yangi fayl), panelda ko'rinmaydi
    audience: Mapped[str] = mapped_column(String(8), default="all")
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=True)  # masalan {"account_id": 5}


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(32))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[Any]] = mapped_column(JSON, default=list)
    rate_limit: Mapped[int] = mapped_column(Integer, default=60)  # so'rov/daqiqa
    allowed_ips: Mapped[list[Any]] = mapped_column(JSON, default=list)
    storage_id: Mapped[int | None] = mapped_column(ForeignKey("storages.id", ondelete="SET NULL"), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    webhook_url: Mapped[str] = mapped_column(Text, default="")
    webhook_secret_enc: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(default=now)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("api_key_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(200))
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=now)


class ApiRequest(Base):
    __tablename__ = "api_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(default=now, index=True)
    api_key_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(300))
    status_code: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    ip: Mapped[str] = mapped_column(String(64), default="")


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(32))
    file_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | ok | failed
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=now)


class Heartbeat(Base):
    """Har bir jarayon (api, worker, bot) o'z holatini shu yerga yozadi — «Tizim holati» sahifasi uchun."""
    __tablename__ = "heartbeats"
    service: Mapped[str] = mapped_column(String(32), primary_key=True)
    at: Mapped[datetime] = mapped_column(default=now)
    started_at: Mapped[datetime] = mapped_column(default=now)
    info: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


Index("ix_files_queue", FileRecord.status, FileRecord.next_attempt_at)


class UploadTicket(Base):
    """Bir martalik veb-yuklash havolasi: /qrdrive/u/<token>. Rasmiy Telegram Bot API botga 20 MB dan katta
    faylni bermaydi — bot shunday faylga havola beradi, foydalanuvchi brauzerda yuklaydi, QR Telegram'ga keladi."""
    __tablename__ = "upload_tickets"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("tg_accounts.id", ondelete="CASCADE"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(300), default="")  # botga yuborilgan fayl nomi (ko'rsatish uchun)
    size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    caption: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=now)
    expires_at: Mapped[datetime] = mapped_column()
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    file_id: Mapped[int | None] = mapped_column(nullable=True)
    reply_to: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # foydalanuvchi xabari (javob reply bo'ladi)
