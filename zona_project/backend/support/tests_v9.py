"""Albomdagi turli ekranlar, matn ustunligi (rasm bilan/rasmsiz bir xil javob) va AI'ga xodimlarning haqiqiy javoblari."""
from unittest import mock

from django.test import TestCase

from zona.ai import service as ai_service

from . import engine
from .models import Bot, Entry, Group, Media, Message, Settings, TgUser
from .runner import _album_order
from .tests_v6 import FlowBase


def mk(title, answer, questions=(), kind=Entry.FAQ):
    return Entry.objects.create(kind=kind, title=title, questions=list(questions), answer=answer, status=Entry.APPROVED)


class DecideTests(TestCase):
    def setUp(self):
        Settings.load()
        Settings.objects.update(ai_enabled=False, ai_primary=False, faq_threshold=60)
        self.employee = mk("PRBC: yangi klient qo'shish bo'limi ko'rinmaydi (rol Employee)", "Akkaunt tasdiqlanishi kerak.",
                           ["yangi klient bo'limi yo'q", "klient qo'shish chiqmayapti"])
        self.moder = mk("ProTarget: nuqta moderatsiyaga yuborildi", "Moderatsiya 9:00–18:00 da 5–10 daqiqa.",
                        ["moderatsiyaga yuborildi qachon tasdiqlanadi"])
        self.connect = mk("Klient bor, lekin agentda (podkluchenie) chiqmayapti",
                          "Supervayzer klientni agentga ulaydi va marshrutiga qo'shadi. Sinxronizatsiyadan so'ng chiqadi.",
                          ["klient bor deyapti lekin podklucheniyada chiqmayapti", "klient agentda ko'rinmayapti"])

    def test_substantive(self):
        self.assertFalse(engine.substantive("ko'rib bering"))
        self.assertFalse(engine.substantive("iltimos yordam bering"))
        self.assertTrue(engine.substantive("Abdullayevni bor deyabdi lekin podklucheniyadam chiqmayabdi korib bering"))

    def test_album_with_different_screens_answers_each(self):
        d = engine.decide("", text="", images=[(self.employee, 90, 1), (self.moder, 95, 0)])
        self.assertEqual(d.stage, "image")
        self.assertIn("1-rasm", d.text)
        self.assertIn("2-rasm", d.text)
        self.assertLess(d.text.index("Moderatsiya"), d.text.index("Akkaunt"))  # rasm tartibida

    def test_text_wins_over_unrelated_image(self):
        Settings.objects.update(faq_threshold=40)
        text = "Abdullayevni bor deyabdi lekin podklucheniyadam chiqmayabdi korib bering"
        with_photo = engine.decide(text + "\nOutlet already exists in 1C", text=text, ocr="Outlet already exists in 1C",
                                   images=[(self.moder, 92, 0)])
        text_only = engine.decide(text)
        self.assertEqual(with_photo.entry, self.connect)
        self.assertEqual((with_photo.stage, with_photo.entry), (text_only.stage, text_only.entry))  # bir xil javob

    def test_text_related_to_image_picks_that_screen(self):
        d = engine.decide("", text="moderatsiyaga yuborildi qachon tasdiqlanadi?", images=[(self.employee, 90, 0), (self.moder, 80, 1)])
        self.assertEqual((d.stage, d.entry), ("image", self.moder))

    def test_generic_text_lets_image_decide(self):
        d = engine.decide("ko'rib bering", text="ko'rib bering", images=[(self.employee, 90, 0)])
        self.assertEqual((d.stage, d.entry), ("image", self.employee))

    def test_fast_path_returns_none_before_ai(self):
        self.assertIsNone(engine.decide("tamomila boshqa narsa haqida savol bor", fast=True))


class StaffExamplesTests(TestCase):
    def test_ai_gets_real_staff_answers_and_ocr(self):
        bot = Bot.objects.create(name="b", token_enc="x")
        u = TgUser.objects.create(tg_id=1, name="Agent")
        q = Message.objects.create(bot=bot, chat_id=-1, message_id=1, user=u, text="klient bor lekin agentda chiqmayapti")
        Message.objects.create(bot=bot, chat_id=-1, message_id=2, kind=Message.STAFF, question=q,
                               text="Supervayzeringiz klientni sizga ulashi kerak, keyin sinxronizatsiya qiling.")
        self.assertEqual(len(engine.staff_examples("klient bor ammo agentda chiqmayapti")), 1)
        s = Settings.load()
        Settings.objects.update(ai_enabled=True, ai_daily_limit=100)
        s.refresh_from_db()
        captured = {}

        def fake_run(task, user, label, system, message, schema):
            captured.update(system=system, message=message)
            return {"answer": "ok", "confidence": 0.9, "needs_human": False, "reason": ""}, {}
        with mock.patch.object(ai_service, "run", side_effect=fake_run):
            engine.ai_answer("klient bor ammo agentda chiqmayapti", "uz", [], None, s, ocr="Outlet already exists")
        self.assertIn("XODIM JAVOBI: Supervayzeringiz", captured["system"])
        self.assertIn("RASMDAGI MATN", captured["message"])


class AlbumOrderTests(FlowBase):
    def test_main_photo_fetched_even_if_album_parts_saved_first(self):
        from . import vision
        g = Group.objects.create(bot=self.bot, chat_id=-100, title="G")
        q = Message.objects.create(bot=self.bot, group=g, chat_id=-100, message_id=10, photo_file_id="big", media_group_id="a1")
        part = vision.store(b"part", kind="photo", name="album:11", message=q)  # bo'lak asosiy rasmdan oldin saqlandi
        main = self.h()._fetch_media(q)
        self.assertNotEqual(main.pk, part.pk)
        self.assertEqual([m.pk for m in sorted(Media.objects.filter(message=q), key=_album_order)], [main.pk, part.pk])
