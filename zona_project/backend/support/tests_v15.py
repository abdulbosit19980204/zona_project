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

    def test_variants_job_retries_one_by_one_when_truncated(self):
        e2 = Entry.objects.create(kind=Entry.FAQ, title="T2", status=Entry.APPROVED, answer="Parolni tiklash: Profil bo'limi, 3 qadam.")
        good = {self.e.id: "Odatda 5–10 daqiqada, ish vaqtida 9:00–18:00 tekshiriladi. Natijani **Profil → Bildirishnomalar**da ko'rasiz.",
                e2.id: "Parolni tiklash uchun Profil bo'limiga kiring — jami 3 qadam."}
        seen = []

        def fake(label, system, message, schema):
            ids = [i for i in good if f"[id={i}]" in message]
            seen.append(len(ids))
            if len(ids) > 1:
                raise RuntimeError("AIError: Javob max_tokens chegarasida uzilib qoldi")
            return {"items": [{"entry_id": ids[0], "variants": [{"uz": good[ids[0]], "ru": ""}]}]}
        with mock.patch.object(ai_review, "_run", side_effect=fake):
            job = AIJob.objects.create(kind=AIJob.VARIANTS, params={"ids": [self.e.id, e2.id]})
            ai_review.run_job(job.id)
        self.assertEqual(seen, [2, 1, 1])
        self.assertEqual(Entry.objects.filter(variants__isnull=False).count(), 2)


class ProgressTests(FlowBase):
    def test_slow_answer_shows_progress_then_becomes_the_answer(self):
        Settings.load()
        slow = Decision("ai", None, 90, "AI javobi: supervayzer marshrutga qo'shadi.", False)

        def fake(*a, **k):
            return None if k.get("fast") else slow
        with mock.patch.object(engine, "decide", side_effect=fake):
            self.h().handle(group_msg(1, 10, "klientim agentda ko'rinmayapti nima qilay"))
        group = [x for x in self.tg.sent if x["chat"] == -100]
        self.assertEqual(len(group), 1)  # bitta xabar: avval "ko'ryapman…", keyin shu xabar javobga aylandi
        self.assertTrue(group[0]["placeholder"].startswith(("🔎", "👀", "⏳")))
        self.assertEqual(group[0]["reply_to"], 1)
        self.assertIn("supervayzer marshrutga", group[0]["text"])
        self.assertEqual(Message.objects.get(message_id=1).status, Message.ANSWERED)

    def test_fast_answer_also_starts_with_reply_and_becomes_answer(self):
        Entry.objects.create(kind=Entry.FAQ, title="Parol", answer="Profil → Parolni tiklash.",
                             questions=["parolni qanday tiklayman"], status=Entry.APPROVED)
        Settings.objects.update(ai_primary=False, ai_enabled=False)
        self.h().handle(group_msg(2, 10, "parolni qanday tiklayman"))
        group = [x for x in self.tg.sent if x["chat"] == -100]
        self.assertEqual(len(group), 1)
        self.assertEqual(group[0]["reply_to"], 2)
        self.assertIn("Parolni tiklash", group[0]["text"])


class PolicyTests(FlowBase):
    def setUp(self):
        super().setUp()
        Settings.load()
        self.std = Entry.objects.create(kind=Entry.TEMPLATE, title="Planshet qotdi", answer="Planshetni 10 soniya bosib qayta yoqing.",
                                        questions=["planshet ekrani qotib qoldi nima qilay"], status=Entry.APPROVED)
        self.faq = Entry.objects.create(kind=Entry.FAQ, title="Kassa", answer="Kassani qayta yoqing.",
                                        questions=["kassa apparati chek chiqarmayapti"], status=Entry.APPROVED)
        Settings.objects.update(ai_primary=False, ai_enabled=False, answer_policy="standard")

    def test_standard_policy_answers_templates_and_learns_the_rest(self):
        h = self.h()
        h.handle(group_msg(1, 10, "planshet ekrani qotib qoldi nima qilay"))
        h.handle(group_msg(2, 11, "kassa apparati chek chiqarmayapti"))
        a = Message.objects.get(message_id=1)
        b = Message.objects.get(message_id=2)
        self.assertEqual(a.status, Message.ANSWERED)
        self.assertEqual((b.status, b.entry_id), (Message.DRAFTED, self.faq.id))  # o'rganish rejimi, taklif saqlandi
        texts = [x["text"] for x in self.tg.sent if x["chat"] == -100]
        self.assertIn("Planshetni 10 soniya bosib qayta yoqing.", " | ".join(texts))
        self.assertNotIn("Kassani qayta yoqing", " | ".join(texts))
        self.assertTrue(any("qabul qilindi" in t for t in texts))

    def test_entry_override_wins(self):
        Entry.objects.filter(pk=self.faq.pk).update(answer_mode="on")
        Entry.objects.filter(pk=self.std.pk).update(answer_mode="off")
        h = self.h()
        h.handle(group_msg(1, 10, "planshet ekrani qotib qoldi nima qilay"))
        h.handle(group_msg(2, 11, "kassa apparati chek chiqarmayapti"))
        self.assertEqual(Message.objects.get(message_id=1).status, Message.DRAFTED)
        self.assertEqual(Message.objects.get(message_id=2).status, Message.ANSWERED)

    def test_template_found_by_questions_and_bulk_kind_change(self):
        self.login("editor")
        r = self.call("post", "support/entries/bulk/", {"ids": [self.faq.id], "action": "kind_template"})
        self.assertEqual(r.json()["done"], 1)
        self.assertEqual(Entry.objects.get(pk=self.faq.pk).kind, Entry.TEMPLATE)
        # standart holatga o'tgan yozuv shartlari bo'lmasa ham savol ko'rinishi bo'yicha topiladi
        self.assertEqual(engine.decide("kassa apparati chek chiqarmayapti").entry, Entry.objects.get(pk=self.faq.pk))
