"""Deploydan keyingi sinov buyrug'i (support_smoke): 3 asosiy savol va AI'siz standartlar qamrovi."""
import io

from django.core.management import CommandError, call_command

from . import smoke
from .models import Entry, Message
from .tests_controls import ControlsBase


class SmokeTests(ControlsBase):
    def setUp(self):
        super().setUp()
        self.geo = Entry.objects.create(kind=Entry.FAQ, title="Nuqta joylashuvidan uzoqda deb tashrif qabul qilinmayapti",
                                        questions=["lokatsiya uzoq deyapti", "uzoqdasiz deyapti"], answer="Aniq joylashuv",
                                        status=Entry.APPROVED, uses=50)
        self.vis = Entry.objects.create(kind=Entry.FAQ, title="ProTarget: «User already has an active visit» — ochiq vizit",
                                        questions=["aktiv vizit bor", "ochiq vizit bor deyapti"], answer="Vizitni yoping",
                                        status=Entry.APPROVED, uses=40)

    def test_smoke_passes_and_fails(self):
        out = io.StringIO()
        call_command("support_smoke", stdout=out)
        self.assertEqual(out.getvalue().count("PASS"), 3, out.getvalue())
        Entry.objects.filter(pk=self.vis.pk).update(status=Entry.ARCHIVED)
        with self.assertRaises(CommandError):
            call_command("support_smoke", stdout=io.StringIO())

    def test_standards_use_real_phrases_of_absorbed_entries(self):
        q1 = Message.objects.create(bot=self.bot, chat_id=-1, message_id=1, kind=Message.QUESTION,
                                    text="Uzoqdasiz deyapti do'kon ichidaman")
        q2 = Message.objects.create(bot=self.bot, chat_id=-1, message_id=2, kind=Message.QUESTION,
                                    text="Assalomu alaykum")                       # mazmunsiz — olinmaydi
        q3 = Message.objects.create(bot=self.bot, chat_id=-1, message_id=3, kind=Message.QUESTION,
                                    text="Vizit boshlanmayapti radius xato chiqyapti")
        Entry.objects.create(kind=Entry.FAQ, title="x", answer="y", status=Entry.ARCHIVED, claude_target=self.geo,
                             sources=[q1.pk, q2.pk, q3.pk])
        rows = smoke.standards(2, 5)
        geo = next(r for r in rows if r["id"] == self.geo.pk)
        self.assertEqual([t for t, _ok, _g in geo["phrases"]], ["Uzoqdasiz deyapti do'kon ichidaman",
                                                                "Vizit boshlanmayapti radius xato chiqyapti"])
        self.assertEqual(geo["total"], 2)
        self.assertEqual(geo["hit"], sum(1 for _t, ok, _g in geo["phrases"] if ok))
        out = io.StringIO()
        call_command("support_smoke", "--standards", "2", stdout=out)
        self.assertIn("Standartlar (AI'siz)", out.getvalue())

    def test_no_ai_blocks_ai_calls(self):
        from unittest import mock

        from . import engine
        from .models import Settings
        Settings.load()
        Settings.objects.update(ai_enabled=True)
        with mock.patch("zona.ai.service.run", side_effect=AssertionError("AI chaqirildi")):
            with engine.no_ai():
                self.assertIsNone(engine.ai_answer("noma'lum savol bor", "uz", [], None, Settings.load()))
                d = engine.decide("butunlay noma'lum yangi muammo chiqdi", "uz", live=False)
        self.assertTrue(d is None or d.stage != "ai")
        self.assertFalse(getattr(engine._NO_AI, "on", False))
