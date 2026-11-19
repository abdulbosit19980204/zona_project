"""Javob videolari: oldindan yuklash (file_id), oqimli ijro, siqish ffmpeg bo'lmasa xavfsiz."""
import os
import tempfile
from unittest import mock

from zona.crypto import encrypt
from zona.tests import Base

from . import mediaprep
from . import telegram as T
from .models import Bot, Entry, Media


class FakeTG:
    SEND = T.Client.SEND

    def __init__(self):
        self.calls = []

    def call_multipart(self, method, fields, files, timeout=120):
        self.calls.append((method, fields))
        return {"message_id": 77, "video": {"file_id": "VID123"}}

    def call(self, method, params=None, **k):
        self.calls.append((method, params))
        return True

    _file_id = staticmethod(T.Client._file_id)


class VideoTests(Base):
    def test_warm_uploads_once_and_cleans_admin_chat(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as f:
            f.write(b"video-bytes")
        self.addCleanup(os.unlink, f.name)
        m = Media.objects.create(kind="video", path=f.name, name="howto.mp4", source="answer")
        Entry.objects.create(kind=Entry.FAQ, title="T", answer="a", status=Entry.APPROVED, attachments=[m.id])
        bot = Bot.objects.create(name="b", token_enc=encrypt("1:x"), admin_chat_id=-500)
        tg = FakeTG()
        self.assertEqual(mediaprep.warm(bot, tg), 1)
        m.refresh_from_db()
        self.assertEqual(m.tg_file_ids[str(bot.id)], "VID123")
        self.assertEqual(tg.calls[0][1]["supports_streaming"], True)
        self.assertEqual(tg.calls[1][0], "deleteMessage")  # admin chatida iz qolmaydi
        self.assertEqual(mediaprep.warm(bot, tg), 0)  # ikkinchi marta yuklanmaydi

    def test_send_media_streams_video(self):
        c = T.Client("1:x")
        with mock.patch.object(c, "call", return_value={"video": {"file_id": "X"}}) as call, mock.patch.object(c, "_throttle"):
            c.send_media(1, [{"kind": "video", "file_id": "X"}])
        self.assertTrue(call.call_args[0][1]["supports_streaming"])

    def test_compress_without_ffmpeg_keeps_original(self):
        with mock.patch.object(mediaprep, "ffmpeg", return_value=None):
            data = b"x" * 2_000_000
            self.assertIs(mediaprep.compress_video(data, "a.mp4"), data)
