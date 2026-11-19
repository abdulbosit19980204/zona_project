"""Tezlik va aniqlik: imlo xatolari, hisobot/forward filtri, savol beruvchi va supervayzerni belgilash, parallel ishlov."""
import time

from django.core.management import call_command

from zona.crypto import encrypt
from zona.models import StaffPerson, StaffProject
from zona.tests import Base

from . import engine
from .models import MODE_LIVE, Bot, Entry, Message, TgUser
from .runner import Handler
from .tests import FakeClient, group_msg


class ImmediateExecutor:
    def __init__(self):
        self.calls = 0

    def submit(self, fn, *args):
        self.calls += 1
        fn(*args)


class TypoAndFilterTests(Base):
    def setUp(self):
        call_command("support_setup", verbosity=0)
        call_command("support_import_kb", verbosity=0)
        Entry.objects.update(status=Entry.APPROVED)
        Entry.objects.get_or_create(kind=Entry.FAQ, title="Klient bazada bor, lekin agentda ko'rinmayapti",
                                    defaults={"answer": "Supervayzer marshrutga qo'shadi.", "status": Entry.APPROVED,
                                              "questions": ["klient agentda ko'rinmayapti", "klientim menda chiqmayapti"]})

    def test_misspelled_questions_from_real_group_are_found(self):
        d = engine.decide("Kilentlarim korinmayapti", "uz")
        self.assertTrue(d.entry and "ko'rinmayapti" in d.entry.title, (d.stage, d.confidence, d.entry))
        d = engine.decide("Prbc da kilent qoshish chiqmayapti", "uz")
        self.assertEqual(d.stage, "template")
        self.assertIn("klient", d.entry.title.lower())

    def test_reports_and_forwards_are_not_questions(self):
        self.assertFalse(engine.is_question("✅ Торговые точки добавлены в маршрут: \"X\"\nAgent: Y\nKun: 3"))
        self.assertFalse(engine.is_question("🌅 Kun boshi — 19.11.2026\nMDLZ ROP\n\n📅 Bugun"))
        self.assertFalse(engine.is_question("Klient ko'rinmayapti nima qilay", forwarded=True))
        self.assertTrue(engine.is_question("Kilentlarim korinmayapti"))
        self.assertTrue(engine.is_question("✅ tochka qo'shdim lekin ko'rinmayapti?"))

    def test_decide_is_fast_with_cached_index(self):
        engine.decide("klient agentda ko'rinmayapti", "uz")  # kesh qiziydi
        t0 = time.perf_counter()
        for _ in range(5):
            engine.decide("plan qolib ketyapti nima qilay", "uz")
        self.assertLess((time.perf_counter() - t0) / 5, 1.0)


class MentionTests(Base):
    def setUp(self):
        call_command("support_setup", verbosity=0)
        Entry.objects.update(status=Entry.APPROVED)
        proj = StaffProject.objects.create(name="Heinz")
        self.svr = StaffPerson.objects.create(project=proj, name="Valiyev Anvar Karimovich", role="SVR")
        self.tp = StaffPerson.objects.create(project=proj, name="Toshmatov Bekzod Ali o'g'li", role="TP", manager=self.svr)
        self.bot = Bot.objects.create(name="S", token_enc=encrypt("1:x"), mode=MODE_LIVE, admin_chat_id=555)
        self.tg = FakeClient()

    def test_asker_is_mentioned_and_supervisor_only_when_needed(self):
        h = Handler(self.bot, self.tg)
        # supervayzer ham guruhda yozgan — ID orqali taniladi
        engine.identify(500, "", "Anvar Valiyev")
        msg = group_msg(1, 10, "Prbc da kilent qoshish chiqmayapti", username="")
        msg["message"]["from"]["first_name"], msg["message"]["from"]["last_name"] = "Bekzod", "Toshmatov"
        h.handle(msg)
        u = TgUser.objects.get(tg_id=10)
        self.assertEqual((u.staff_person, u.staff_link), (self.tp, "auto"))
        text = self.tg.sent[-1]["text"]
        self.assertTrue(text.startswith('<a href="tg://user?id=10">'))          # savol beruvchi belgilandi
        self.assertIn('tg://user?id=500', text)                                 # supervayzeri (javob supervayzerni talab qiladi)
        h.handle(group_msg(2, 10, "Nuqta отправлена на модерацию, qachon tasdiqlanadi?"))
        self.assertNotIn("Supervayzeringiz", self.tg.sent[-1]["text"])       # moderatsiya — supervayzer kerak emas

    def test_ambiguous_names_are_not_linked(self):
        StaffPerson.objects.create(project=self.svr.project, name="Toshmatov Bekzod Valiyevich", role="TP")
        self.assertIsNone(engine.match_staff_person("Bekzod Toshmatov"))
        self.assertIsNone(engine.match_staff_person("Bekzod"))

    def test_parallel_executor_processes_question(self):
        ex = ImmediateExecutor()
        Handler(self.bot, self.tg, executor=ex).handle(group_msg(3, 11, "Nuqta отправлена на модерацию, qachon?"))
        self.assertEqual(ex.calls, 1)
        self.assertEqual(Message.objects.get(message_id=3).status, Message.ANSWERED)


class ExportAndLinkTests(Base):
    def setUp(self):
        call_command("support_setup", verbosity=0)
        Entry.objects.update(status=Entry.APPROVED)
        self.bot = Bot.objects.create(name="S", token_enc=encrypt("1:x"), mode=MODE_LIVE)
        u = engine.identify(10, "agent1", "Agent Bir")
        st = engine.identify(77, "staff1", "Xodim")
        q = Message.objects.create(bot=self.bot, chat_id=-1, message_id=1, user=u, text="Klient ko'rinmayapti", kind="question",
                                   stage="staff", status="answered")
        Message.objects.create(bot=self.bot, chat_id=-1, message_id=2, user=st, text="STIR yuboring", kind="clarify", question=q)
        Message.objects.create(bot=self.bot, chat_id=-1, message_id=3, user=st, text="Marshrutga qo'shildi", kind="staff", question=q)

    def test_export_includes_support_answers_and_threads_without_ids(self):
        import json
        self.login("viewer")
        body = self.client.get("/api/knowledge/export.jsonl", headers={"Authorization": f"Bearer {self.token}"}).content.decode()
        rows = [json.loads(x) for x in body.splitlines() if x]
        types = {r.get("type") for r in rows}
        self.assertTrue({"question_type", "support_answer", "support_thread"} <= types, types)
        thread = next(r for r in rows if r["type"] == "support_thread")
        self.assertEqual((thread["clarifications"], thread["answer"]), (["STIR yuboring"], "Marshrutga qo'shildi"))
        self.assertNotIn("agent1", body)  # username chiqmaydi
        chat = self.client.get("/api/knowledge/export.chat", headers={"Authorization": f"Bearer {self.token}"}).content.decode()
        self.assertIn("STIR yuboring", chat)
        plain = self.client.get("/api/knowledge/export.jsonl?support=0", headers={"Authorization": f"Bearer {self.token}"}).content.decode()
        self.assertNotIn("support_thread", plain)

    def test_manual_link_api(self):
        proj = StaffProject.objects.create(name="BIC")
        sv = StaffPerson.objects.create(project=proj, name="Sv Bir", role="SVR")
        tp = StaffPerson.objects.create(project=proj, name="Agent Ikki", role="TP", manager=sv)
        u = TgUser.objects.get(tg_id=10)
        self.login("viewer")
        self.assertEqual(self.call("post", f"support/tg-users/{u.id}/link/", {"staff_person": tp.id}).status_code, 403)
        self.login("editor")
        r = self.call("post", f"support/tg-users/{u.id}/link/", {"staff_person": tp.id})
        self.assertEqual((r.json()["supervisor"], r.json()["link"]), ("Sv Bir", "manual"))
        self.assertEqual(self.call("get", "support/staff-people/?q=Agent").json()[0]["id"], tp.id)
        r = self.call("post", f"support/tg-users/{u.id}/link/", {"staff_person": None})
        self.assertEqual(r.json()["link"], "none")
