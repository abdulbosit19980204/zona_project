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
