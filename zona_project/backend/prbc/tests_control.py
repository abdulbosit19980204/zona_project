"""Vazifa nazorati (SLA): muddat, savol holati -> PRBC holati, muddati o'tganlar, vazifasiz savollar, panel API."""
from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from support import tasks as st_tasks
from support.engine import Decision
from support.models import Bot, Group, Message, Settings, SupportTask, TgUser
from zona.crypto import encrypt
from zona.models import Member

from . import control, tasks
from .models import Connection, Person, Task
from .tests import FakePrbc, FakeTg

TZ = ZoneInfo("Asia/Tashkent")
STATUSES = [{"id": 86, "project": 15, "name": "New", "category": "new", "is_default": True},
            {"id": 87, "project": 15, "name": "In Progress", "category": "in_progress"},
            {"id": 89, "project": 15, "name": "Done", "category": "done"},
            {"id": 90, "project": 15, "name": "Cancelled", "category": "cancelled"}]
BY_ID = {s["id"]: s for s in STATUSES}


class ControlPrbc(FakePrbc):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.patches, self.refuse = [], False

    def patch(self, path, body=None):
        from .client import PrbcError
        if self.refuse:
            raise PrbcError("Definition of Done bajarilmagan", 400)
        tid = int(path.strip("/").split("/")[-1])
        self.patches.append((tid, body))
        if "status" in (body or {}):
            s = BY_ID[body["status"]]
            self.task_status[tid] = {"id": s["id"], "name": s["name"], "category": s["category"]}
        return {}

    def pages(self, path, params=None, max_pages=200, stop=None):
        if path == "/task-statuses/":
            yield from STATUSES
            return
        yield from super().pages(path, params, max_pages, stop)


def at(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=TZ)


class SlaTests(TestCase):
    def setUp(self):
        self.c = Connection.get()  # standart: 10 daqiqa, Du–Sha 09:00–18:00

    def test_window_inside_working_hours(self):
        s, d = control.sla_window(self.c, at(2026, 11, 26, 10, 0))  # payshanba
        self.assertEqual((s, d), (at(2026, 11, 26, 10, 0), at(2026, 11, 26, 10, 10)))

    def test_after_hours_and_sunday_move_to_next_work_morning(self):
        s, d = control.sla_window(self.c, at(2026, 11, 26, 21, 30))
        self.assertEqual((s, d), (at(2026, 11, 27, 9, 0), at(2026, 11, 27, 9, 10)))
        s, d = control.sla_window(self.c, at(2026, 11, 29, 12, 0))  # yakshanba -> dushanba
        self.assertEqual(s, at(2026, 11, 30, 9, 0))

    def test_crosses_end_of_day(self):
        s, d = control.sla_window(self.c, at(2026, 11, 26, 17, 55))
        self.assertEqual(d, at(2026, 11, 27, 9, 5))  # 5 daqiqa bugun + 5 daqiqa ertaga


class Base(TestCase):
    def setUp(self):
        self.conn = Connection.get()
        self.conn.enabled, self.conn.phone, self.conn.password_enc = True, "998900000000", encrypt("x")
        self.conn.task_project, self.conn.task_default_assignees = 15, [167]
        self.conn.save()
        s = Settings.load()
        s.task_mode, s.tasks_enabled = "api", True
        s.save()
        self.tg = FakeTg()
        p = mock.patch.object(tasks, "_bot_client", lambda q: self.tg)
        p.start()
        self.addCleanup(p.stop)
        Person.objects.create(prbc_user=167, full_name="G'ANIYEV XUSNIDDIN", name_key="ganiyev xusniddin", in_roster=True)
        self.bot = Bot.objects.create(name="S", token_enc=encrypt("1:x"))
        self.group = Group.objects.create(bot=self.bot, chat_id=-300, title="HEINZ ROP")
        self.user = TgUser.objects.create(tg_id=991, name="Boburmirzo")
        self.fake = ControlPrbc()

    def question(self, text="Ассалом алейкум. Профиль не завершается, номер принадлежит другому аккаунту", **kw):
        return Message.objects.create(bot=self.bot, group=self.group, chat_id=-300, message_id=500 + Message.objects.count(),
                                      user=self.user, kind="question", text=text, status=Message.ESCALATED, **kw)

    def open_task(self, q):
        SupportTask.objects.create(message=q, assignee="", title="Profil", text="Savol", status=SupportTask.QUEUED)
        self.assertEqual(tasks.process_support_queue(self.conn, self.fake), 1)
        return Task.objects.get(support_task__message=q)


class CreateWithSlaTests(Base):
    def test_task_gets_start_due_estimate_priority_and_clean_title(self):
        with mock.patch("django.utils.timezone.now", return_value=at(2026, 11, 26, 11, 0)):
            q = self.question()
            SupportTask.objects.filter(pk=0).delete()
            st = SupportTask.objects.create(message=q, assignee="", title="Profil", text="Savol", status=SupportTask.QUEUED)
            SupportTask.objects.filter(pk=st.pk).update(created_at=at(2026, 11, 26, 11, 0))
            tasks.process_support_queue(self.conn, self.fake)
        kw = self.fake.created[0]["kw"]
        self.assertEqual(kw["start_at"], at(2026, 11, 26, 11, 0).isoformat())
        self.assertEqual(kw["due_at"], at(2026, 11, 26, 11, 10).isoformat())
        self.assertEqual((kw["estimated_minutes"], kw["priority"], kw["project"]), (10, 3, 15))
        self.assertEqual(kw["assignee_ids"], [167])  # standart ijrochi
        self.assertFalse(kw["title"].lower().startswith("ассалом"))  # salomlashuv sarlavhada yo'q
        self.assertIn("Muddat: 26.11 11:10 gacha", kw["description"])


class PushStatusTests(Base):
    def test_resolved_question_closes_task_without_second_group_message(self):
        q = self.question()
        t = self.open_task(q)
        from support.resolution import YES, mark
        mark(q, YES, "Xusniddin")
        self.assertEqual(control.push_status(self.conn, self.fake), 1)
        t.refresh_from_db()
        self.assertEqual(t.status_category, "done")
        self.assertEqual(self.fake.patches[-1][1], {"status": 89})
        self.assertIn("Savol hal bo'ldi (Xusniddin", self.fake.comments[-1][1])
        tasks.poll(self.conn, self.fake)  # hisobot; guruhga "bajarildi" qayta yozilmaydi — savol allaqachon hal
        self.assertFalse(any("bajarildi" in x[1].lower() for x in self.tg.sent))
        self.assertEqual(control.push_status(self.conn, self.fake), 0)  # takror — o'zgarish yo'q

    def test_staff_reply_moves_to_in_progress_then_reopen_on_not_solved(self):
        q = self.question()
        t = self.open_task(q)
        Message.objects.create(bot=self.bot, group=self.group, chat_id=-300, message_id=999, kind=Message.STAFF,
                               question=q, text="Tekshiryapman")
        self.assertEqual(control.push_status(self.conn, self.fake), 1)
        t.refresh_from_db()
        self.assertEqual(t.status_category, "in_progress")
        self.assertEqual(control.push_status(self.conn, self.fake), 0)
        # PRBC'da yopildi, keyin savol egasi "hal bo'lmadi" -> qayta ochiladi
        self.fake.task_status[t.prbc_id] = {"name": "Done", "category": "done"}
        tasks.poll(self.conn, self.fake)
        from support.resolution import NO, mark
        q.refresh_from_db()
        Message.objects.filter(pk=q.pk).update(resolution="", resolved_at=None)
        q.refresh_from_db()
        t.refresh_from_db()
        Task.objects.filter(pk=t.pk).update(completed_at=timezone.now() - timedelta(minutes=5))
        mark(q, NO, "savol egasi")
        self.assertEqual(control.push_status(self.conn, self.fake), 1)
        t.refresh_from_db()
        self.assertEqual(t.status_category, "in_progress")
        self.assertIn("hal bo'lmadi", self.fake.comments[-1][1])

    def test_refused_status_is_recorded(self):
        q = self.question()
        t = self.open_task(q)
        self.fake.refuse = True
        from support.resolution import YES, mark
        mark(q, YES, "Xusniddin")
        self.assertEqual(control.push_status(self.conn, self.fake), 0)
        t.refresh_from_db()
        self.assertIn("Definition of Done", t.sync["status_error"])

    def test_switch_off(self):
        q = self.question()
        self.open_task(q)
        Connection.objects.update(sync_status=False)
        from support.resolution import YES, mark
        mark(q, YES, "Xusniddin")
        self.assertEqual(control.push_status(Connection.get(), self.fake), 0)


class OverdueTests(Base):
    def test_overdue_marked_once(self):
        t = self.open_task(self.question())
        Task.objects.filter(pk=t.pk).update(due_at=timezone.now() - timedelta(minutes=7))
        self.assertEqual(control.watch_overdue(self.conn, self.fake), 1)
        self.assertEqual(self.fake.patches[-1][1], {"priority": 4})
        self.assertIn("Muddat o'tdi (7 daqiqa", self.fake.comments[-1][1])
        self.assertEqual(control.watch_overdue(self.conn, self.fake), 0)


class EscalationTests(Base):
    def test_every_escalated_question_gets_a_task(self):
        q = self.question("ProTarget'da klient chiqmayapti, nima qilay")
        d = Decision("", None, 0, "", True, [])
        need, assignee, reason = st_tasks.decide_task(q, d)
        self.assertTrue(need)
        self.assertEqual(reason, "escalated")
        sv = Member.objects.create(name="Supervayzerlar", role="SV", is_team=True)
        d = Decision("", None, 0, "", True, [{"id": sv.id, "name": sv.name}])
        self.assertTrue(st_tasks.decide_task(q, d)[0])
        Settings.objects.update(task_all_escalated=False)
        self.assertFalse(st_tasks.decide_task(q, Decision("", None, 0, "", True, []))[0])
        self.assertFalse(st_tasks.decide_task(q, Decision("faq", None, 90, "javob", False, []))[0])  # bot javob berdi

    def test_greeting_stripped(self):
        self.assertEqual(st_tasks.strip_greeting("Добрый день. Акция для аптек не работает"), "Акция для аптек не работает")
        self.assertEqual(st_tasks.strip_greeting("Assalomu alaykum Said aka, klient chiqmayapti"), "klient chiqmayapti")
        self.assertEqual(st_tasks.strip_greeting("Buyam qo'shildimi?"), "Buyam qo'shildimi?")

    def test_backfill_untasked_open_questions(self):
        q1 = self.question("Zakaz 1C ga o'tmayapti")
        self.question("Hal bo'lgan savol", resolution=Message.YES)
        Message.objects.create(bot=self.bot, group=self.group, chat_id=-300, message_id=77, user=self.user, kind="question",
                               text="eski", status=Message.ESCALATED, created_at=timezone.now())
        Message.objects.filter(message_id=77).update(created_at=timezone.now() - timedelta(days=20))
        self.assertEqual(control.backfill(dry=True), 1)
        self.assertEqual(control.backfill(actor="admin"), 1)
        self.assertTrue(SupportTask.objects.filter(message=q1, status=SupportTask.QUEUED).exists())
        self.assertEqual(control.backfill(dry=True), 0)


class ApiTests(Base):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(User.objects.create_superuser("adm", "a@x.uz", "x"))
        p = mock.patch("prbc.views.Client", lambda conn: self.fake)
        p.start()
        self.addCleanup(p.stop)

    def test_control_status_and_settings(self):
        q = self.question()
        t = self.open_task(q)
        self.question("Vazifasiz ochiq savol")
        r = self.api.get("/api/prbc/control/").json()
        self.assertEqual(r["summary"]["open"], 1)
        self.assertEqual(r["summary"]["untasked"], 1)
        self.assertEqual(r["open"][0]["asker"], "Boburmirzo")
        self.assertIsNotNone(r["open"][0]["due_in"])
        r = self.api.post(f"/api/prbc/tasks/{t.id}/status/", {"category": "done"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["category"], "done")
        r = self.api.patch("/api/prbc/connection/", {"sla_minutes": 15, "work_days": [0, 1, 2, 3, 4], "task_all_escalated": False},
                           format="json").json()
        self.assertEqual((r["sla_minutes"], r["work_days"], r["task_all_escalated"]), (15, [0, 1, 2, 3, 4], False))
        self.assertEqual(self.api.post("/api/prbc/tasks/backfill/", {"dry": True}, format="json").json()["count"], 1)


class OwnerPrbc(ControlPrbc):
    """Ijrochi qo'shish / olib tashlash va loyiha ruxsati (soxta)."""

    def __init__(self, *a, refuse_project=None, **kw):
        super().__init__(*a, **kw)
        self.refuse_project = refuse_project

    def create_task(self, **kw):
        from .client import PrbcError
        if self.refuse_project and kw.get("project") == self.refuse_project:
            raise PrbcError("Loyihaga ruxsat yo'q", 403)
        return super().create_task(**kw)

    def get(self, path, params=None):
        data = super().get(path, params)
        if isinstance(data, dict) and data.get("assignees"):
            data["assignees"] = [{**a, "id": a["user"]["id"] * 10} for a in data["assignees"]]
        return data

    def post(self, path, body=None):
        tid = int(path.strip("/").split("/")[1])
        if "/assignees/" in path:
            for c in self.created:
                if c["id"] == tid:
                    c["kw"]["assignee_ids"] = [*c["kw"]["assignee_ids"], body["user_id"]]
            return {}
        return super().post(path, body)

    def request(self, method, path, params=None, body=None):
        parts = path.strip("/").split("/")
        tid, aid = int(parts[1]), int(parts[3])
        for c in self.created:
            if c["id"] == tid:
                c["kw"]["assignee_ids"] = [u for u in c["kw"]["assignee_ids"] if u * 10 != aid]
        return {}


class OwnerTests(Base):
    def setUp(self):
        super().setUp()
        self.fake = OwnerPrbc()
        self.said_tg = TgUser.objects.create(tg_id=51, name="Said Abror", username="StargroupSaid")
        self.said = Member.objects.create(name="Saidabror", role="Operator", telegram="StargroupSaid")
        Person.objects.create(prbc_user=51, full_name="Said Abror", name_key="said abror", in_roster=True, tg_user=self.said_tg,
                              member=self.said)
        self.it_tg = TgUser.objects.create(tg_id=168, name="STAR GROUP | IT SUPPORT", username="IT_StarGroup")

    def staff_reply(self, q, user):
        return Message.objects.create(bot=self.bot, group=self.group, chat_id=-300, message_id=9000 + Message.objects.count(),
                                      kind=Message.STAFF, question=q, user=user, text="ko'ryapman")

    def test_test_group_opens_no_task(self):
        Group.objects.filter(pk=self.group.pk).update(creates_tasks=False)
        self.group.refresh_from_db()
        q = self.question("Klient chiqmayapti")
        self.assertFalse(st_tasks.decide_task(q, Decision("", None, 0, "", True, []))[0])
        self.assertEqual(control.untasked().count(), 0)

    def test_owner_order(self):
        q = self.question("Aksiya ishlamayapti")
        st = SupportTask(message=q, assignee="")
        self.assertEqual(control.pick_assignees(self.conn, st, q), ([167], "standart ijrochi"))
        other = self.question("boshqa savol")
        self.staff_reply(other, self.said_tg)  # Said shu guruhda javob beradi
        self.staff_reply(other, self.it_tg)
        self.staff_reply(other, self.it_tg)  # umumiy akkaunt — hisobga olinmaydi
        self.assertEqual(control.pick_assignees(self.conn, st, q)[0], [51])
        Connection.objects.update(group_assignees={str(self.group.pk): 49})
        self.conn.refresh_from_db()
        self.assertEqual(control.pick_assignees(self.conn, st, q), ([49], "guruh ijrochisi (HEINZ ROP)"))
        Settings.objects.update(category_owners={"promo": self.said.pk})
        Message.objects.filter(pk=q.pk).update(category="promo")
        q.refresh_from_db()
        self.assertEqual(control.pick_assignees(self.conn, st, q)[0], [51])  # toifa mas'uli guruh sozlamasidan ustun
        self.staff_reply(q, self.said_tg)
        self.assertEqual(control.pick_assignees(self.conn, st, q)[1], "savolga javob yozgan: Said Abror")

    def test_group_project_with_fallback_and_reassign_on_reply(self):
        Connection.objects.update(group_projects={str(self.group.pk): 45})
        self.conn.refresh_from_db()
        self.fake.refuse_project = 45
        q = self.question("Zakaz o'tmayapti")
        t = self.open_task(q)
        self.assertEqual(self.fake.created[-1]["kw"]["project"], 15)  # 45 ga ruxsat yo'q — standart loyiha
        self.assertIn("Ijrochi tanlandi: standart ijrochi", self.fake.created[-1]["kw"]["description"])
        self.staff_reply(q, self.said_tg)
        control.push_status(self.conn, self.fake)
        t.refresh_from_db()
        self.assertEqual([p["id"] for p in t.people if p["role"] == "assignee"], [51])  # javob yozgan Said — ijrochi
        self.assertEqual(t.status_category, "in_progress")
        self.assertTrue(any("Said Abror — savolga u javob yozdi" in c[1] for c in self.fake.comments))

    def test_group_table_api(self):
        api = APIClient()
        api.force_authenticate(User.objects.create_superuser("adm2", "b@x.uz", "x"))
        r = api.patch("/api/prbc/group-projects/", {f"tasks:{self.group.pk}": False, f"owner:{self.group.pk}": 51},
                      format="json").json()
        row = next(g for g in r["groups"] if g["id"] == self.group.pk)
        self.assertEqual((row["creates_tasks"], row["owner"], row["owner_name"]), (False, 51, "Said Abror"))


class OldGroupAndDocsTests(Base):
    def test_old_redirected_group_opens_no_task(self):
        new = Group.objects.create(bot=self.bot, chat_id=-301, title="HEINZ ROP (yangi)")
        Group.objects.filter(pk=self.group.pk).update(redirect_to=new)
        self.group.refresh_from_db()
        q = self.question("Klient chiqmayapti")
        self.assertFalse(st_tasks.decide_task(q, Decision("", None, 0, "", True, []))[0])
        self.assertEqual(control.untasked().count(), 0)

    def test_manual_chapters_api(self):
        api = APIClient()
        api.force_authenticate(User.objects.create_superuser("adm3", "c@x.uz", "x"))
        rows = api.get("/api/docs/").json()
        slugs = [r["slug"] for r in rows]
        for s in ("umumiy", "support-bot", "prbc", "inventarizatsiya", "zona", "texnik", "ozgarishlar"):
            self.assertIn(s, slugs)
        doc = api.get("/api/docs/prbc/").json()
        self.assertTrue(doc["title"].startswith("PRBC"))
        self.assertIn("Ijrochi: vazifa kimga tegishli", doc["text"])
        hits = api.get("/api/docs/", {"q": "VAZIFALAR"}).json()
        self.assertTrue(any(r["slug"] == "prbc" and r["hits"] > 0 for r in hits))
        self.assertEqual(api.get("/api/docs/yoq/").status_code, 404)
        self.assertEqual(APIClient().get("/api/docs/").status_code, 401)

    def test_control_has_stats(self):
        self.open_task(self.question())
        api = APIClient()
        api.force_authenticate(User.objects.create_superuser("adm4", "d@x.uz", "x"))
        r = api.get("/api/prbc/control/").json()
        self.assertEqual(r["by_assignee"][0]["open"], 1)
        self.assertEqual(r["by_group"][0]["name"], "HEINZ ROP")
        self.assertIn("unlinked", r["people"])
