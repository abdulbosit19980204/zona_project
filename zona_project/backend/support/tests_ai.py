"""Kontakt qidiruvi, kirill/yangi alifbo, AI tahlillarini saqlash, AI takliflari va tarix chegaralari."""
from unittest import mock

from django.core.management import call_command
from django.utils import timezone

from zona.ai import providers
from zona.crypto import encrypt
from zona.models import AIAnalysis, AIProvider, AITaskConfig, Member, StaffPerson, StaffProject, StaffUnit
from zona.tests import Base

from . import contacts, engine
from .models import MODE_LIVE, AIJob, Bot, Entry, Group, HistoryJob, Message, Settings, Suggestion
from .runner import Handler
from .tests import FakeClient, group_msg


class ContactClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.contacts = []

    def send_contact(self, chat_id, phone, first_name, last_name="", vcard="", reply_to=None):
        self.contacts.append({"chat": chat_id, "phone": phone, "first": first_name, "vcard": vcard})
        return {"message_id": 1}


def private(mid, uid, text, username=""):
    return {"update_id": mid, "message": {"message_id": mid, "chat": {"id": uid, "type": "private"},
                                          "from": {"id": uid, "username": username, "first_name": "U"}, "text": text}}


class ContactSearchTests(Base):
    def setUp(self):
        lo = StaffProject.objects.create(name="L'Oréal")
        hz = StaffProject.objects.create(name="Heinz")
        sw = StaffUnit.objects.create(project=hz, key="sw", title="Юго-Запад")
        self.rop = StaffPerson.objects.create(project=lo, name="Xasanova Yuliya", role="ROP", phone="+998 90 111 22 33")
        self.svr = StaffPerson.objects.create(project=hz, unit=sw, name="Karimov Anvar", role="SVR", city="Джиззак",
                                              territory="SVR SW 3", phone="+998 91 222 33 44", manager=self.rop)
        StaffPerson.objects.create(project=hz, unit=sw, name="Toshev Ali", role="TP", city="Джиззак", phone="+998 93 000 00 00",
                                   manager=self.svr)
        self.bot = Bot.objects.create(name="S", username="savolbot", token_enc=encrypt("1:x"), mode=MODE_LIVE, admin_chat_id=555)

    def test_parse_and_search_in_any_script(self):
        for q in ["L'Oréal ROP", "loreal ropini topib ber", "Лореаль РОП"]:
            res, _ = contacts.search(q)
            self.assertEqual([r["name"] for r in res], ["Xasanova Yuliya"], q)
        for q in ["Jizzax supervayzeri nomerini topib ber", "Jizzax SVR", "Джиззак супервайзер", "jizzax svr heinz"]:
            res, _ = contacts.search(q)
            self.assertEqual([r["name"] for r in res], ["Karimov Anvar"], q)
        # hududda SVR'ning o'zi yozilmagan bo'lsa — o'sha hududdagi agentlarning supervayzeri
        self.svr.city = "Самарканд"
        self.svr.save()
        res, _ = contacts.search("Jizzax supervayzeri")
        self.assertEqual([(r["name"], r["via"]) for r in res], [("Karimov Anvar", "hudud")])
        # brendda ROP yo'q — eng yuqori rahbar
        res, _ = contacts.search("Heinz ROP")
        self.assertEqual([(r["name"], r["via"]) for r in res], [("Karimov Anvar", "yuqori")])
        self.svr.city = "Джиззак"
        self.svr.save()
        res, q = contacts.search("Jizzax SVR MDLZ")
        self.assertIn("mdlz", q.names)  # MDLZ loyihasi kontaktlarda yo'q — topilmaydi
        self.assertEqual(res, [])
        res, _ = contacts.search("Saidabror telefoni")  # bizning xodim (Xodimlar ro'yxatidan)
        self.assertEqual([(r["kind"], r["name"]) for r in res], [("member", "Saidabror")])

    def test_private_lookup_sends_card_and_contact_only_to_allowed(self):
        tg = ContactClient()
        Member.objects.create(name="Saidabror", role="Operator", telegram="op_said")
        h = Handler(self.bot, tg)
        h.handle(private(1, 900, "Jizzax supervayzeri nomerini topib ber"))  # begona
        self.assertIn("faqat xodimlar", tg.sent[-1]["text"])
        self.assertEqual(tg.contacts, [])
        h.handle(private(2, 901, "Jizzax supervayzeri nomerini topib ber", "op_said"))  # xodim
        self.assertIn("Karimov Anvar", tg.sent[-1]["text"])
        self.assertIn("+998 91 222 33 44", tg.sent[-1]["text"])
        self.assertEqual(tg.contacts[0]["phone"], "+998912223344")
        self.assertIn("ORG:StarGroup;Heinz", tg.contacts[0]["vcard"])

    def test_group_lookup_is_redirected_without_phones(self):
        tg = ContactClient()
        Handler(self.bot, tg).handle(group_msg(5, 10, "/kontakt Jizzax SVR"))
        self.assertIn("shaxsiy chatda", tg.sent[-1]["text"])
        self.assertNotIn("+998", tg.sent[-1]["text"])
        self.assertEqual(tg.contacts, [])


class ScriptTests(Base):
    def setUp(self):
        call_command("support_setup", verbosity=0)
        Entry.objects.update(status=Entry.ARCHIVED)  # shablonlar bu testga aralashmasin
        Entry.objects.create(kind=Entry.FAQ, title="Klient qo'shish", questions=["yangi klient qanday qo'shiladi"],
                             answer="Supervayzerga yozing: klient qo'shish uchun STIR kerak.", status=Entry.APPROVED)
        self.bot = Bot.objects.create(name="S", token_enc=encrypt("1:x"), mode=MODE_LIVE)

    def test_new_alphabet_and_cyrillic_questions_match(self):
        for q in ["yangi klient qanday qōşiladi", "Янги клиент қандай қўшилади", "yangi kliyent qanday qoshiladi"]:
            d = engine.decide(q, engine.detect_lang(q))
            self.assertEqual(d.entry.title if d.entry else None, "Klient qo'shish", q)

    def test_cyrillic_question_gets_cyrillic_answer(self):
        tg = FakeClient()
        Handler(self.bot, tg).handle(group_msg(1, 10, "Янги клиент қандай қўшилади?"))
        self.assertIn("Супервайзерга ёзинг", tg.sent[-1]["text"])
        self.assertIn("STIR", tg.sent[-1]["text"])

    def test_translit_details(self):
        from .translit import lat2cyr
        self.assertEqual(lat2cyr("bo'lim yo'q"), "бўлим йўқ")
        self.assertEqual(lat2cyr("rol: Employee, PRBC'ga kiring"), "рол: Employee, PRBC'га киринг")


class AIHistoryAndSuggestionTests(Base):
    def setUp(self):
        p = AIProvider.objects.create(name="Test", kind="openai_compatible", base_url="http://x", is_active=True)
        AITaskConfig.objects.update_or_create(task=AITaskConfig.SUPPORT, defaults={"enabled": True, "provider": p, "model": "m"})
        self.e1 = Entry.objects.create(kind=Entry.FAQ, title="Klient ko'rinmayapti", answer="Yozing.", status=Entry.APPROVED,
                                       dislikes=3)
        self.e2 = Entry.objects.create(kind=Entry.FAQ, title="Klient agentda chiqmayapti", answer="Supervayzerga yozing.",
                                       status=Entry.APPROVED)

    def fake(self, payload):
        import json
        return mock.patch.object(providers, "call", return_value=providers.Result(json.dumps(payload), 10, 20))

    def test_ai_results_are_saved(self):
        from zona.ai import service
        with self.fake({"text": "Tahlil natijasi"}), mock.patch.object(service, "_ready", return_value=True):
            service.run(AITaskConfig.SUPPORT, None, "Sinov", "sys", "savol", None)
        a = AIAnalysis.objects.get()
        self.assertEqual((a.task, a.label, a.output_tokens), ("support", "Sinov", 20))
        self.login("viewer")
        self.assertEqual(self.call("get", "ai/history/").json()[0]["id"], a.id)
        self.assertEqual(self.call("get", f"ai/history/{a.id}/").json()["prompt"], "savol")

    def test_review_job_creates_suggestions_and_apply(self):
        from . import ai_review
        job = AIJob.objects.create(kind=AIJob.REVIEW_ENTRIES)
        out = {"suggestions": [
            {"entry_id": self.e1.id, "kind": "improve", "answer": "1. Supervayzerga klient nomi va STIR ni yozing.\n2. U marshrutga qo'shadi.",
             "answer_ru": "", "ask_first": "STIR", "add_questions": [], "merge_into": 0, "reason": "Javob juda qisqa"},
            {"entry_id": self.e2.id, "kind": "merge", "answer": "", "answer_ru": "", "ask_first": "", "add_questions": [],
             "merge_into": self.e1.id, "reason": "Takror"},
            {"entry_id": self.e1.id, "kind": "questions", "answer": "", "answer_ru": "", "ask_first": "",
             "add_questions": ["kilent korinmayapti", "Клиент кўринмаяпти"], "merge_into": 0, "reason": "Imlo ko'rinishlari"}]}
        with mock.patch.object(ai_review, "_run", return_value=out):
            ai_review.run_job(job.id)
        self.assertEqual(Suggestion.objects.filter(status="pending").count(), 3)
        self.login("viewer")
        sid = Suggestion.objects.get(kind="improve").id
        self.assertEqual(self.call("post", f"support/ai/suggestions/{sid}/approve/").status_code, 403)
        self.login("editor")
        r = self.call("post", f"support/ai/suggestions/{sid}/approve/", {"payload": {"answer": "Tahrirlangan javob"}})
        self.assertEqual(r.status_code, 200, r.content)
        self.e1.refresh_from_db()
        self.assertEqual((self.e1.answer, self.e1.ask_first), ("Tahrirlangan javob", "STIR"))
        self.assertEqual(self.e1.versions.first().answer, "Yozing.")  # eski javob versiyada
        self.call("post", f"support/ai/suggestions/{Suggestion.objects.get(kind='merge').id}/approve/")
        self.e2.refresh_from_db()
        self.assertEqual(self.e2.status, Entry.ARCHIVED)
        self.call("post", f"support/ai/suggestions/{Suggestion.objects.get(kind='questions').id}/reject/")
        self.assertEqual(Suggestion.objects.get(kind="questions").status, "rejected")
        self.assertEqual(self.call("get", "support/ai/suggestions/").json(), [])

    def test_unanswered_review_proposes_new_entry_requiring_answer(self):
        from . import ai_review
        bot = Bot.objects.create(name="S", token_enc=encrypt("1:x"))
        q = Message.objects.create(bot=bot, chat_id=-1, message_id=1, text="YATT chiqayapti nima qilaman", kind="question",
                                   status="escalated")
        job = AIJob.objects.create(kind=AIJob.REVIEW_UNANSWERED)
        out = {"items": [{"question_ids": [q.id], "existing_entry_id": 0, "title": "YATT xatosi", "questions": ["YATT chiqayapti"],
                          "answer": "", "ask_first": "skrinshot", "reason": "Yangi savol turi"}]}
        with mock.patch.object(ai_review, "_run", return_value=out):
            ai_review.run_job(job.id)
        s = Suggestion.objects.get(kind="new")
        self.login("editor")
        self.assertEqual(self.call("post", f"support/ai/suggestions/{s.id}/approve/").status_code, 400)  # javobsiz qo'shilmaydi
        r = self.call("post", f"support/ai/suggestions/{s.id}/approve/", {"payload": {"answer": "Supervayzerga yozing."}})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Entry.objects.get(title="YATT xatosi").status, Entry.APPROVED)

    def test_ai_jobs_api_requires_configured_ai_and_editor(self):
        self.login("viewer")
        self.assertEqual(self.call("post", "support/ai/jobs/", {"kind": "entries"}).status_code, 403)
        self.login("editor")
        with mock.patch("zona.ai.service.status", return_value={"support": True}):
            self.assertEqual(self.call("post", "support/ai/jobs/", {"kind": "entries"}).status_code, 200)
            self.assertEqual(self.call("post", "support/ai/jobs/", {"kind": "entries"}).status_code, 400)  # bittadan


class HistoryLimitTests(Base):
    def test_history_rate_limits(self):
        bot = Bot.objects.create(name="S", token_enc=encrypt("1:x"))
        s = Settings.load()
        s.mtproto_session_enc = encrypt("sess")
        s.save()
        groups = [Group.objects.create(bot=bot, chat_id=-100 - i, title=f"G{i}") for i in range(4)]
        self.login("admin")
        self.assertEqual(self.call("post", "support/history/", {"group": groups[0].id}).status_code, 200)
        HistoryJob.objects.update(status=HistoryJob.DONE)
        self.assertEqual(self.call("post", "support/history/", {"group": groups[0].id}).status_code, 400)  # 6 soat
        self.assertEqual(self.call("post", "support/history/", {"group": groups[1].id}).status_code, 200)
        HistoryJob.objects.update(status=HistoryJob.DONE)
        self.assertEqual(self.call("post", "support/history/", {"group": groups[2].id}).status_code, 200)
        HistoryJob.objects.update(status=HistoryJob.DONE)
        self.assertEqual(self.call("post", "support/history/", {"group": groups[3].id}).status_code, 400)  # sutkada 3 ta
        self.assertEqual(self.call("post", "support/mtproto/send-code/", {"phone": "+998901234567"}).status_code, 400)  # rozilik
        _ = timezone
