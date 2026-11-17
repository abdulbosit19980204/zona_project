"""Xatolar: har biri oddiy tilda "nima bo'ldi" va "nima qilish kerak". Texnik matn foydalanuvchiga chiqmaydi."""
from __future__ import annotations

import httpx


class QRDriveError(Exception):
    kind = "unknown"
    retry = True  # qayta urinish foyda berishi mumkinmi

    def __init__(self, detail: str = ""):
        super().__init__(detail or self.kind)
        self.detail = detail


class StorageAuthError(QRDriveError):
    kind, retry = "storage_auth", False


class StorageUnavailable(QRDriveError):
    kind = "storage_down"


class StoragePermission(QRDriveError):
    kind, retry = "storage_permission", False


class StorageQuota(QRDriveError):
    kind, retry = "storage_full", False


class StorageNotFound(QRDriveError):
    kind, retry = "not_found", False


class NotSupported(QRDriveError):
    kind, retry = "not_supported", False


class NoStorage(QRDriveError):
    kind, retry = "no_storage", False


class FileTooBig(QRDriveError):
    kind, retry = "too_big", False


class FileTypeNotAllowed(QRDriveError):
    kind, retry = "type_not_allowed", False


class TelegramError(QRDriveError):
    kind = "telegram"


class StorageError(QRDriveError):
    kind = "storage_other"


MESSAGES: dict[str, dict[str, str]] = {
    "storage_auth": {
        "title": "Saqlash joyiga kirib bo'lmadi: login yoki parol noto'g'ri",
        "hint": "«Saqlash joylari» bo'limida ulanish ma'lumotlarini yangilang, keyin «Qayta urinish» bosing.",
    },
    "storage_down": {
        "title": "Saqlash joyi javob bermayapti",
        "hint": "NAS/server yoqilganini va internet borligini tekshiring. Tiklangach «Qayta urinish» bosing.",
    },
    "storage_permission": {
        "title": "Saqlash joyidagi papkaga yozish uchun ruxsat yo'q",
        "hint": "Saqlash joyidagi foydalanuvchiga asosiy papkaga yozish huquqini bering.",
    },
    "storage_full": {
        "title": "Saqlash joyida bo'sh joy qolmagan",
        "hint": "Keraksiz fayllarni o'chiring yoki boshqa saqlash joyini asosiy qiling.",
    },
    "not_found": {
        "title": "Fayl yoki papka saqlash joyida topilmadi",
        "hint": "Fayl qo'lda o'chirilgan yoki ko'chirilgan bo'lishi mumkin.",
    },
    "not_supported": {
        "title": "Bu amal ushbu saqlash joyida qo'llab-quvvatlanmaydi",
        "hint": "Saqlash joyi sozlamasida «Tizim havolasi» rejimini tanlang.",
    },
    "not_configured": {
        "title": "Saqlash joyiga kirish ma'lumotlari kiritilmagan",
        "hint": "«Saqlash joylari» → «Tahrirlash»: foydalanuvchi nomi va parolni kiriting, keyin «Ulanishni tekshirish».",
    },
    "no_storage": {
        "title": "Saqlash joyi sozlanmagan",
        "hint": "«Saqlash joylari» bo'limida saqlash joyi qo'shing va uni asosiy qiling.",
    },
    "too_big": {
        "title": "Fayl ruxsat etilganidan katta",
        "hint": "«Bot sozlamalari»da maksimal hajmni oshiring yoki faylni kichraytiring.",
    },
    "type_not_allowed": {
        "title": "Bu turdagi fayllarga ruxsat berilmagan",
        "hint": "«Bot sozlamalari»dagi ruxsat etilgan turlar ro'yxatini tekshiring.",
    },
    "telegram": {
        "title": "Telegram'dan faylni olib bo'lmadi",
        "hint": "Bot tokeni va lokal Bot API serverini tekshiring. 20 MB dan katta fayllar uchun lokal server kerak.",
    },
    "storage_other": {
        "title": "Saqlash joyi amalni bajarmadi",
        "hint": "Bir ozdan keyin «Qayta urinish» bosing. Takrorlansa, «Saqlash joylari»da «Tekshirish»ni bosing.",
    },
    "unknown": {
        "title": "Kutilmagan xato yuz berdi",
        "hint": "«Qayta urinish» bosing. Takrorlansa, «Jurnal» bo'limini tekshiring.",
    },
}


def classify(exc: BaseException) -> QRDriveError:
    """Har qanday istisnoni QRDriveError'ga aylantiradi."""
    if isinstance(exc, QRDriveError):
        return exc
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout,
                        httpx.PoolTimeout, httpx.RemoteProtocolError, ConnectionError, TimeoutError)):
        return StorageUnavailable(type(exc).__name__)
    if isinstance(exc, PermissionError):
        return StoragePermission(str(exc))
    if isinstance(exc, FileNotFoundError):
        return StorageNotFound(str(exc))
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return StorageQuota(str(exc))
    err = QRDriveError(f"{type(exc).__name__}: {exc}")
    return err


def human(kind: str) -> dict[str, str]:
    return {"kind": kind, **MESSAGES.get(kind, MESSAGES["unknown"])}
