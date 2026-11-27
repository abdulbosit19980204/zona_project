"""Bot aniqligini baholash (support_eval): to'plam, javob yuborilmaydi, holdout, hukm, mas'ul va xulosa."""
from unittest import mock

from zona.models import Department, Member, TeamContact

from . import engine, evaluate
from .models import Entry, Message, Settings, TgUser
from .tests_controls import ControlsBase


class EvalTests(ControlsBase):
    def setUp(self):
        super().setUp()
        Settings.load()
        Settings.objects.update(ai_enabled=False)
        dep = Department.objects.create(name="IT")
        self.pt = Member.objects.create(name="Pro-target", role="PT", department=dep, is_team=True, level="EXT")
        g = TeamContact.objects.create(member=self.pt, name="Guzel Taipova", telegram="Guzel_Taipova")
        self.guzel = TgUser.objects.create(tg_id=5, username="Guzel_Taipova", name="Guzel", contact=g)
        self.agent = TgUser.objects.create(tg_id=900, username="agent", name="Agent")
        s = Settings.load()
        s.category_owners = {"visit": self.pt.pk}
        s.save()
        Entry.objects.create(kind=Entry.FAQ, title="Aktiv vizit bor", questions=["aktiv vizit bor deyapti"],
                             answer="Ochiq vizitni «Магазин закрыт» bilan yoping.", status=Entry.APPROVED)
        self.n = 0

    def pair(self, q_text, a_text):
        self.n += 1
        q = Message.objects.create(bot=self.bot, chat_id=-1, message_id=self.n, kind=Message.QUESTION, text=q_text,
                                   user=self.agent, source="live")
        self.n += 1
        Message.objects.create(bot=self.bot, chat_id=-1, message_id=self.n, kind=Message.STAFF, question=q,
                               user=self.guzel, text=a_text)
        return q

    def test_run(self):
        self.pair("aktiv vizit bor deyapti, vizit ochilmayapti", "Eski vizitni «Магазин закрыт» qilib yoping")
        self.pair("Assalomu alaykum", "Va alaykum assalom, savolingiz?")             # salom — to'plamga kirmaydi
        self.pair("Vizit lokatsiya uzoq deyapti nima qilay", "Готово")                 # «Готово» — javob emas
        q3 = self.pair("Tashrif vaqti noto'g'ri ko'rsatilyapti nima qilay", "Ilovani Play Marketdan yangilang, keyin vaqt avtomatik chiqadi")
        sent_before = Message.objects.count()
        with mock.patch.object(evaluate, "judge", return_value=("correct", "mos")) as j:
            summ, rows = evaluate.run(days=30, limit=10)
        self.assertEqual(Message.objects.count(), sent_before)                          # hech narsa yozilmadi
        self.assertEqual(summ["questions"], 2)
        self.assertEqual(summ["bot_answered"], 1)
        self.assertEqual(j.call_count, 1)
        self.assertEqual(summ["accuracy_pct"], 100)
        hand = next(r for r in rows if r["id"] == q3.pk)
        self.assertFalse(hand["sent"])
        self.assertTrue(hand["owner_ok"])                                               # mas'ul Pro-target = Guzel jamoasi
        self.assertEqual(engine.EVAL_HOLDOUT, set())
        self.assertIn("Bot aniqligi", evaluate.markdown(summ, rows))

    def test_holdout_hides_own_answer(self):
        q = self.pair("Klient agentda chiqmayapti nima qilay", "Supervayzer marshrutga qo'shadi, keyin sinxronlang")
        engine._STAFF["key"] = None
        self.assertTrue(engine.staff_examples("Klient agentda chiqmayapti", min_score=0))
        engine.EVAL_HOLDOUT.add(q.pk)
        try:
            self.assertEqual(engine.staff_examples("Klient agentda chiqmayapti", min_score=0), [])
        finally:
            engine.EVAL_HOLDOUT.clear()


class AiDownTests(ControlsBase):
    def test_circuit_breaker(self):
        from zona.models import AIUsage
        engine._AI_DOWN.update(at=0.0, down=False)
        self.assertFalse(engine.ai_down())
        for _ in range(8):
            AIUsage.objects.create(task="support", provider="g", model="m", ok=False, error="429")
        engine._AI_DOWN.update(at=0.0)
        self.assertTrue(engine.ai_down())
        AIUsage.objects.create(task="support", provider="g", model="m", ok=True)
        engine._AI_DOWN.update(at=0.0)
        self.assertFalse(engine.ai_down())


class StatusPanelTests(ControlsBase):
    def test_stats_panel(self):
        from django.utils import timezone
        Settings.load()
        dep = Department.objects.create(name="IT")
        said = Member.objects.create(name="Saidabror", role="Op", department=dep, telegram="StargroupSaid")
        s = Settings.load()
        s.category_owners = {"promo": said.pk}
        s.save()
        mk = lambda i, **kw: Message.objects.create(bot=self.bot, chat_id=-1, message_id=i, kind=Message.QUESTION,  # noqa: E731
                                                     text="savol", **kw)
        mk(1, stage="faq", status=Message.ANSWERED)
        mk(2, stage="template", status=Message.ANSWERED, review="wrong")
        mk(3, status=Message.ESCALATED, category="promo")
        mk(4, status=Message.ESCALATED, category="promo")
        old = mk(5, stage="ai", status=Message.ANSWERED)
        Message.objects.filter(pk=old.pk).update(created_at=timezone.now() - timezone.timedelta(days=10))
        self.login("viewer")
        p = self.call("get", "support/stats/?days=7").json()["panel"]
        self.assertEqual((p["bot"], p["prev_total"], p["prev_bot"], p["wrong"]), (2, 1, 1, 1))
        self.assertEqual(p["escalated_by_owner"], [{"name": "Saidabror", "count": 2}])

    def test_category_stats(self):
        from zona.models import TeamContact
        dep = Department.objects.create(name="IT2")
        pt = Member.objects.create(name="Pro-target", role="PT", department=dep, is_team=True, level="EXT")
        g = TeamContact.objects.create(member=pt, name="Guzel Taipova", telegram="Guzel_Taipova")
        gu = TgUser.objects.create(tg_id=5, username="Guzel_Taipova", name="Guzel", contact=g)
        q = Message.objects.create(bot=self.bot, chat_id=-1, message_id=1, kind=Message.QUESTION, text="vizit", category="visit")
        Message.objects.create(bot=self.bot, chat_id=-1, message_id=2, kind=Message.STAFF, question=q, user=gu, text="javob")
        self.login("viewer")
        r = self.call("get", "support/category-stats/?days=30").json()
        self.assertEqual(r["visit"]["questions"], 1)
        self.assertEqual(r["visit"]["answered_by"], [{"name": "Guzel Taipova", "count": 1}])
        self.assertEqual(r["visit"]["teams"], ["Pro-target"])
