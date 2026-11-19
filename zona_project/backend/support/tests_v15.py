"""Standart rasmli savol kutmasdan javob oladi; javob variantlari (mazmuni bir xil) va insoniy kirish so'zi."""
import random
from unittest import mock

from . import ai_review, engine
from .engine import Decision
from .models import AIJob, Entry, Message, Settings
from .runner import Handler
from .tests import group_msg
from .tests_v6 import FlowBase


FEATS = {"width": 576, "height": 1280, "dhash": "0f0f0f0f0f0f0f0f", "dhash_mid": "0f0f0f0f0f0f0f0f"}


@mock.patch("support.vision.features", return_value=FEATS)
class FastImageTests(FlowBase):
    def test_lone_unrecognized_photo_is_deferred_recognized_is_not(self, _feats):
        h = Handler(self.bot, self.tg)
        calls = []
        h.defer = lambda: calls.append(1)
        with mock.patch("support.runner.ocr.read_text", return_value=""), \
                mock.patch("support.runner.vision.match", return_value=(None, 64, None)):
            h.handle(group_msg(1, 10, "", photo=True))
        self.assertEqual(calls, [1])  # tanilmadi — izohni kutamiz
        self.assertEqual(Message.objects.get(message_id=1).status, Message.NEW)
        e = Entry.objects.filter(status=Entry.APPROVED).first()
        h2 = Handler(self.bot, self.tg)
        h2.defer = lambda: calls.append(2)
        with mock.patch("support.runner.ocr.read_text", return_value=""), \
                mock.patch("support.runner.vision.match", return_value=(e, 1, None)):
            h2.handle(group_msg(2, 11, "", photo=True))
        self.assertEqual(calls, [1])  # tanilgan ekran — kutmasdan javob
        self.assertEqual(Message.objects.get(message_id=2).status, Message.ANSWERED)


class VarietyTests(FlowBase):
    def setUp(self):
        super().setUp()
        Settings.load()
        self.e = Entry.objects.create(kind=Entry.FAQ, title="T", status=Entry.APPROVED,
                                      answer="Moderatsiya 9:00–18:00 da 5–10 daqiqa. Natija **Profil → Bildirishnomalar**da.")

    def test_valid_variant_keeps_facts(self):
        ok = "Odatda 5–10 daqiqada, ish vaqtida 9:00–18:00 tekshiriladi. Natijani **Profil → Bildirishnomalar**da ko'rasiz."
        self.assertTrue(ai_review.valid_variant(self.e.answer, ok))
        self.assertFalse(ai_review.valid_variant(self.e.answer, "Tez orada tekshiriladi, kuting."))  # raqamlar yo'qoldi
        self.assertFalse(ai_review.valid_variant("Kod: {kod}", "Kod: tayyor bo'ladi juda tez orada"))  # maydon yo'qoldi

    def test_vary_picks_variant_and_opener(self):
        self.e.variants = [{"uz": "Variant A 9:00–18:00 5–10 **Profil → Bildirishnomalar**", "ru": ""}]
        d = Decision("faq", self.e, 90, self.e.answer, False)
        s = Settings.load()
        outs = {engine.vary(d, "uz", s, random.Random(i)) for i in range(40)}
        self.assertTrue(any("Variant A" in o for o in outs))
        self.assertTrue(any(o == self.e.answer for o in outs))
        self.assertTrue(any(o.startswith(("Tushunarli", "Mana", "Bu tez")) for o in outs))
        s.answer_variety = False
        self.assertEqual(engine.vary(d, "uz", s), self.e.answer)
        ai = Decision("ai", self.e, 90, "AI matni", False)
        self.assertEqual(engine.vary(ai, "uz", Settings.load()), "AI matni")  # AI javobi o'zi har xil

    def test_variants_cleared_when_answer_changes(self):
        Entry.objects.filter(pk=self.e.pk).update(variants=[{"uz": "x", "ru": ""}])
        e = Entry.objects.get(pk=self.e.pk)
        e.title = "Yangi sarlavha"
        e.save()
        self.assertIsNotNone(Entry.objects.get(pk=e.pk).variants)  # javob o'zgarmadi
        e.answer = "Boshqa javob"
        e.save(update_fields=["answer"])
        self.assertIsNone(Entry.objects.get(pk=e.pk).variants)

    def test_variants_job(self):
        good = "Odatda 5–10 daqiqada, ish vaqtida 9:00–18:00 tekshiriladi. Natijani **Profil → Bildirishnomalar**da ko'rasiz."

        def fake(label, system, message, schema):
            return {"items": [{"entry_id": self.e.id, "variants": [{"uz": good, "ru": ""}, {"uz": "yomon", "ru": ""}]}]}
        with mock.patch.object(ai_review, "_run", side_effect=fake):
            job = AIJob.objects.create(kind=AIJob.VARIANTS, params={"ids": [self.e.id]})
            ai_review.run_job(job.id)
        self.e.refresh_from_db()
        self.assertEqual([v["uz"] for v in self.e.variants], [good])
