"""Arxivni xavfsiz ochish (zip, tar, tar.gz/bz2/xz): yo'l hujumlari (../, absolyut yo'l, symlink),
zip-bomba (fayllar soni va umumiy hajm chegarasi) dan himoya; Windows zip'laridagi kirill nomlar (cp866) tiklanadi."""
from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import FileTooBig, QRDriveError
from .naming import safe_name

ARCHIVE_EXT = (".zip", ".rar", ".7z", ".tar", ".tgz", ".tar.gz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar.zst",
               ".cab", ".iso", ".arj", ".lzh", ".lha", ".xar")
IS_WIN = os.name == "nt"
TAR_EXT = (".tar", ".tgz", ".tar.gz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")


def _tool() -> list[str] | None:
    """RAR/7z/CAB/ISO uchun tashqi ochuvchi. Windows'da 7-Zip birinchi (Unicode nomlarni to'g'ri ochadi),
    Linux'da bsdtar (libarchive-tools, UTF-8 lokal bilan) yoki 7-Zip."""
    seven = [shutil.which(n) for n in ("7zz", "7z", "7za")]
    if IS_WIN:
        seven.append(next((str(p) for p in (Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "7-Zip" / "7z.exe",) if p.is_file()), None))
    seven_exe = next((x for x in seven if x), None)
    bsdtar = shutil.which("bsdtar")
    if IS_WIN and seven_exe:
        return [seven_exe, "x", "-y", "-p-", "-bd"]
    if bsdtar:
        return [bsdtar, "-x", "--no-same-owner", "-f"]
    if seven_exe:
        return [seven_exe, "x", "-y", "-p-", "-bd"]
    return None


def _dir_size(path: Path) -> tuple[int, int]:
    size = count = 0
    for p in path.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                size += p.stat().st_size
                count += 1
        except OSError:
            pass
    return size, count


def _extract_external(archive: Path, dest: Path, max_files: int, max_bytes: int) -> None:
    """Tashqi ochuvchi bilan ochish; jarayon davomida hajm va fayllar soni kuzatiladi (zip-bomba — darhol to'xtatiladi)."""
    tool = _tool()
    if tool is None:
        raise ArchiveError("bu arxiv turini ochish uchun serverda bsdtar (libarchive-tools) yoki 7-Zip kerak")
    cmd = [*tool, str(archive)] + (["-C", str(dest)] if tool[1] == "-x" else [f"-o{dest}"])
    env = {**os.environ, "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"}  # bsdtar: kirill nomlar
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
    deadline = time.monotonic() + 600
    while proc.poll() is None:
        size, count = _dir_size(dest)
        if size > max_bytes or count > max_files or time.monotonic() > deadline:
            proc.kill()
            proc.wait()
            if count > max_files:
                raise ArchiveError(f"arxivda fayllar juda ko'p (>{max_files})")
            raise FileTooBig(f"arxiv ochilganda {size} bayt (> {max_bytes})")
        time.sleep(0.2)
    size, count = _dir_size(dest)  # tugagandan keyin ham tekshiriladi (kichik, lekin chegaradan katta arxiv)
    if count > max_files:
        raise ArchiveError(f"arxivda fayllar juda ko'p (>{max_files})")
    if size > max_bytes:
        raise FileTooBig(f"arxiv ochilganda {size} bayt (> {max_bytes})")
    if proc.returncode != 0 and count == 0:  # ba'zi ortiqcha yozuvlar xato beradi — fayllar ochilgan bo'lsa qabul
        err = (proc.stderr.read() if proc.stderr else b"").decode("utf-8", "replace")[:200]
        raise ArchiveError(f"arxivni ochib bo'lmadi (parolli yoki buzilgan): {err}")
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
    is_tar = not is_zip and _is_tar(archive)
    if not is_zip and not is_tar:
        return _external(archive, dest, max_files=max_files, max_bytes=max_bytes, allowed=allowed)

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
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError, RuntimeError, NotImplementedError) as e:  # parolli zip — RuntimeError
        if isinstance(e, QRDriveError):
            raise
        raise ArchiveError(f"arxivni ochib bo'lmadi: {type(e).__name__}") from e
    if not files:
        raise ArchiveError("arxiv bo'sh yoki ichidagi fayllarga ruxsat yo'q")
    files.sort()
    return Extracted(root=dest, files=files, skipped=skipped)


def _is_tar(path: Path) -> bool:
    try:
        return tarfile.is_tarfile(path)
    except OSError:
        return False


def _external(archive: Path, dest: Path, *, max_files: int, max_bytes: int, allowed=None) -> Extracted:
    """RAR, 7z, CAB, ISO: vaqtinchalik papkaga ochiladi, keyin xavfsizlik qoidalari bilan saralanadi."""
    raw = dest.parent / (dest.name + "_raw")
    raw.mkdir(parents=True, exist_ok=True)
    try:
        _extract_external(archive, raw, max_files, max_bytes)
        files: list[tuple[str, int]] = []
        skipped = 0
        for p in sorted(raw.rglob("*")):
            if p.is_symlink():
                skipped += 1
                continue
            if not p.is_file():
                continue
            rel = _safe_rel(p.relative_to(raw).as_posix())
            if rel is None or (allowed and not allowed(rel.rsplit("/", 1)[-1])):
                skipped += 1
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), target)
            files.append((rel, target.stat().st_size))
    finally:
        shutil.rmtree(raw, ignore_errors=True)
    if not files:
        raise ArchiveError("arxiv bo'sh yoki ichidagi fayllarga ruxsat yo'q")
    return Extracted(root=dest, files=sorted(files), skipped=skipped)


def stem(name: str) -> str:
    low = name.lower()
    for ext in sorted(ARCHIVE_EXT, key=len, reverse=True):
        if low.endswith(ext):
            return name[: -len(ext)] or name
    return name
