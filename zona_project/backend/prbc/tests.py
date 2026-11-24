"""PRBC integratsiyasi testlari — soxta PRBC (javob shakllari prbc.uz'dagi haqiqiy javoblardan olingan)."""
import io
import json
import urllib.error
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from zona.crypto import encrypt

from . import people, tasks
from .client import AuthError, Client
from .models import Change, Connection, Person, Task

TODAY = timezone.localdate()


def lifecycle(task_id, kind, name, position, tab, day, status="new", updated=None):
    title = f"{'Yangi xodim' if kind == 'hire' else 'Ishdan bo' + chr(39) + 'shash'}: {name} — {position}"
    key = "Ishga kirish sanasi" if kind == "hire" else "Oxirgi ish kuni"
    desc = (f"Xodim ishdan bo'shatildi.\n\nXodim: {name}\nLavozim: {position}\nBo'lim: 7. 3 Фергана Проект BIC\n"
            f"Korxona: \"Star Distribution\" Mchj\nTabel raqami: {tab}\nBandlik: Asosiy ish joyi\n{key}: {day:%d.%m.%Y}\n")
    upd = (updated or timezone.now()).isoformat()
    item = {"id": task_id, "code": f"TASK-{task_id}", "title": title, "updated_at": upd,
            "status": {"id": 1, "name": status.title(), "category": status}, "project": {"id": 15, "name": "IT"},
            "primary_assignee": {"id": 48, "full_name": "IT xodimi"}, "due_at": upd}
    return item, {**item, "description": desc, "created_at": upd}


class FakePrbc:
    """Client o'rnini bosadi: get/post/pages/comment/create_task."""

    def __init__(self, roster=(), tasks_=(), hr=None):
        self.roster, self.tasks, self.hr = list(roster), list(tasks_), hr
        self.comments, self.created, self.task_status = [], [], {}
        self.watchers_added, self.checklists, self.ignore_watchers = {}, [], False

    def get(self, path, params=None):
        from .client import PrbcError
        if path == "/tasks/assignable-users/":
            return self.roster
        if path == "/hr/employees/":
            if self.hr is None:
                raise PrbcError("Ruxsat yo'q", 403)
            return {"results": self.hr}
        if path.startswith("/tasks/") and path.rstrip("/").split("/")[-1].isdigit():
            tid = int(path.rstrip("/").split("/")[-1])
            for _, full in self.tasks:
                if full["id"] == tid:
                    return full
            for c in self.created:
                if c["id"] == tid:
                    kw = c["kw"]
                    people_ = [{"user": {"id": u, "full_name": f"User {u}"}, "role": "assignee"} for u in kw.get("assignee_ids") or []]
                    people_ += [{"user": {"id": u, "full_name": f"User {u}"}, "role": "observer"}
                                for u in [*(kw.get("watcher_ids") or []), *self.watchers_added.get(tid, [])]]
                    st = self.task_status.get(tid, {"name": "New", "category": "new"})
                    return {**c, "status": st, "assignees": people_, "checklists": self.checklists,
                            "completed_at": timezone.now().isoformat() if st["category"] == "done" else None,
                            "due_at": (timezone.now() + timedelta(hours=1)).isoformat(), "spent_minutes": 45}
        if path.endswith("/worklog/"):
            return {"team": {"minutes": 45}, "entries": [{"user": {"full_name": "User 51"}, "minutes": 45, "note": "almashtirildi"}]}
        raise PrbcError("topilmadi", 404)

    def post(self, path, body=None):
        tid = int(path.strip("/").split("/")[1])
        self.watchers_added.setdefault(tid, []).append(body["user_id"])
        return {}

    def pages(self, path, params=None, max_pages=200, stop=None):
        if path.endswith("/activity/"):
            yield {"verb": "status_changed", "actor": {"id": 51, "full_name": "Said Abror"},
                   "metadata": {"to": "Done", "from": "New", "to_category": "done"}, "created_at": timezone.now().isoformat()}
            yield {"verb": "comment_added", "actor": {"id": 51, "full_name": "Said Abror"},
                   "metadata": {"excerpt": "Kartrij almashtirildi"}, "created_at": timezone.now().isoformat()}
            return
        if path == "/task-comments/":
            yield {"task": 1, "body": "boshqa vazifa izohi", "author": {"full_name": "X"}}
            return
        prefix = (params or {}).get("search", "")
        for item, _ in sorted(self.tasks, key=lambda x: x[0]["updated_at"], reverse=True):
            if item["title"].startswith(prefix[:5]):
                if stop and stop(item):
                    return
                yield item

    def comment(self, task_id, text):
        self.comments.append((task_id, text))

    def profile(self):
        return getattr(self, "me", {})

    def create_task(self, **kw):
        tid = 9000 + len(self.created)
        if self.ignore_watchers:
            kw = {**kw, "watcher_ids": []}
        data = {"id": tid, "code": f"TASK-{tid}", "title": kw["title"], "status": {"name": "New", "category": "new"},
                "project": {"id": kw.get("project") or 15, "name": "IT"}, "updated_at": timezone.now().isoformat(), **{"kw": kw}}
        self.created.append(data)
        return data


class ParsingTests(TestCase):
    def test_parse_lifecycle_real_format(self):
        _, full = lifecycle(3300, "leave", "KATTABEKOV XASAN KABULOVICH", "Торговый представитель", "0000-00446", TODAY)
        info = people.parse_lifecycle(full["title"], full["description"])
        self.assertEqual(info["kind"], "leave")
        self.assertEqual(info["name"], "KATTABEKOV XASAN KABULOVICH")
        self.assertEqual(info["tab_number"], "0000-00446")
        self.assertEqual(info["date"], TODAY)
        self.assertEqual(info["company"], "Star Distribution\" Mchj".strip('"') or info["company"])
        self.assertIsNone(people.parse_lifecycle("Pochta uchun service larni gaplashish kerak"))

    def test_names_latin_cyrillic_and_patronymic(self):
        self.assertTrue(people.same_person("NE’MATOV JAHONGIR MO‘MINJON O‘G‘LI", "Jahongir Ne'matov"))
        self.assertTrue(people.same_person("KATTABEKOV XASAN KABULOVICH", "Каттабеков Хасан"))
        self.assertFalse(people.same_person("KATTABEKOV XASAN", "KATTABEKOV ALISHER"))
        self.assertEqual(people.phone9("+998 (90) 123-45-67"), "901234567")


class ClientTests(TestCase):
    def setUp(self):
        self.conn = Connection.get()
        self.conn.phone, self.conn.password_enc = "998901234567", encrypt("sir")
        self.conn.save()

    def _opener(self, responses):
        calls = []

        def opener(req, timeout=None):
            calls.append((req.get_method(), req.full_url, req.headers.get("Authorization"), req.data))
            status, body = responses.pop(0)
            raw = json.dumps(body).encode()
            if status >= 400:
                raise urllib.error.HTTPError(req.full_url, status, "err", {}, io.BytesIO(raw))
            r = io.BytesIO(raw)
            r.status = status
            r.__enter__ = lambda *a: r
            return type("R", (), {"__enter__": lambda s: r, "__exit__": lambda s, *a: None})()
        return opener, calls

    def test_login_then_retry_on_401(self):
        import base64
        exp = int((timezone.now() + timedelta(minutes=30)).timestamp())
        tok = "x." + base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=") + ".y"
        opener, calls = self._opener([(200, {"access": tok, "refresh": "R1"}), (401, {"detail": "expired"}),
                                      (200, {"access": tok, "refresh": "R2"}), (200, {"id": 1})])
        c = Client(self.conn, opener=opener)
        self.assertEqual(c.get("/auth/profile/"), {"id": 1})
        self.assertIn(b'"phone": "998901234567"', calls[0][3])
        self.assertEqual(calls[1][2], f"Bearer {tok}")
        self.assertEqual(calls[-1][1], "https://prbc.uz/api/v1/auth/profile/")
        self.conn.refresh_from_db()
        self.assertIsNotNone(self.conn.access_until)

    def test_bad_password(self):
        opener, _ = self._opener([(400, {"detail": "Telefon yoki parol noto'g'ri"})])
        with self.assertRaises(AuthError) as e:
            Client(self.conn, opener=opener).login()
        self.assertIn("parol noto'g'ri", str(e.exception))


class SyncTests(TestCase):
    def setUp(self):
        from inventory.models import Branch, DeviceType, Employee, Item
        from zona.models import Member, StaffPerson, StaffProject as Project
        self.conn = Connection.get()
        self.conn.enabled, self.conn.phone, self.conn.password_enc = True, "1", encrypt("x")
        self.conn.save()
        proj = Project.objects.create(name="BIC Farg'ona")
        self.sp = StaffPerson.objects.create(project=proj, name="Kattabekov Xasan", territory="Farg'ona-3",
                                             phone="+998 90 111 22 33", telegram="xasan_k")
        self.member = Member.objects.create(name="Ne'matov Jahongir", role="IT", telegram="jahongir_it")
        branch = Branch.objects.filter(name="Farg'ona").first() or Branch.objects.create(code="FRG-T", name="Farg'ona")
        self.emp = Employee.objects.create(full_name="KATTABEKOV XASAN", position="TP", branch=branch, is_active=True)
        dt, _ = DeviceType.objects.get_or_create(name="Planshet")
        Item.objects.create(inv_number="INV-7", branch=branch, device_type=dt, brand="Samsung", model="Tab A",
                            serial="SN1", employee=self.emp)
        self.roster = [{"id": 48, "full_name": "NE’MATOV JAHONGIR MO‘MINJON O‘G‘LI", "position": "IT"},
                       {"id": 700, "full_name": "KATTABEKOV XASAN KABULOVICH", "position": "Торговый представитель"}]

    def test_leave_task_vacates_seat_deactivates_employee_and_comments_devices(self):
        fake = FakePrbc(self.roster, [lifecycle(3300, "leave", "KATTABEKOV XASAN KABULOVICH", "Торговый представитель",
                                                "0000-00446", TODAY - timedelta(days=1))])
        run = people.run(self.conn, fake)
        self.assertTrue(run.ok, run.error)
        p = Person.objects.get(prbc_user=700)
        self.assertEqual((p.status, p.tab_number, p.leave_task), (Person.LEFT, "0000-00446", "TASK-3300"))
        self.assertEqual(p.staff_person_id, self.sp.pk)
        self.assertTrue(p.left_applied)
        self.sp.refresh_from_db()
        self.assertTrue(self.sp.is_vacancy)
        self.assertEqual(self.sp.history[0]["name"], "Kattabekov Xasan")
        self.emp.refresh_from_db()
        self.assertFalse(self.emp.is_active)
        self.assertEqual(len(fake.comments), 1)
        self.assertIn("INV-7", fake.comments[0][1])
        # ikkinchi sinxronlash hech narsani takrorlamaydi
        people.run(self.conn, fake)
        self.assertEqual(len(fake.comments), 1)
        self.assertEqual(Person.objects.filter(full_name__icontains="KATTABEKOV").count(), 1)
        # qaytarish
        people.revert_left(p, "admin")
        self.sp.refresh_from_db()
        self.emp.refresh_from_db()
        self.assertEqual((self.sp.is_vacancy, self.sp.name, self.sp.phone), (False, "Kattabekov Xasan", "+998 90 111 22 33"))
        self.assertTrue(self.emp.is_active)

    def test_future_last_day_is_leaving_not_applied(self):
        fake = FakePrbc(self.roster, [lifecycle(3301, "leave", "KATTABEKOV XASAN KABULOVICH", "TP", "0000-00446",
                                                TODAY + timedelta(days=5))])
        people.run(self.conn, fake)
        p = Person.objects.get(prbc_user=700)
        self.assertEqual(p.status, Person.LEAVING)
        self.assertFalse(p.left_applied)
        self.sp.refresh_from_db()
        self.assertFalse(self.sp.is_vacancy)

    def test_cancelled_in_1c_returns_person(self):
        old = timezone.now() - timedelta(hours=1)
        fake = FakePrbc(self.roster, [lifecycle(3302, "leave", "KATTABEKOV XASAN KABULOVICH", "TP", "T1", TODAY, updated=old)])
        self.conn.auto_left = False
        self.conn.save()
        people.run(self.conn, fake)
        self.assertEqual(Person.objects.get(prbc_user=700).status, Person.LEFT)
        fake.tasks = [lifecycle(3302, "leave", "KATTABEKOV XASAN KABULOVICH", "TP", "T1", TODAY, status="cancelled")]
        people.run(self.conn, fake)
        p = Person.objects.get(prbc_user=700)
        self.assertEqual(p.status, Person.ACTIVE)
        self.assertTrue(Change.objects.filter(person=p, kind=Change.RETURNED).exists())

    def test_hire_creates_person_and_rehire_after_leave(self):
        fake = FakePrbc([], [lifecycle(3297, "hire", "MUXAMEDJANOV RUSTAM MUXRUM O‘G‘LI", "Водитель экспедитор", "0000-00206", TODAY)])
        people.run(self.conn, fake)
        p = Person.objects.get(tab_number="0000-00206")
        self.assertEqual((p.status, p.hired_on, p.hire_task), (Person.ACTIVE, TODAY, "TASK-3297"))

    def test_ambiguous_names_not_linked_manual_link_kept(self):
        from zona.models import StaffPerson, StaffProject as Project
        StaffPerson.objects.create(project=Project.objects.first(), name="Kattabekov Xasan", territory="Farg'ona-4")
        people.run(self.conn, FakePrbc(self.roster, []))
        p = Person.objects.get(prbc_user=700)
        self.assertIsNone(p.staff_person_id)  # ikki «Kattabekov Xasan» — taxmin qilinmaydi
        p.staff_person, p.link_manual = self.sp, True
        p.save()
        people.run(self.conn, FakePrbc(self.roster, []))
        self.assertEqual(Person.objects.get(prbc_user=700).staff_person_id, self.sp.pk)

    def test_hr_inactive_marks_left(self):
        fake = FakePrbc(self.roster, [], hr=[{"id": 5, "full_name": "KATTABEKOV XASAN KABULOVICH", "is_active": False}])
        people.run(self.conn, fake)
        self.assertEqual(Person.objects.get(prbc_user=700).status, Person.LEFT)

    def test_closed_sources_do_not_fail(self):
        class Closed(FakePrbc):
            def get(self, path, params=None):
                from .client import PrbcError
                raise PrbcError("403", 403)

            def pages(self, *a, **k):
                from .client import PrbcError
                raise PrbcError("403", 403)
                yield  # noqa
        run = people.run(self.conn, Closed())
        self.assertTrue(run.ok)
        self.assertIn("yopiq", run.stats["sources"]["assignable"])

    def test_login_failure_fails_the_run(self):
        from .client import LoginError

        class NoLogin(FakePrbc):
            def get(self, path, params=None):
                raise LoginError("PRBC'ga kirib bo'lmadi: parol noto'g'ri", 400)
        run = people.run(self.conn, NoLogin())
        self.assertFalse(run.ok)
        self.assertIn("parol", run.error)
        self.conn.refresh_from_db()
        self.assertIn("parol", self.conn.last_error)


class TaskTests(TestCase):
    def setUp(self):
        from zona.models import Member
        self.conn = Connection.get()
        self.conn.task_project, self.conn.task_default_assignees = 15, [48]
        self.conn.save()
        m = Member.objects.create(name="Said Abror", role="IT", telegram="StargroupSaid")
        Person.objects.create(prbc_user=51, full_name="Said Abror", name_key="abror said", member=m, in_roster=True)

    def test_support_api_mode_creates_task_with_resolved_assignee_and_polls(self):
        from support.models import Settings, SupportTask
        s = Settings.load()
        s.task_mode = "api"
        s.save()
        st = SupportTask.objects.create(assignee="StargroupSaid", title="Printer ishlamayapti",
                                        text="/vazifa @StargroupSaid Printer\n\nSavol: printer ishlamayapti", status=SupportTask.QUEUED)
        fake = FakePrbc()
        self.assertEqual(tasks.process_support_queue(self.conn, fake), 1)
        kw = fake.created[0]["kw"]
        self.assertEqual((kw["assignee_ids"], kw["project"]), ([51], 15))
        self.assertNotIn("/vazifa", kw["description"])
        st.refresh_from_db()
        self.assertEqual(st.status, SupportTask.SENT)
        self.assertIn("TASK-9000", st.reply)
        fake.task_status[9000] = {"name": "Done", "category": "done"}
        self.assertEqual(tasks.poll(self.conn, fake), 1)
        self.assertEqual(Task.objects.get(prbc_id=9000).status_category, "done")
        st.refresh_from_db()
        self.assertIn("Done", st.reply)

    def test_unknown_assignee_falls_back_to_default(self):
        t = tasks.create(title="Test", assignee_ids=[], conn=self.conn, client=FakePrbc())
        self.assertEqual(t.code, "TASK-9000")

    def test_api_admin_only(self):
        api = APIClient()
        viewer = User.objects.create_user("v", password="x")
        api.force_authenticate(viewer)
        self.assertEqual(api.get("/api/prbc/overview/").status_code, 403)
        admin = User.objects.create_superuser("a", password="x")
        api.force_authenticate(admin)
        r = api.patch("/api/prbc/connection/", {"phone": "998901234567", "password": "sir", "sync_minutes": 1,
                                                "enabled": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["password_set"])
        self.assertNotIn("sir", json.dumps(r.json()))
        self.assertEqual(r.json()["sync_minutes"], 5)
        self.assertEqual(api.post("/api/prbc/sync/").status_code, 200)
        self.assertTrue(Connection.get().sync_requested)
        self.assertEqual(api.get("/api/prbc/overview/").status_code, 200)


class ControlTests(TestCase):
    """Agent kodi, kuzatuvchi (Kamoliddin aka), bajarilganda hisobot va savolni yopish."""

    def setUp(self):
        from support.models import Bot, TgUser
        from zona.models import Member, StaffPerson, StaffProject
        self.conn = Connection.get()
        self.conn.task_project, self.conn.task_default_assignees = 15, [48]
        self.conn.save()
        m = Member.objects.create(name="Said Abror", role="IT", telegram="StargroupSaid")
        Person.objects.create(prbc_user=51, full_name="Said Abror", name_key="abror said", member=m, in_roster=True)
        proj = StaffProject.objects.create(name="Heinz")
        sv = StaffPerson.objects.create(project=proj, name="Aliyev Vali", role="SVR", territory="SVR Tash 1", phone="+998901112233")
        self.sp = StaffPerson.objects.create(project=proj, name="Karimov Anvar", role="TP", territory="SR2 Tashkent",
                                             city="Ташкент", phone="+998907776655", manager=sv)
        self.bot = Bot.objects.create(name="S", token_enc=encrypt("1:x"))
        self.user = TgUser.objects.create(tg_id=777, name="Anvar", username="anvar_tp", staff_person=self.sp)

    def _question(self):
        from support.models import Message
        return Message.objects.create(bot=self.bot, chat_id=-100, message_id=5, user=self.user, kind="question",
                                      text="Planshetda zakaz o'tmayapti", status=Message.ESCALATED)

    def test_default_watcher_is_kamoliddin(self):
        self.assertEqual(Connection.get().task_watchers, [2])

    def test_agent_card_in_task_text_and_dm(self):
        from support import agent
        from support.models import TgUser
        from support.tasks import build_text, dm_text
        q = self._question()
        text, _ = build_text(q, "Zakaz o'tmayapti", "StargroupSaid")
        self.assertIn("Agent kodi: SR2 Tashkent", text)
        self.assertIn("Supervayzer: Aliyev Vali (+998901112233)", text)
        self.assertIn("Loyiha: Heinz", text)
        self.assertIn("SR2 Tashkent", dm_text(q, "Zakaz", "StargroupSaid", ""))
        self.assertIn("SR2 Tashkent · Heinz", agent.short(self.user))
        # kontaktga bog'lanmagan, lekin ismida kod bor
        self.assertEqual(agent.info(TgUser.objects.create(tg_id=778, name="Toshkent K1"))["code"], "Toshkent K1")
        self.assertIsNone(agent.info(TgUser.objects.create(tg_id=779, name="Dilshod")))

    def test_agent_code_synced_from_seat_and_manual_override(self):
        p = Person.objects.create(prbc_user=700, full_name="KARIMOV ANVAR", staff_person=self.sp)
        people.sync_codes({})
        p.refresh_from_db()
        self.assertEqual(p.agent_code, "SR2 Tashkent")
        api = APIClient()
        api.force_authenticate(User.objects.create_superuser("a", password="x"))
        r = api.patch(f"/api/prbc/people/{p.pk}/", {"agent_code": "Toshkent K1"}, format="json")
        self.assertEqual((r.json()["agent_code"], r.json()["code_manual"]), ("Toshkent K1", True))
        from support import agent
        self.assertEqual(agent.info(self.user)["code"], "Toshkent K1")  # PRBC'dagi kod ustun

    def test_task_has_assignee_and_observer_then_done_fills_report_and_closes_question(self):
        from support.models import Message, Settings, SupportTask
        from support.resolution import YES
        s = Settings.load()
        s.task_mode = "api"
        s.save()
        q = self._question()
        dup = Message.objects.create(bot=self.bot, chat_id=-100, message_id=6, user=self.user, kind="question", text="yana")
        st = SupportTask.objects.create(message=q, assignee="StargroupSaid", title="Zakaz", text="Savol: zakaz",
                                        duplicates=[dup.pk], status=SupportTask.QUEUED)
        fake = FakePrbc()
        fake.ignore_watchers = True  # PRBC watcher_ids'ni qabul qilmasa — alohida qo'shiladi
        fake.checklists = [{"title": "Tekshiruv", "items": [{"text": "Planshet", "is_done": True}, {"text": "1C", "is_done": False}]}]
        tasks.process_support_queue(self.conn, fake)
        self.assertEqual(fake.watchers_added, {9000: [2]})
        t = Task.objects.get(prbc_id=9000)
        self.assertEqual(t.assignee, "User 51")
        self.assertEqual(t.watchers, "User 2")
        st.refresh_from_db()
        self.assertIn("Mas'ul: User 51", st.reply)
        self.assertIn("Kuzatuvchi: User 2", st.reply)

        fake.task_status[9000] = {"name": "Done", "category": "done"}
        self.assertEqual(tasks.poll(self.conn, fake), 1)
        t.refresh_from_db()
        self.assertEqual(t.completed_by, "Said Abror")
        self.assertEqual(t.spent_minutes, 45)
        self.assertTrue(t.report["on_time"])
        self.assertEqual(t.report["comments"][0]["text"], "Kartrij almashtirildi")  # boshqa vazifa izohi olinmadi
        self.assertEqual(t.report["checklist"][0]["done"], 1)
        self.assertEqual(t.report["worklog"]["entries"][0]["note"], "almashtirildi")
        st.refresh_from_db()
        self.assertEqual(st.status, SupportTask.DONE)
        self.assertIn("yopdi: Said Abror", st.reply)
        for m in (q, dup):
            m.refresh_from_db()
            self.assertEqual(m.resolution, YES)
            self.assertIn("TASK-9000", m.resolved_by)
        # qayta so'rov hisobotni takrorlamaydi
        self.assertEqual(tasks.poll(self.conn, fake), 0)
        self.assertEqual(Change.objects.filter(text__startswith="Bajarildi").count(), 1)

        api = APIClient()
        api.force_authenticate(User.objects.create_superuser("a", password="x"))
        d = api.get(f"/api/prbc/tasks/{t.pk}/").json()
        self.assertEqual((d["question"], d["report"]["completed_by"]), (q.pk, "Said Abror"))
        st_ = api.get("/api/prbc/tasks/stats/").json()
        self.assertEqual(st_["total"]["done"], 1)
        self.assertEqual(st_["rows"][0]["name"], "User 51")

    def test_close_on_done_off_keeps_question_open(self):
        from support.models import SupportTask
        from support.resolution import YES
        self.conn.close_on_done = False
        self.conn.save()
        q = self._question()
        st = SupportTask.objects.create(message=q, title="Zakaz", status=SupportTask.SENT)
        fake = FakePrbc()
        tasks.create(title="Zakaz", assignee_ids=[51], support_task=st, conn=self.conn, client=fake)
        fake.task_status[9000] = {"name": "Done", "category": "done"}
        tasks.poll(self.conn, fake)
        q.refresh_from_db()
        st.refresh_from_db()
        self.assertEqual(st.status, SupportTask.DONE)
        self.assertNotEqual(q.resolution, YES)

    def test_lifecycle_tasks_are_polled_too(self):
        _, full = lifecycle(3300, "leave", "KATTABEKOV XASAN", "TP", "T1", TODAY, status="done")
        full["assignees"] = [{"user": {"id": 48, "full_name": "NE'MATOV JAHONGIR"}, "role": "assignee"},
                             {"user": {"id": 2, "full_name": "ATAQULOV KAMOLIDDIN"}, "role": "observer"}]
        Task.objects.create(prbc_id=3300, code="TASK-3300", title=full["title"], kind=Task.LEAVE, status_category="new")
        tasks.poll(self.conn, FakePrbc(tasks_=[(None, full)]))
        t = Task.objects.get(prbc_id=3300)
        self.assertEqual((t.status_category, t.kind, t.watchers), ("done", Task.LEAVE, "ATAQULOV KAMOLIDDIN"))
        self.assertEqual(t.completed_by, "Said Abror")


class FakeTg:
    """Telegram bot (worker guruhga yozadi va fayl yuklab oladi)."""

    def __init__(self):
        self.sent, self.edited = [], []

    def send(self, chat_id, text, reply_to=None, **kw):
        self.sent.append((chat_id, text, reply_to))
        return {"message_id": 900 + len(self.sent)}

    def edit_text(self, chat_id, message_id, text, **kw):
        self.edited.append((chat_id, message_id, text))

    def download(self, file_id, max_bytes=0):
        return b"tg-bytes-" + file_id.encode()


class AttachPrbc(FakePrbc):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.files = []

    def attach(self, task_id, filename, content, mime=""):
        self.files.append((task_id, filename, content))
        return {"id": len(self.files)}


class SupportFlowTests(TestCase):
    """Bot savoldan PRBC vazifasini o'zi ochadi: fayllar, qo'shimchalar, guruhga "ochildi" / "bajarildi" javobi."""

    def setUp(self):
        import tempfile
        from unittest import mock

        from support.models import Bot, Group, Settings, TgUser
        from zona.models import Member
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict("os.environ", {"ZONA_SUPPORT_MEDIA": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.tg = FakeTg()
        p = mock.patch.object(tasks, "_bot_client", lambda q: self.tg)
        p.start()
        self.addCleanup(p.stop)
        self.conn = Connection.get()
        self.conn.task_project, self.conn.task_default_assignees, self.conn.notify_created = 15, [48], True
        self.conn.save()
        s = Settings.load()
        s.task_mode = "api"
        s.save()
        self.member = Member.objects.create(name="Xusniddin", role="IT operator", telegram="xusniddin_it")
        Person.objects.create(prbc_user=60, full_name="TOSHMATOV XUSNIDDIN", name_key="toshmatov xusniddin", in_roster=True)
        self.bot = Bot.objects.create(name="S", token_enc=encrypt("1:x"))
        self.group = Group.objects.create(bot=self.bot, chat_id=-200, title="ROP Toshkent")
        self.user = TgUser.objects.create(tg_id=881, name="Toshkent K1")

    def _media(self, msg, name, data=b"", file_id=""):
        import os

        from support.models import Media
        path = ""
        if data:
            path = name
            with open(os.path.join(self.tmp.name, path), "wb") as f:
                f.write(data)
        return Media.objects.create(message=msg, kind=Media.PHOTO, path=path, mime="image/jpeg",
                                    tg_file_ids={str(self.bot.pk): file_id} if file_id else {})

    def test_full_flow_files_followups_and_group_reports(self):
        from support.models import Message, SupportTask
        from support.resolution import YES
        q = Message.objects.create(bot=self.bot, group=self.group, chat_id=-200, message_id=10, user=self.user,
                                   kind="question", text="ProTarget ochilmayapti, login xato", status=Message.ESCALATED,
                                   confirm_msg_id=55)
        self._media(q, "a.jpg", b"disk-bytes")
        self._media(q, "", file_id="FILE9")  # serverga saqlanmagan — worker Telegram'dan oladi
        Message.objects.create(bot=self.bot, group=self.group, chat_id=-200, message_id=11, user=self.user,
                               kind=Message.INFO, question=q, text="login: k1_tash")
        st = SupportTask.objects.create(message=q, assignee="xusniddin_it", title="ProTarget", text="Savol: ProTarget",
                                        status=SupportTask.QUEUED)
        fake = AttachPrbc()
        self.assertEqual(tasks.process_support_queue(self.conn, fake), 1)
        kw = fake.created[0]["kw"]
        self.assertEqual(kw["assignee_ids"], [60])  # Xusniddin — zona xodimi ismi PRBC'da yagona
        self.assertEqual(kw["watcher_ids"], [2])  # kuzatuvchi — Kamoliddin aka
        self.assertIn("ProTarget ochilmayapti", kw["title"])
        self.assertIn("login: k1_tash", kw["description"])
        self.assertEqual(sorted(f[2] for f in fake.files), [b"disk-bytes", b"tg-bytes-FILE9"])
        self.assertEqual(fake.comments, [])  # vazifa ochilishidagi qo'shimcha tavsifda — izoh takrorlanmaydi
        st.refresh_from_db()
        self.assertIn("2 ta fayl biriktirildi", st.reply)
        self.assertEqual(len(self.tg.sent), 1)
        self.assertIn("Vazifa ochildi", self.tg.sent[0][1])
        self.assertEqual(self.tg.sent[0][2], 10)  # savolga reply

        # savol egasi keyin yana rasm va izoh yubordi, boshqa savol takror — keyingi tekshiruvda vazifaga o'tadi
        later = Message.objects.create(bot=self.bot, group=self.group, chat_id=-200, message_id=12, user=self.user,
                                       kind=Message.INFO, question=q, text="yana skrin")
        self._media(later, "b.jpg", b"later-bytes")
        dup = Message.objects.create(bot=self.bot, group=self.group, chat_id=-200, message_id=13, user=self.user,
                                     kind="question", text="ProTarget hali ham ochilmayapti")
        SupportTask.objects.filter(pk=st.pk).update(duplicates=[dup.pk])
        tasks.poll(self.conn, fake)
        self.assertEqual(len(fake.files), 3)
        texts = [c[1] for c in fake.comments]
        self.assertTrue(any(c.startswith(tasks.INFO_MARK) and "yana skrin" in c for c in texts))
        self.assertTrue(any(c.startswith("🔁") and "hali ham" in c for c in texts))
        tasks.poll(self.conn, fake)  # takrorlanmaydi
        self.assertEqual((len(fake.files), len(fake.comments)), (3, 2))

        fake.task_status[9000] = {"name": "Done", "category": "done"}
        tasks.poll(self.conn, fake)
        done = self.tg.sent[-1][1]
        self.assertIn("Bajarildi", done)
        self.assertIn("TASK-9000", done)
        self.assertIn("Kartrij almashtirildi", done)
        self.assertIn("Said Abror", done)
        self.assertEqual(self.tg.edited, [(-200, 55, "✅ Rahmat! Savol yopildi.")])  # "hal bo'ldimi?" tugmalari yopildi
        q.refresh_from_db()
        self.assertEqual(q.resolution, YES)
        n = len(self.tg.sent)
        tasks.poll(self.conn, fake)
        self.assertEqual(len(self.tg.sent), n)  # guruhga ikkinchi marta yozilmaydi
        t = Task.objects.get(prbc_id=9000)
        self.assertEqual((t.sync["files"], t.sync["notified"]), (3, ["created", "done"]))

    def test_russian_question_gets_russian_report_and_settings_off(self):
        from support.models import Message, SupportTask
        q = Message.objects.create(bot=self.bot, group=self.group, chat_id=-200, message_id=20, user=self.user,
                                   kind="question", text="Не открывается ProTarget", lang="ru")
        SupportTask.objects.create(message=q, assignee="xusniddin_it", title="ProTarget", status=SupportTask.QUEUED)
        fake = AttachPrbc()
        tasks.process_support_queue(self.conn, fake)
        self.assertIn("Создана задача", self.tg.sent[0][1])
        fake.task_status[9000] = {"name": "Done", "category": "done"}
        tasks.poll(self.conn, fake)
        self.assertIn("Выполнено", self.tg.sent[-1][1])
        # sozlamada o'chirilsa — guruhga yozilmaydi, fayl yuklanmaydi
        self.conn.notify_done = self.conn.notify_created = self.conn.attach_files = False
        self.conn.save()
        q2 = Message.objects.create(bot=self.bot, group=self.group, chat_id=-200, message_id=21, user=self.user,
                                    kind="question", text="Yana")
        self._media(q2, "c.jpg", b"x")
        SupportTask.objects.create(message=q2, assignee="xusniddin_it", title="Yana", status=SupportTask.QUEUED)
        n = len(self.tg.sent)
        tasks.process_support_queue(self.conn, fake)
        fake.task_status[9001] = {"name": "Done", "category": "done"}
        tasks.poll(self.conn, fake)
        self.assertEqual((len(self.tg.sent), fake.files), (n, []))

    def test_assignee_mapping(self):
        self.assertEqual(tasks.assignee_ids_for("@Xusniddin_IT", self.conn), [60])
        self.conn.assignee_map = {"xusniddin_it": 61}
        self.conn.save()
        self.assertEqual(tasks.assignee_ids_for("xusniddin_it", self.conn), [61])  # qo'lda moslash ustun
        self.conn.assignee_map = {}
        self.conn.save()
        Person.objects.create(prbc_user=62, full_name="ALIYEV XUSNIDDIN", name_key="aliyev xusniddin")
        self.assertEqual(tasks.assignee_ids_for("xusniddin_it", self.conn), [])  # ikki xil Xusniddin — taxmin qilinmaydi
        api = APIClient()
        api.force_authenticate(User.objects.create_superuser("a", password="x"))
        r = api.patch("/api/prbc/connection/", {"assignee_map": "xusniddin_it=60, @Said=51, bad=x",
                                                "notify_created": True}, format="json").json()
        self.assertEqual(r["assignee_map"], {"xusniddin_it": 60, "said": 51})
        self.assertEqual(r["named"]["60"], "TOSHMATOV XUSNIDDIN")

    def test_group_stats_and_cancelled(self):
        from support.models import Message, SupportTask
        q = Message.objects.create(bot=self.bot, group=self.group, chat_id=-200, message_id=30, user=self.user,
                                   kind="question", text="x")
        st = SupportTask.objects.create(message=q, title="x", status=SupportTask.SENT)
        Task.objects.create(prbc_id=1, title="a", kind=Task.OURS, status_category="done", support_task=st, assignee="X")
        Task.objects.create(prbc_id=2, title="b", kind=Task.OURS, status_category="cancelled", support_task=st, assignee="X")
        Task.objects.create(prbc_id=3, title="c", kind=Task.OURS, status_category="new", assignee="X",
                            due_at=timezone.now() - timedelta(hours=1))
        api = APIClient()
        api.force_authenticate(User.objects.create_superuser("a", password="x"))
        d = api.get("/api/prbc/tasks/stats/").json()
        self.assertEqual(d["total"]["cancelled"], 1)
        g = {r["name"]: r for r in d["groups"]}
        self.assertEqual((g["ROP Toshkent"]["done"], g["ROP Toshkent"]["cancelled"]), (1, 1))
        self.assertEqual(g["Guruhsiz (panel yoki shaxsiy chat)"]["overdue"], 1)
        self.assertEqual(d["rows"][0]["cancelled"], 1)

    def test_client_upload_is_multipart(self):
        self.conn.phone, self.conn.password_enc = "998901234567", encrypt("sir")
        self.conn.save()
        calls = []

        def opener(req, timeout=None):
            calls.append(req)
            body = {"access": "a.eyJleHAiOjk5OTk5OTk5OTl9.s", "refresh": "r"} if "login" in req.full_url else {"id": 7}
            r = io.BytesIO(json.dumps(body).encode())
            r.status = 200
            return type("R", (), {"__enter__": lambda s: r, "__exit__": lambda s, *a: None})()
        out = Client(self.conn, opener=opener).attach(9000, 'skrin"1.jpg', b"\x89PNG", "image/png")
        self.assertEqual(out, {"id": 7})
        req = calls[-1]
        self.assertTrue(req.full_url.endswith("/api/v1/tasks/9000/attachments/"))
        self.assertIn("multipart/form-data; boundary=", req.headers["Content-type"])
        self.assertIn(b'name="file"; filename="skrin1.jpg"', req.data)
        self.assertIn(b"\x89PNG", req.data)


class SelfWatcherAndSyncTests(TestCase):
    def test_connected_account_owner_is_observer_too(self):
        conn = Connection.get()
        conn.task_default_assignees = [48]
        conn.save()
        Person.objects.create(prbc_user=495, full_name="TO‘YCHIYEV ABDULBOSIT ORIBJON O‘G‘LI",
                              name_key=people.name_key("TO‘YCHIYEV ABDULBOSIT ORIBJON O‘G‘LI"))
        fake = FakePrbc()
        fake.me = {"id": 7, "full_name": "TO‘YCHIYEV ABDULBOSIT ORIBJON O‘G‘LI"}  # profil id'si boshqa — ism bo'yicha
        tasks.create(title="x", conn=conn, client=fake)
        self.assertEqual(fake.created[0]["kw"]["watcher_ids"], [2, 495])
        self.assertEqual(Connection.get().me["full_name"], "TO‘YCHIYEV ABDULBOSIT ORIBJON O‘G‘LI")
        tasks.create(title="y", assignee_ids=[495], conn=conn, client=fake)  # o'zi ijrochi — kuzatuvchi emas
        self.assertEqual(fake.created[1]["kw"]["watcher_ids"], [2])
        conn.watch_self = False
        conn.save()
        tasks.create(title="z", conn=conn, client=fake)
        self.assertEqual(fake.created[2]["kw"]["watcher_ids"], [2])

    def test_sync_says_exactly_what_is_missing(self):
        api = APIClient()
        api.force_authenticate(User.objects.create_superuser("a", password="x"))
        self.assertIn("telefon", api.post("/api/prbc/sync/").json()["detail"])
        api.patch("/api/prbc/connection/", {"phone": "998901234567", "password": "sir"}, format="json")
        r = api.post("/api/prbc/sync/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("«Ulanish yoqilgan»", r.json()["detail"])
        self.assertFalse(Connection.get().sync_requested)
        Connection.objects.filter(pk=1).update(last_error="PRBC ulanishi yoqilmagan yoki parol kiritilmagan.")
        c = api.patch("/api/prbc/connection/", {"enabled": True}, format="json").json()
        self.assertEqual((c["last_error"], c["ready"]), ("", True))  # eski xato tozalandi
        self.assertEqual(api.post("/api/prbc/sync/").status_code, 200)
        self.assertTrue(Connection.get().sync_requested)
