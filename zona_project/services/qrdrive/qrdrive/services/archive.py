"""Arxivni xavfsiz ochish (zip, tar, tar.gz/bz2/xz): yo'l hujumlari (../, absolyut yo'l, symlink),
zip-bomba (fayllar soni va umumiy hajm chegarasi) dan himoya; Windows zip'laridagi kirill nomlar (cp866) tiklanadi."""
from __future__ import annotations

import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import FileTooBig, QRDriveError
from .naming import safe_name

ARCHIVE_EXT = (".zip", ".tar", ".tgz", ".tar.gz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")
SKIP_NAMES = {"__MACOSX", ".DS_Store", "Thumbs.db", "desktop.ini"}


class ArchiveError(QRDriveError):
    kind, retry = "archive_bad", False


def is_archive(name: str) -> bool:
    return name.lower().endswith(ARCHIVE_EXT)


@dataclass
class Extracted:
    root: Path
    files: list[tuple[str, int]]  # (nisbiy yo'l "a/b.pdf", hajm)
    skipped: int = 0


def _zip_name(info: zipfile.ZipInfo) -> str:
    name = info.filename
    if not info.flag_bits & 0x800:  # UTF-8 bayrog'i yo'q — Windows arxivlovchilari odatda cp866 (kirill)
        try:
            name = name.encode("cp437").decode("cp866")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name


def _safe_rel(name: str) -> str | None:
    """Arxivdagi yo'lni xavfsiz nisbiy yo'lga aylantiradi; xavfli yoki keraksiz bo'lsa None."""
    parts = []
    for part in name.replace("\\", "/").split("/"):
        if part in ("", ".") or part in SKIP_NAMES:
            if part in SKIP_NAMES:
                return None
            continue
        if part == "..":
            return None
        parts.append(safe_name(part, 120))
    return "/".join(parts) or None


def extract(archive: Path, dest: Path, *, max_files: int, max_bytes: int, allowed=None) -> Extracted:
    """Arxivni dest ga ochadi. allowed(name)->bool — ruxsat etilmagan turlar o'tkazib yuboriladi."""
    dest.mkdir(parents=True, exist_ok=True)
    files: list[tuple[str, int]] = []
    skipped, total = 0, 0
    is_zip = zipfile.is_zipfile(archive)  # format — tarkibdan (worker'da fayl kengaytmasiz vaqtinchalik nomda)

    def check(rel: str | None, size: int) -> bool:
        nonlocal skipped, total
        if rel is None or (allowed and not allowed(rel.rsplit("/", 1)[-1])):
            skipped += 1
            return False
        total += size
        if len(files) + 1 > max_files:
            raise ArchiveError(f"arxivda fayllar juda ko'p (>{max_files})")
        if total > max_bytes:
            raise FileTooBig(f"arxiv ochilganda {total} bayt (> {max_bytes})")
        return True

    try:
        if is_zip:
            with zipfile.ZipFile(archive) as zf:
                for info in zf.infolist():
                    if info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000:  # papka yoki symlink
                        continue
                    rel = _safe_rel(_zip_name(info))
                    if not check(rel, info.file_size):
                        continue
                    target = dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    written = 0
                    with zf.open(info) as src, open(target, "wb") as out:  # haqiqiy hajm ham sanaladi (soxta header)
                        while chunk := src.read(1024 * 1024):
                            written += len(chunk)
                            if written > info.file_size + 1024 or total - info.file_size + written > max_bytes:
                                raise FileTooBig("arxivdagi fayl e'lon qilinganidan katta")
                            out.write(chunk)
                    files.append((rel, written))
        else:
            with tarfile.open(archive) as tf:
                for m in tf:
                    if not m.isfile():  # papka, symlink, qurilma — o'tkaziladi
                        continue
                    rel = _safe_rel(m.name)
                    if not check(rel, m.size):
                        continue
                    target = dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    src = tf.extractfile(m)
                    if src is None:
                        continue
                    with src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out, 1024 * 1024)
                    files.append((rel, m.size))
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError) as e:
        if isinstance(e, QRDriveError):
            raise
        raise ArchiveError(f"arxivni ochib bo'lmadi: {type(e).__name__}") from e
    if not files:
        raise ArchiveError("arxiv bo'sh yoki ichidagi fayllarga ruxsat yo'q")
    files.sort()
    return Extracted(root=dest, files=files, skipped=skipped)


def stem(name: str) -> str:
    low = name.lower()
    for ext in sorted(ARCHIVE_EXT, key=len, reverse=True):
        if low.endswith(ext):
            return name[: -len(ext)] or name
    return name
