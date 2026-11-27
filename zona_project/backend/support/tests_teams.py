"""Jamoalar va mas'ullar: toifaga asosiy + zaxira mas'ul; jamoaga qo'shilgan yakka xodimlar (Dasturchilar: Ulug'bek,
Kamoliddin, Timur); umumiy akkauntning asosiy operatori (@IT_StarGroup -> Xusniddin); toifa qoidalari (ТТ/точка,
доступ/позывной)."""
from unittest import mock

from django.utils import timezone

from prbc import control
from zona import timeload
from zona.models import Department, Member, Task, TeamContact

from . import activity, engine, systems, tasks
from .models import Message, Settings, TgUser
from .tests_controls import ControlsBase


class Base(ControlsBase):
    def setUp(self):
        super().setUp()
        dep = Department.objects.create(name="IT")
        self.dev = Member.objects.create(name="Dasturchilar jamoasi", role="Dasturchilar", department=dep, is_team=True)
        TeamContact.objects.create(member=self.dev, name="Ulug'bek", telegram="stargroupUlugbek")
        self.kamol = Member.objects.create(name="Kamoliddin Atakulov", role="IT direktor", department=dep,
                                           telegram="DevProgArt", member_of=self.dev)
        self.timur = Member.objects.create(name="Timur Doskabilov", role="Dasturchi", department=dep,
                                           telegram="timurdoskabilov", member_of=self.dev)
        self.xus = Member.objects.create(name="Xusniddin", role="IT operator", department=dep, telegram="ganiyevxusniddin")
        self.op = Member.objects.create(name="Saidabror", role="Operator", department=dep, telegram="StargroupSaid")
        self.common = Member.objects.create(name="IT support (umumiy akkaunt)", role="IT support", department=dep,
                                            is_team=True)
        self.it = TeamContact.objects.create(member=self.common, name="STAR GROUP", telegram="IT_StarGroup",
                                             operator=self.xus)
        Settings.load()


class CategoryRuleTests(Base):
    def test_new_words(self):
        for text, cat in [("ТТ не открывается", "client"), ("новая точка не добавляется", "prbc_outlet"),
                          ("yangi tochka qo'sha olmayapman", "prbc_outlet"), ("т.т. закрыта", "client"),
                          ("доступ нет", "login"), ("dostup bering", "login"), ("pozivnoy biriktirilmagan", "login"),
                          ("позывной не найден", "login"), ("aksiya ishlamayapti", "promo"),
                          ("ostatka ko'rinmayapti", "stock")]:
            self.assertEqual(systems.detect(text)["category"], cat, text)


class TeamMembersTests(Base):
    def test_team_owner_tags_contacts_and_members(self):
        tgs = engine._person(self.dev)["telegram"]
        self.assertEqual(tgs, ["stargroupUlugbek", "DevProgArt", "timurdoskabilov"])

    def test_staff_endpoint_lists_members_under_team(self):
        self.login("admin")
        rows = {r["name"]: r for r in self.call("get", "support/staff/").json()}
        self.assertEqual(rows["Kamoliddin Atakulov"]["team_id"], self.dev.pk)
        self.assertEqual(rows["Timur Doskabilov"]["team"], "Dasturchilar jamoasi")
        self.assertEqual(rows["STAR GROUP"]["operator"], "Xusniddin")

    def test_member_of_validation(self):
        self.login("admin")
        r = self.call("patch", f"members/{self.dev.pk}/", {"member_of": self.dev.pk})
        self.assertEqual(r.status_code, 400, r.content)
        r = self.call("patch", f"members/{self.xus.pk}/", {"member_of": self.xus.pk})
        self.assertEqual(r.status_code, 400, r.content)                   # faqat jamoaga
        r = self.call("patch", f"members/{self.xus.pk}/", {"member_of": self.dev.pk})
        self.assertEqual(r.status_code, 200, r.content)

    def test_team_load_share(self):
        Task.objects.create(title="Integratsiya xatosi", owner=self.dev, minutes=60, per_week=6)
        load = timeload.member_load()
        self.assertAlmostEqual(load[self.dev.pk]["owner_min"], 360)
        self.assertAlmostEqual(load[self.kamol.pk]["team_min"], 120)      # 1 kontakt + 2 a'zo
        self.assertAlmostEqual(load[self.kamol.pk]["total_h"], 2)
        self.assertEqual(load[self.xus.pk]["team_min"], 0)

    def test_report_team_of_member(self):
        u = TgUser.objects.create(tg_id=1, username="timurdoskabilov", name="Timur", member=self.timur)
        u = TgUser.objects.select_related("member__member_of", "contact").get(pk=u.pk)
        self.assertEqual(activity.team_of(u), "Dasturchilar jamoasi")


class BackupOwnerTests(Base):
    def test_backup_saved_and_tagged(self):
        self.login("admin")
        r = self.call("patch", "support/settings/", {"category_owners": {"promo": self.op.pk},
                                                     "category_backups": {"promo": self.xus.pk, "zzz": 1}})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["category_backups"], {"promo": self.xus.pk})
        r = self.call("patch", "support/settings/", {"category_backups": {"promo": 999999}})
        self.assertEqual(r.status_code, 400)
        d = engine.apply_owner(engine.Decision("ai", None, 90, "javob", False, []), "aksiya ishlamayapti")
        self.assertTrue(d.owner)
        self.assertEqual(d.responsible[0]["name"], "Saidabror")
        self.assertEqual(engine.owner_tags(d.responsible), "@StargroupSaid · zaxira: @ganiyevxusniddin")
        self.assertIn("zaxira: Xusniddin", engine.responsible_line(d.responsible, "uz"))
        self.assertIn("zaxira — Xusniddin", engine.owner_line("aksiya chiqmayapti"))

    def test_same_as_main_or_empty_is_ignored(self):
        Settings.objects.update(category_owners={"promo": self.op.pk}, category_backups={"promo": self.op.pk})
        self.assertIsNone(engine.category_backup("promo"))
        d = engine.apply_owner(engine.Decision("ai", None, 90, "javob", False, []), "aksiya")
        self.assertNotIn("backup", d.responsible[0])
        self.assertEqual(engine.owner_tags(d.responsible), "@StargroupSaid")

    def test_backup_is_prbc_watcher(self):
        Settings.objects.update(category_owners={"promo": self.op.pk}, category_backups={"promo": self.xus.pk})
        q = Message(kind=Message.QUESTION, category="promo")
        with mock.patch("prbc.tasks.assignee_ids_for", side_effect=lambda n, c: {"ganiyevxusniddin": [55]}.get(n.lstrip("@"), [])):
            self.assertEqual(control.backup_ids(mock.Mock(), q), [55])


class OperatorTests(Base):
    def test_prbc_answerer_is_operator(self):
        u = TgUser.objects.create(tg_id=8977751590, username="IT_StarGroup", name="STAR GROUP", contact=self.it)
        with mock.patch("prbc.tasks.assignee_ids_for", side_effect=lambda n, c: {"ganiyevxusniddin": [77]}.get(n.lstrip("@"), [])):
            self.assertEqual(control._prbc_of_tg(u, mock.Mock()), 77)
        self.it.operator = None
        self.it.save()
        u = TgUser.objects.get(pk=u.pk)
        self.assertIsNone(control._prbc_of_tg(u, mock.Mock()))          # operator yo'q — umumiy akkaunt e'tiborsiz

    def test_team_task_assignee_is_operator(self):
        s = Settings.load()
        s.task_default_assignee = ""
        self.assertEqual(tasks._tg_of(self.common, s), "ganiyevxusniddin")

    def test_board_merges_shared_account_into_operator(self):
        xu = TgUser.objects.create(tg_id=10, username="ganiyevxusniddin", name="Xusniddin", member=self.xus)
        it = TgUser.objects.create(tg_id=11, username="IT_StarGroup", name="STAR GROUP", contact=self.it)
        q = Message.objects.create(bot=self.bot, chat_id=-1, message_id=1, kind=Message.QUESTION, text="savol")
        for i, u in enumerate([xu, it, it]):
            Message.objects.create(bot=q.bot, chat_id=-1, message_id=10 + i, kind=Message.STAFF, user=u, question=q,
                                   text="Tekshirdim, to'g'riladim — endi ishlaydi")
        now = timezone.now()
        rep = activity.board(now - timezone.timedelta(days=1), now + timezone.timedelta(minutes=1))
        rows = {r["id"]: r for r in rep["staff"]}
        self.assertNotIn(it.pk, rows)
        self.assertEqual(rows[xu.pk]["answers"], 3)
        self.assertEqual(rows[xu.pk]["via"], ["@IT_StarGroup"])
