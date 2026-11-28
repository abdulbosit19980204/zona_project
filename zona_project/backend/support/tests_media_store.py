"""Rasmlar: bir xil rasm qayta hisoblanmaydi (iz, OCR), to'yingan ekran turiga tushgan yangi rasm diskka yozilmaydi,
panel ro'yxati uchun eskiz (?thumb=1) va kesh sarlavhasi."""
import io
import os
import tempfile
from unittest import mock

from . import screens, slim, vision
from .models import Media, Message, ScreenType
from .tests_controls import ControlsBase


def png(color=(200, 30, 30), size=(900, 1600), vertical=False):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", size, color)
    d = ImageDraw.Draw(img)
    for i in range(0, size[0] if vertical else size[1], 120):
        d.rectangle([i, 0, i + 60, size[1]] if vertical else [40, i, size[0] - 40, i + 60], fill=(255, 255, 255))
    if vertical:
        d.ellipse([200, 300, 700, 800], fill=(0, 0, 0))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


class StoreTests(ControlsBase):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = mock.patch.dict(os.environ, {"ZONA_SUPPORT_MEDIA": tmp.name})
        p.start()
        self.addCleanup(p.stop)
        self.n = 0

    def q(self):
        self.n += 1
        return Message.objects.create(bot=self.bot, chat_id=-1, message_id=self.n, kind=Message.QUESTION, text="rasm")

    def test_same_image_reuses_hash_ocr_and_alert(self):
        data = png()
        q1 = self.q()
        q1.alert_text = "Ошибка"
        q1.save()
        a = vision.store(data, kind=Media.PHOTO, source="question", message=q1)
        Media.objects.filter(pk=a.pk).update(ocr_text="Новая торговая точка")
        with mock.patch.object(vision, "features", side_effect=AssertionError("qayta hisoblandi")):
            b = vision.store(data, kind=Media.PHOTO, source="question", message=self.q())
        self.assertEqual(b.prev_alert, "Ошибка")
        b.refresh_from_db()
        self.assertEqual((b.dhash, b.ocr_text), (a.dhash, "Новая торговая точка"))

    def test_saturated_screen_type_is_not_written(self):
        base = vision.store(png(), kind=Media.PHOTO, source="question", message=self.q())
        t = ScreenType.objects.create(title="Moderatsiya", hashes=[[base.dhash, base.dhash_mid]])
        screens._CACHE["key"] = None
        Media.objects.filter(pk=base.pk).update(screen=t)
        for i in range(slim.KEEP_PER_TYPE):
            Media.objects.create(kind=Media.PHOTO, path=f"/x/{i}.jpg", sha256=f"s{i}", screen=t, dhash=base.dhash)
        m = vision.store(png(color=(201, 30, 30)), kind=Media.PHOTO, source="question", message=self.q())
        m.refresh_from_db()
        self.assertEqual((m.path, m.slim, m.screen_id), ("", True, t.pk))
        self.assertGreater(m.full_size, 0)
        from . import tasks
        self.assertEqual(tasks._task_media(m.message), [])            # na fayl, na file_id — biriktirilmaydi
        Media.objects.filter(pk=m.pk).update(tg_file_ids={"1": "fid"})
        self.assertEqual(tasks._task_media(m.message), [m.pk])        # Telegram'dan olinadi
        h = vision.store(png(color=(202, 30, 30)), kind=Media.PHOTO, source="history", message=self.q())
        self.assertTrue(h.path)                                       # tarix (Telegram file_id yo'q) — yoziladi
        other = vision.store(png(color=(10, 200, 10), vertical=True), kind=Media.PHOTO, source="question",
                             message=self.q())
        self.assertTrue(other.path)                                   # yangi / noyob ekran — saqlanadi

    def test_thumb_endpoint(self):
        m = vision.store(png(), kind=Media.PHOTO, source="question", message=self.q())
        self.login("viewer")
        r = self.call("get", f"support/media/{m.pk}/file/?thumb=1")
        self.assertEqual(r.status_code, 200)
        self.assertLess(len(r.content), m.size)
        self.assertIn("max-age", r["Cache-Control"])
        r2 = self.call("get", f"support/media/{m.pk}/file/")
        self.assertIn("max-age", r2["Cache-Control"])
        r2.close()  # fayl dastagi (Windows'da vaqtinchalik papka o'chirilsin)

    def test_slim_photo_still_gets_ocr(self):
        # 28.11 regressiya: diskka yozilmagan (slim) rasmda OCR bo'sh qolardi — bot skrinshot matnini ko'rmasdi
        from .runner import Handler
        from .telegram import Client
        data = png()
        q = self.q()
        q.photo_file_id = "fid"
        h = Handler(self.bot, mock.Mock(spec=Client))
        h.tg.download.return_value = data
        slim_media = Media(kind=Media.PHOTO, path="")
        slim_media.save()
        with mock.patch.object(vision, "store", return_value=slim_media):
            m = h._fetch_media(q)
        self.assertEqual(m.raw_bytes, data)
        with mock.patch("support.runner.ocr.read_text", return_value="Торговая точка создана в 1С UZ-00069329") as rt:
            h._ocr(q, m)
        rt.assert_called_once_with(data)
        self.assertIn("UZ-00069329", q.ocr_text)

    def test_slim_photo_after_defer_gets_ocr(self):
        # izohsiz skrinshot: 3 s izoh kutiladi, qayta ishlashda Media bazadan olinadi (baytsiz) — OCR baribir o'qilsin
        from .runner import Handler
        from .telegram import Client
        data = png()
        q = self.q()
        q.photo_file_id = "fid"
        Media.objects.create(kind=Media.PHOTO, path="", message=q)
        h = Handler(self.bot, mock.Mock(spec=Client))
        h.tg.download.return_value = data
        m = h._fetch_media(q)
        h.tg.download.assert_called_once()
        with mock.patch("support.runner.ocr.read_text", return_value="Торговая точка создана в 1С UZ-00069329") as rt:
            h._ocr(q, m)
        rt.assert_called_once_with(data)
        self.assertIn("UZ-00069329", q.ocr_text)
