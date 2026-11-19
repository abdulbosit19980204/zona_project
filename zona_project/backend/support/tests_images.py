"""Rasmlarni saqlash, tanish (vizual iz), javob biriktirmalari va Pro-target to'plami testlari."""
import io
import os
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from PIL import Image, ImageDraw

from zona.crypto import encrypt
from zona.models import Member, TeamContact
from zona.tests import Base

from . import engine, vision
from .models import MODE_LIVE, Bot, Entry, Media, Message
from .runner import Handler
from .tests import FakeClient, group_msg


def screen(kind="moderation", name="BRAND-BRO-TRADE", size=(540, 1170)):
    """Sintetik "skrinshot": ekran turi joylashuvni belgilaydi, nom — foydalanuvchi ma'lumoti."""
    im = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(im)
    w, h = size
    if kind == "moderation":
        d.ellipse((w * 0.3, h * 0.3, w * 0.7, h * 0.5), fill=(250, 150, 20))
        d.rounded_rectangle((20, h * 0.85, w - 20, h * 0.92), radius=20, outline=(0, 170, 200), width=4)
    else:
        d.rectangle((0, 0, w, h * 0.1), fill=(20, 30, 50))
        for i in range(4):
            d.rectangle((20, h * (0.15 + i * 0.18), w - 20, h * (0.30 + i * 0.18)), fill=(30, 45, 70))
    d.text((40, h * 0.55), name, fill=(0, 0, 0))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


class Media0(Base):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        p = mock.patch.dict(os.environ, {"ZONA_SUPPORT_MEDIA": media.name})
        p.start()
        self.addCleanup(p.stop)
        self.entry = Entry.objects.create(kind=Entry.FAQ, title="ProTarget moderatsiya", answer="Moderatsiyada, kuting.",
                                          status=Entry.APPROVED)
        self.bot = Bot.objects.create(name="S", token_enc=encrypt("1:x"), mode=MODE_LIVE, admin_chat_id=555)


class VisionTests(Media0):
    def test_same_screen_other_user_matches_other_screen_does_not(self):
        a = vision.store(screen(name="BRAND-BRO-TRADE"), source="seed")
        vision.label([a], self.entry, "test")
        same = vision.features(screen(name="Boshqa Do'kon MCHJ 12345", size=(720, 1560)))
        other = vision.features(screen(kind="prbc"))
        e, dist, _ = vision.match(same, 10)
        self.assertEqual(e, self.entry)
        self.assertLessEqual(dist, 10)
        self.assertEqual(vision.match(other, 10)[0], None)

    def test_store_dedupes_files_and_cleanup_keeps_labeled(self):
        a = vision.store(screen(), source="question")
        b = vision.store(screen(), source="question")
        self.assertEqual(a.path, b.path)
        vision.label([a], self.entry, "x")
        Media.objects.update(created_at=a.created_at.replace(year=2020))
        vision.cleanup(30)
        a.refresh_from_db()
        self.assertTrue(a.path and os.path.exists(a.path))
        self.assertEqual(vision.cleanup(0), 0)


class FakeClientMedia(FakeClient):
    def __init__(self, photo):
        super().__init__()
        self.photo, self.media_sent = photo, []

    def download(self, file_id, max_bytes=0):
        return self.photo

    def send_media(self, chat_id, items, reply_to=None):
        self.media_sent.append({"chat": chat_id, "items": items, "reply_to": reply_to})
        return [f"fid{i}" for i in range(len(items))]


class ImageAnswerTests(Media0):
    def test_known_screen_is_answered_before_ocr_and_attachments_are_sent(self):
        ex = vision.store(screen(), source="seed")
        vision.label([ex], self.entry, "test")
        att = vision.store(b"\x00video", kind=Media.VIDEO, name="yo'riqnoma.mp4", source="answer")
        self.entry.attachments = [att.id]
        self.entry.save()
        tg = FakeClientMedia(screen(name="Yangi Do'kon"))
        seen = {}

        def fake_ocr(data):
            seen["sent_before_ocr"] = len(tg.sent)
            return "Новая торговая точка"

        with mock.patch("support.runner.ocr.read_text", side_effect=fake_ocr):
            Handler(self.bot, tg).handle(group_msg(1, 10, "", photo=True))
        q = Message.objects.get(message_id=1)
        self.assertEqual((q.stage, q.status), ("image", Message.ANSWERED))
        self.assertEqual(seen["sent_before_ocr"], 1)          # javob OCR'dan oldin ketdi
        self.assertEqual(q.ocr_text, "Новая торговая точка")  # OCR keyin saqlandi
        self.assertEqual(tg.media_sent[0]["items"][0]["kind"], "video")
        att.refresh_from_db()
        self.assertEqual(att.tg_file_ids, {str(self.bot.id): "fid0"})  # keyingi safar qayta yuklanmaydi
        self.assertTrue(Media.objects.filter(message=q, kind=Media.PHOTO).exists())  # savol rasmi serverda

    def test_staff_answer_teaches_the_screen(self):
        team = Member.objects.create(name="Pro-target", role="PT", is_team=True, level="EXT")
        TeamContact.objects.create(member=team, name="Guzel", telegram="guzel_t")
        tg = FakeClientMedia(screen(kind="prbc", name="Oleg"))
        h = Handler(self.bot, tg)
        with mock.patch("support.runner.ocr.read_text", return_value=""):
            h.handle(group_msg(1, 10, "bu nima", photo=True))
            h.handle(group_msg(2, 77, "Sizda agent roli yo'q, supervayzer rol beradi", "guzel_t", reply_to=1))
        m = Media.objects.get(message__message_id=1)
        self.assertTrue(m.label_id and m.label_auto)
        Entry.objects.filter(pk=m.label_id).update(status=Entry.APPROVED)
        tg2 = FakeClientMedia(screen(kind="prbc", name="Boshqa agent"))
        with mock.patch("support.runner.ocr.read_text", return_value=""):
            Handler(self.bot, tg2).handle(group_msg(3, 11, "", photo=True))
        self.assertEqual(Message.objects.get(message_id=3).stage, "image")


class MediaApiTests(Media0):
    def test_upload_label_types_and_file(self):
        self.login("editor")
        f = SimpleUploadedFile("s.png", screen(), content_type="image/png")
        r = self.client.post("/api/support/media/upload/", {"files": [f], "label": self.entry.id},
                             headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(r.status_code, 200, r.content)
        mid = r.json()[0]["id"]
        self.assertEqual(r.json()[0]["label"], self.entry.id)
        q = vision.store(screen(name="X"), source="question")
        vision.store(screen(name="Y"), source="question")
        types = self.call("get", "support/images/").json()
        self.assertEqual(types["labeled"][0]["entry"], self.entry.id)
        self.assertEqual(types["unlabeled"][0]["guess"], self.entry.id)
        r = self.call("post", "support/images/label/", {"ids": [q.id], "entry": self.entry.id})
        self.assertEqual(r.json()["done"], 1)
        r = self.client.get(f"/api/support/media/{mid}/file/", headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(b"".join(r.streaming_content).startswith(b"\x89PNG"))
        r = self.call("patch", f"support/entries/{self.entry.id}/", {"attachments": [mid]})
        self.assertEqual(r.json()["attachments_info"][0]["id"], mid)
        self.login("viewer")
        f = SimpleUploadedFile("s.png", screen(), content_type="image/png")
        r = self.client.post("/api/support/media/upload/", {"files": [f]}, headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(r.status_code, 403)

    def test_label_images_command(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
            fh.write(screen())
        self.addCleanup(os.remove, fh.name)
        with mock.patch("support.ocr.read_text", return_value=""):
            call_command("support_label_images", fh.name, title=self.entry.title, verbosity=0)
            call_command("support_label_images", fh.name, title=self.entry.title, verbosity=0)
        self.assertEqual(Media.objects.filter(label=self.entry).count(), 1)


class ProtargetPackTests(Base):
    def test_pack_updates_seed_template_and_answers_visit_questions(self):
        call_command("support_setup", verbosity=0)
        call_command("support_import_kb", pack="protarget", verbosity=0)
        mod = Entry.objects.get(title="ProTarget: yangi nuqta moderatsiyaga yuborilgan")
        self.assertEqual(mod.status, Entry.APPROVED)
        self.assertIn("9:00–18:00", mod.answer)
        self.assertEqual(mod.versions.count(), 1)  # eski matn versiyada
        for q, start in [("не могу начать визит", "ProTarget: vizitni"), ("смена геотега точки", "ProTarget: savdo nuqtasi geoloka"),
                         ("vizit boshlanmayapti", "ProTarget: vizitni"), ("уведомление не пришло", "ProTarget: moderatsiya natijasi"), ("tasdiqlandimi qanday bilaman", "ProTarget: moderatsiya natijasi")]:
            d = engine.decide(q, engine.detect_lang(q))
            self.assertTrue(d.entry and d.entry.title.startswith(start), (q, d.stage, d.entry))
        self.assertIn("кружочек", engine.decide("не могу начать визит", "ru").text)
        call_command("support_import_kb", pack="protarget", verbosity=0)  # qayta — takror yo'q
        self.assertEqual(Entry.objects.filter(title__startswith="ProTarget: vizitni").count(), 1)
