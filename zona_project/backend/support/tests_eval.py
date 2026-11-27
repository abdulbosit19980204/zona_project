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
