"""PRBC vazifa to'g'riligi (2026-11-27): tashqi jamoa (Pro-target, EXT) mas'ul bo'lgan savolga vazifa umuman
ochilmaydi va boshqa xodimga tushirilmaydi; Saidabror toifasi -> @StargroupSaid; umumiy akkaunt -> asosiy operator."""
from unittest import mock

from prbc import control
from zona.models import Department, Member, TeamContact

from . import engine, tasks
from .models import Entry, Message, Settings, TgUser
from .tests_controls import ControlsBase


class Base(ControlsBase):
    def setUp(self):
        super().setUp()
        dep = Department.objects.create(name="IT")
        self.pt = Member.objects.create(name="Pro-target", role="ProTarget", department=dep, is_team=True, level="EXT")
        self.guzel = TeamContact.objects.create(member=self.pt, name="Guzel Taipova", telegram="Guzel_Taipova")
        self.said = Member.objects.create(name="Saidabror", role="Operator", department=dep, level="L1",
                                          telegram="StargroupSaid")
        self.xus = Member.objects.create(name="Xusniddin", role="IT operator", department=dep, level="L1",
                                         telegram="ganiyevxusniddin")
        common = Member.objects.create(name="IT support (umumiy akkaunt)", role="IT", department=dep, is_team=True,
                                       level="L1")
        self.it = TeamContact.objects.create(member=common, name="STAR GROUP", telegram="IT_StarGroup", operator=self.xus)
        s = Settings.load()
        s.tasks_enabled, s.task_all_escalated, s.task_default_assignee = True, True, "default_op"
        s.category_owners = {"visit": self.pt.pk, "promo": self.said.pk, "login": f"c:{self.guzel.pk}"}
        s.save()

    def decide(self, text):
        q = Message(kind=Message.QUESTION, text=text)
        d = engine.apply_owner(engine.Decision("", None, 0, "", True, []), text)
        return tasks.decide_task(q, d)


class ExternalTaskTests(Base):
    def test_pro_target_category_opens_no_task(self):
        self.assertEqual(self.decide("vizit ochilmayapti, aktiv vizit bor deyapti"), (False, "", "ext"))

    def test_pro_target_member_as_owner_opens_no_task(self):
        self.assertEqual(self.decide("parolni unutdim, login qilolmayapman"), (False, "", "ext"))

    def test_saidabror_category_goes_to_him(self):
        need, who, _why = self.decide("aksiya chiqmayapti klientga")
        self.assertEqual((need, who), (True, "StargroupSaid"))

    def test_entry_with_task_and_ext_responsible(self):
        e = Entry.objects.create(kind=Entry.FAQ, title="Nuqta moderatsiyada", answer="x", status=Entry.APPROVED,
                                 responsible=self.pt, creates_task=True)
        q = Message(kind=Message.QUESTION, text="nuqta moderatsiyada turibdi")
        d = engine.Decision("faq", e, 90, "x", False, [engine._person(self.pt)])
        self.assertEqual(tasks.decide_task(q, d), (False, "", "ext"))

    def test_escalated_with_ext_first_is_not_dropped_to_someone_else(self):
        q = Message(kind=Message.QUESTION, text="savdo nuqtasini ulab bering iltimos")
        d = engine.Decision("", None, 0, "", True, [engine._person(self.pt), engine._person(self.said)])
        self.assertEqual(tasks.decide_task(q, d), (False, "", "ext"))


class PrbcAssigneeTests(Base):
    def test_ext_never_assignee_or_watcher(self):
        g = TgUser.objects.create(tg_id=5, username="Guzel_Taipova", name="Guzel", contact=self.guzel)
        with mock.patch("prbc.tasks.assignee_ids_for", return_value=[42]):
            self.assertIsNone(control._prbc_of_tg(g, mock.Mock()))
            self.assertEqual(control._member_ids(self.pt, mock.Mock()), [])
            self.assertEqual(control._member_ids(engine.owner_of(f"c:{self.guzel.pk}"), mock.Mock()), [])

    def test_shared_account_answer_goes_to_operator(self):
        u = TgUser.objects.create(tg_id=8977751590, username="IT_StarGroup", name="STAR GROUP", contact=self.it)
        with mock.patch("prbc.tasks.assignee_ids_for",
                        side_effect=lambda n, c: {"ganiyevxusniddin": [77]}.get(n.lstrip("@"), [])):
            self.assertEqual(control._prbc_of_tg(u, mock.Mock()), 77)


class AnalyticsCreditTests(Base):
    def test_shared_account_answers_counted_for_operator_and_pro_target_split(self):
        from .tests import group_msg
        xu = TgUser.objects.create(tg_id=10, username="ganiyevxusniddin", name="Xusniddin", member=self.xus)
        TgUser.objects.create(tg_id=11, username="IT_StarGroup", name="STAR GROUP", contact=self.it)
        eldar = TeamContact.objects.create(member=self.pt, name="Eldar", telegram="anarbekoov077")
        TgUser.objects.create(tg_id=12, username="Guzel_Taipova", name="Guzel", contact=self.guzel)
        TgUser.objects.create(tg_id=13, username="anarbekoov077", name="Eldar", contact=eldar)
        h = self.handler()
        h.handle(group_msg(1, 500, "Klientim agentda ko'rinmayapti, nima qilay?"))
        h.handle(group_msg(2, 11, "Klient 1C da yopilgan: Saidabror qayta ochadi, keyin sinxronlang", "IT_StarGroup",
                           reply_to=1))
        h.handle(group_msg(3, 502, "Vizit ochilmayapti, aktiv vizit bor deyapti"))
        h.handle(group_msg(4, 12, "Ochiq vizitni «Магазин закрыт» bilan yoping, keyin yangisini oching", "Guzel_Taipova",
                           reply_to=3))
        h.handle(group_msg(5, 501, "Foto otmayapti, yuklanmayapti"))
        h.handle(group_msg(6, 13, "Ilovani yopib qayta oching, keyin vizitni davom ettiring",
                           "anarbekoov077", reply_to=5))
        self.login("viewer")
        rows = {r["name"]: r for r in self.call("get", "support/analytics/?days=30").json()["staff"]}
        self.assertNotIn("STAR GROUP", rows)
        self.assertEqual(rows["Xusniddin"]["answers"], 1)
        self.assertEqual((rows["Guzel Taipova"]["answers"], rows["Eldar"]["answers"]), (1, 1))
        self.assertTrue(xu.pk)


class CaseDedupeTests(Base):
    """Bitta holat = bitta agent + bitta obyekt (UZ-kod, zakaz, STIR) + bitta muammo: turli klient — alohida vazifa."""

    def setUp(self):
        super().setUp()
        Settings.objects.update(task_mode="api")
        self.agent = TgUser.objects.create(tg_id=900, username="agent1", name="Agent")
        self.mid = 0

    def ask(self, text, user=None):
        self.mid += 1
        q = Message.objects.create(bot=self.bot, chat_id=-1, message_id=self.mid, kind=Message.QUESTION, text=text,
                                   user=user or self.agent, category="promo")
        d = engine.apply_owner(engine.Decision("", None, 0, "", True, []), text)
        return tasks.maybe_create(q, d)

    def test_three_clients_three_tasks_same_client_one_task(self):
        from .models import SupportTask
        a = self.ask("UZ-00011111 klientga aksiya chiqmayapti")
        b = self.ask("UZ-00022222 klientga aksiya chiqmayapti")
        c = self.ask("UZ-00033333 klientga ham aksiya chiqmayapti")
        self.assertEqual(len({a.pk, b.pk, c.pk}), 3)
        again = self.ask("UZ-00011111 da hali ham aksiya yo'q, skidka chiqmadi")
        self.assertEqual(again.pk, a.pk)
        self.assertEqual(SupportTask.objects.count(), 3)
        self.assertEqual(len(SupportTask.objects.get(pk=a.pk).duplicates), 1)

    def test_continuation_goes_to_open_task(self):
        a = self.ask("UZ-00044444 klientga aksiya skidka chiqmayapti")
        t = self.ask("Тут тоже самое")
        self.assertEqual(t.pk if t else None, a.pk)

    def test_no_owner_no_task(self):
        Settings.objects.update(category_owners=None)
        q = Message.objects.create(bot=self.bot, chat_id=-1, message_id=99, kind=Message.QUESTION,
                                   text="Ilovada noma'lum xato chiqyapti, ishlamayapti", user=self.agent)
        d = engine.Decision("", None, 0, "", True, [])
        self.assertEqual(tasks.decide_task(q, d), (False, "", "no-owner"))

    def test_title_from_meaningful_message(self):
        q = Message.objects.create(bot=self.bot, chat_id=-1, message_id=50, kind=Message.QUESTION, text="Добрый день",
                                   user=self.agent)
        Message.objects.create(bot=self.bot, chat_id=-1, message_id=51, kind=Message.INFO, question=q, user=self.agent,
                               text="Klientga aksiya skidka chiqmayapti UZ-00055555")
        title = tasks.problem_text(q, "Savol")
        self.assertTrue(title.startswith("Klientga aksiya skidka chiqmayapti"), title)
        q2 = Message.objects.create(bot=self.bot, chat_id=-1, message_id=52, kind=Message.QUESTION, text="Кушиб беринг",
                                    user=self.agent, ocr_text="Торговая точка «Bahor» отправлена на модерацию")
        self.assertNotIn("Кушиб", tasks.problem_text(q2, "Savol"))

    def test_shared_account_assignee_is_operator(self):
        self.assertEqual(tasks.operator_tg("@IT_StarGroup"), "ganiyevxusniddin")
        self.assertEqual(tasks.operator_tg("StargroupSaid"), "StargroupSaid")
        self.assertEqual(tasks.case_keys("uz-00012345 va zakaz 1234567, STIR 301234567"),
                         {"UZ-00012345", "zakaz:1234567", "stir:301234567"})


class OwnerWorkTaskTests(Base):
    """28.11: bugungi savollarga vazifa ochilmagan — bot javob bergan/uzatgan bo'lsa ham mas'ulning ishi vazifa bo'ladi."""
    def _d(self, text, stage="ai"):
        d = engine.apply_owner(engine.Decision(stage, None, 90, "javob", False, []), text)
        return d

    def test_bot_answered_owner_request_opens_task(self):
        q = Message(kind=Message.QUESTION, text="Здравствуйте скидку можно sr2 Urgench", status=Message.ANSWERED)
        self.assertEqual(tasks.decide_task(q, self._d(q.text))[:2], (True, "StargroupSaid"))

    def test_handoff_opens_task(self):
        q = Message(kind=Message.QUESTION, text="aksiya qo'shib bering", status=Message.ESCALATED, stage="handoff")
        self.assertEqual(tasks.decide_task(q, self._d(q.text))[:2], (True, "StargroupSaid"))

    def test_standard_answer_solved_by_bot_no_task(self):
        q = Message(kind=Message.QUESTION, text="aksiya qanday ko'rinadi", status=Message.ANSWERED)
        self.assertFalse(tasks.decide_task(q, self._d(q.text, stage="template"))[0])

    def test_ext_owner_still_no_task(self):
        q = Message(kind=Message.QUESTION, text="vizit ochilmayapti", status=Message.ESCALATED, stage="handoff")
        self.assertEqual(tasks.decide_task(q, self._d(q.text)), (False, "", "ext"))

    def test_greeting_no_task(self):
        q = Message(kind=Message.QUESTION, text="salom", status=Message.ANSWERED)
        self.assertFalse(tasks.decide_task(q, engine.Decision("ai", None, 90, "x", False, []))[0])
