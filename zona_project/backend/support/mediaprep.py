"""Javob fayllarini tez yuborishga tayyorlash.

1) Videoni siqish (ffmpeg bo'lsa): 720p, H.264, "faststart" — agentlar mobil internetda tez ochadi, Telegram'ga yuklash
   tezlashadi. Siqilgani kichikroq bo'lmasa — asl fayl qoladi.
2) Oldindan yuklash (warm): biriktirilgan fayl Telegram'ga bir marta (admin chatiga, jim) yuklanib, file_id saqlanadi va
   xabar darhol o'chiriladi. Keyin javobda fayl qayta yuklanmaydi — bir zumda yuboriladi (hatto birinchi agentga ham).
"""
import logging
import os
import shutil
import subprocess
import tempfile

log = logging.getLogger("support")
VIDEO_MIN_BYTES = 1_500_000


def ffmpeg():
    return shutil.which("ffmpeg")


def compress_video(data, name=""):
    """Video baytlari -> siqilgan baytlar (yoki asl, agar ffmpeg yo'q / foydasi bo'lmasa)."""
    exe = ffmpeg()
    if not exe or len(data) < VIDEO_MIN_BYTES:
        return data
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "in" + (os.path.splitext(name)[1] or ".mp4")), os.path.join(d, "out.mp4")
        with open(src, "wb") as f:
            f.write(data)
        cmd = [exe, "-y", "-loglevel", "error", "-i", src, "-vf", "scale='min(720,iw)':-2", "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", dst]
        try:
            subprocess.run(cmd, check=True, timeout=180)
            out = open(dst, "rb").read()
        except Exception as e:  # noqa: BLE001
            log.warning("video compress failed: %s", e)
            return data
    return out if 0 < len(out) < len(data) * 0.9 else data


def warm(bot, tg, limit=10):
    """Bilim bazasidagi tasdiqlangan javoblar fayllarini oldindan Telegram'ga yuklash (file_id keshi)."""
    from .models import Entry, Media
    if not bot.admin_chat_id:
        return 0
    ids = {i for a in Entry.objects.filter(status=Entry.APPROVED).exclude(attachments=[]).values_list("attachments", flat=True) for i in a}
    key, done = str(bot.id), 0
    for m in Media.objects.filter(id__in=ids).exclude(path=""):
        if (m.tg_file_ids or {}).get(key) or done >= limit:
            continue
        try:
            data = open(m.path, "rb").read()
        except OSError:
            continue
        method, field = tg.SEND.get(m.kind, tg.SEND["document"])
        params = {"chat_id": bot.admin_chat_id, "disable_notification": True}
        if m.kind == "video":
            params["supports_streaming"] = True
        try:
            r = tg.call_multipart(method, params, {field: (m.name or f"file{m.id}", data)})
            fid = tg._file_id(r, m.kind)
            if fid:
                Media.objects.filter(pk=m.pk).update(tg_file_ids={**(m.tg_file_ids or {}), key: fid})
                done += 1
            if r.get("message_id"):
                tg.call("deleteMessage", {"chat_id": bot.admin_chat_id, "message_id": r["message_id"]})
        except Exception as e:  # noqa: BLE001
            log.warning("warm %s failed: %s", m.pk, e)
    return done
