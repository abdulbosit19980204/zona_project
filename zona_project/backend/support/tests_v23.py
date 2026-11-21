"""Tizim belgilari (ilova / manba / toifa), AI belgilash, o'qitish ma'lumoti eksporti, guruhlar bo'yicha tahlil."""
import json
from unittest import mock

from django.core.management import call_command

from zona.models import Department, Member

from . import ai_review, systems, training
from .models import AIJob, Entry, Group, Message, Settings
from .tests import group_msg
from .tests_controls import ControlsBase
from .tests_v6 import FlowBase


class DetectTests(FlowBase):
    def test_app_and_origin_differ(self):
        r = systems.detect("zakaz o'tmadi", "Визиты Каталог Задачи Корзина Профиль\nЗаказ отклонен — 1C не принял заказ")
        self.assertEqual((r["app"], r["origin"], r["category"]), ("protarget", "1c", "order"))

    def test_from_knowledge_base_title(self):
        r = systems.detect("", "", "PRBC → 1C: klient 1C'da allaqachon bor")
        self.assertEqual((r["app"], r["origin"]), ("prbc", "1c"))
        self.assertGreaterEqual(r["conf"], 80)

    def test_category_only(self):
        r = systems.detect("Aksiya ishlamayapti klientda", "")
        self.assertEqual((r["app"], r["category"]), ("", "promo"))

    def test_network_origin(self):
        r = systems.detect("PRBC ochilmayapti", "Kirish amalga oshmadi — server vaqtincha javob bermayapti")
        self.assertEqual((r["app"], r["origin"]), ("prbc", "network"))

    def test_live_question_gets_rule_labels(self):
        self.h().handle(group_msg(50, 1, "ProTarget da vizit boshlanmayapti, geoteg radiusi chiqyapti"))
        q = Message.objects.get(message_id=50)
        self.assertEqual((q.app, q.category, q.labeled_by), ("protarget", "visit", "rule"))

    def test_backfill_command_skips_ai_labels(self):
        self.h().handle(group_msg(51, 1, "ProTarget da vizit boshlanmayapti, geotegdan uzoq deyapti"))
        q = Message.objects.get(message_id=51)
        Message.objects.filter(pk=q.pk).update(app="1c", labeled_by="ai")
        call_command("support_label_rules", verbosity=0)
        q.refresh_from_db()
        self.assertEqual((q.app, q.labeled_by), ("1c", "ai"))


class AILabelTests(FlowBase):
    def setUp(self):
        super().setUp()
        Settings.load()
        Settings.objects.update(ai_enabled=True, ai_daily_limit=20000)
        self.h().handle(group_msg(60, 1, "Aksiya klientga o'tmayapti zakazda"))
        self.q = Message.objects.get(message_id=60)

    def run_job(self, out):
        job = AIJob.objects.create(kind=AIJob.LABELS, params={"limit": 50})
        with mock.patch.object(ai_review, "_run", return_value=out) as r:
            ai_review.run_job(job.id)
        job.refresh_from_db()
        return job, r

    def test_ai_labels_question(self):
        out = {"items": [{"id": self.q.id, "app": "protarget", "origin": "1c", "category": "promo",
                          "problem": "Aksiya ProTarget zakazida qo'llanmayapti", "solution": "1C'da aksiya klientga biriktirildi",
                          "train": True, "reason": "x"}, {"id": 999999, "app": "1c", "origin": "1c", "category": "other",
                                                         "problem": "", "solution": "", "train": False, "reason": ""}]}
        from .engine import ai_quota_left
        self.assertGreater(ai_quota_left(Settings.load()), 1000, Settings.load().ai_daily_limit)
        job, r = self.run_job(out)
        self.q.refresh_from_db()
        self.assertEqual(job.error, "")
        self.assertTrue(r.called)
        self.assertEqual((self.q.app, self.q.origin, self.q.labeled_by, self.q.train), ("protarget", "1c", "ai", True))
        self.assertIn("1C'da aksiya", self.q.solution)
        self.assertEqual(job.status, AIJob.DONE)
        self.assertIn("GURUH", r.call_args[0][2])  # guruh nomi kontekstda

    def test_staff_label_is_not_overwritten(self):
        Message.objects.filter(pk=self.q.pk).update(app="prbc", labeled_by="staff")
        job, r = self.run_job({"items": []})
        r.assert_not_called()  # xodim belgilagan savol AI'ga yuborilmaydi

    def test_reserve_keeps_quota_for_live_answers(self):
        Settings.objects.update(ai_daily_limit=100)
        job, r = self.run_job({"items": []})
        r.assert_not_called()
        self.assertIn("zaxira", job.error)


class TrainingExportTests(ControlsBase):
    def setUp(self):
        super().setUp()
        self.g = Group.objects.create(bot=self.bot, chat_id=-100, title="MDLZ ROP")
        it = Department.objects.create(name="IT x")
        Member.objects.create(name="Test Xodim", role="r", department=it, telegram="test_op")

    def test_export_contains_resolved_conversation_and_kb_with_phones_masked(self):
        from .runner import Handler
        h = Handler(self.bot, self.tg)
        h.handle(group_msg(70, 1, "Aksiya klientga o'tmayapti, tel 90 123 45 67"))
        h.handle(group_msg(71, 2, "1C da aksiyani klientga biriktirdim, qayta sinxronlang", username="test_op", reply_to=70))
        q = Message.objects.get(message_id=70)
        Message.objects.filter(pk=q.pk).update(train=True, app="protarget", origin="1c", category="promo")
        Entry.objects.create(kind=Entry.FAQ, title="Aksiya ishlamayapti", questions=["aksiya o'tmayapti"],
                             answer="1C'da aksiya shartini tekshiring", status=Entry.APPROVED)
        rows = [json.loads(x) for x in training.export_lines()]
        chat = [r for r in rows if r["meta"]["source"] == "chat"]
        self.assertEqual(len(chat), 1)
        self.assertIn("qayta sinxronlang", chat[0]["messages"][2]["content"])
        self.assertIn("<telefon>", chat[0]["messages"][1]["content"])
        self.assertNotIn("123 45 67", json.dumps(chat[0], ensure_ascii=False))
        self.assertEqual(chat[0]["meta"]["origin"], "1c")
        self.assertTrue(any(r["meta"]["source"] == "kb" for r in rows))

    def test_api_export_and_stats_admin_only(self):
        self.login("admin")
        r = self.call("get", "support/training/export/?stats=1")
        self.assertEqual(r.status_code, 200)
        self.assertIn("train", r.json())
        r = self.call("get", "support/training/export/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r["Content-Disposition"])
        self.login("editor")
        self.assertEqual(self.call("get", "support/training/export/").status_code, 403)

    def test_analytics_systems_by_group_and_label_api(self):
        q = Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=80, kind=Message.QUESTION,
                                   text="x", app="protarget", origin="1c", category="promo", labeled_by="ai")
        self.login("admin")
        sysd = self.call("get", "support/analytics/").json()["systems"]
        self.assertEqual(sysd["pairs"][0], {"app": "protarget", "origin": "1c", "n": 1})
        self.assertEqual(sysd["groups"][0]["title"], "MDLZ ROP")
        r = self.call("post", f"support/messages/{q.id}/label/", {"origin": "protarget", "train": False})
        self.assertEqual(r.status_code, 200, r.content)
        q.refresh_from_db()
        self.assertEqual((q.origin, q.labeled_by, q.train), ("protarget", "staff", False))
        self.assertEqual(self.call("post", f"support/messages/{q.id}/label/", {"app": "xxx"}).status_code, 400)
