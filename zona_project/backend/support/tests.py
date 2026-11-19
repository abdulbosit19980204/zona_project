import os
import tempfile
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from zona.crypto import encrypt
from zona.models import Member, Profile, TeamContact
from zona.tests import Base

from . import engine
from .models import MODE_LIVE, MODE_SHADOW, Bot, Entry, Group, Message, Settings, TgUser
from .runner import Handler

OCR_1C = """1c DMS food · #1588 · 1-tahrir  1C da allaqachon bor
1C DMS da bu nuqta allaqachon bor edi — mavjudini qaytardi; yangisi yaratilmadi.
1C dagi nuqta kodi UZ-00032829
1C dagi kontragent BOBOJONOVA MAXFUZA AZIMOVNA (UZ-00024680)
Marshrut Kunlarsiz"""
OCR_PT = 'Новая торговая точка\nТорговая точка "BRAND-BRO-TRADE" MAS`ULIYATI CHEKLANGAN JAMIYAT\nотправлена на модерацию!'


class FakeClient:
    def __init__(self):
        self.sent, self.callbacks, self.edited = [], [], []

    def send(self, chat_id, text, reply_to=None, buttons=None, html=True):
        self.sent.append({"chat": chat_id, "text": text, "reply_to": reply_to, "buttons": buttons})
        return {"message_id": 1000 + len(self.sent)}

    def answer_callback(self, cid, text="", alert=False):
        self.callbacks.append(text)

    def edit_buttons(self, chat_id, message_id, buttons=None):
        self.edited.append(message_id)

    def typing(self, chat_id):
        pass

    def download(self, file_id):
        return b"img"


def group_msg(mid, uid, text, username="", reply_to=None, chat=-100, photo=False):
    m = {"message_id": mid, "chat": {"id": chat, "type": "supergroup", "title": "Support"},
         "from": {"id": uid, "first_name": f"U{uid}", "username": username}, "text": text}
    if reply_to:
        m["reply_to_message"] = {"message_id": reply_to}
    if photo:
        m.pop("text")
        m["caption"] = text
        m["photo"] = [{"file_id": "small"}, {"file_id": "big"}]
    return {"update_id": mid, "message": m}


class EngineTests(TestCase):
    def setUp(self):
        call_command("support_setup", verbosity=0)
        Entry.objects.update(status=Entry.APPROVED)

    def test_question_filter_and_lang(self):
        self.assertFalse(engine.is_question("rahmat"))
        self.assertFalse(engine.is_question("ok"))
        self.assertTrue(engine.is_question("klient qo'shib bo'lmayapti nima qilay"))
        self.assertTrue(engine.is_question("", has_photo=True))
        self.assertEqual(engine.detect_lang("Почему не создаётся точка?"), "ru")
        self.assertEqual(engine.detect_lang("Нуқта қўшилмаяпти"), "uz")
        self.assertEqual(engine.detect_lang("nuqta qo'shilmayapti"), "uz")

    def test_screenshot_1c_already_exists(self):
        d = engine.decide("shu klient nima bo'ldi?\n" + OCR_1C, "uz")
        self.assertEqual(d.stage, "template")
        self.assertIn("UZ-00032829", d.text)  # nuqta kodi (kontragent kodi emas)
        self.assertFalse(d.needs_human)

    def test_screenshot_moderation_ru_answer(self):
        d = engine.decide(OCR_PT, "ru")
        self.assertEqual(d.stage, "template")
        self.assertIn("модерацию", d.text)
        self.assertIn("BRAND-BRO-TRADE", d.text)

    def test_missing_field_line_is_dropped(self):
        e = Entry.objects.get(title__startswith="PRBC → 1C")
        self.assertNotIn("{kod}", engine.render_answer(e, {}, "uz"))

    def test_faq_similarity_and_threshold(self):
        Entry.objects.create(kind=Entry.FAQ, title="ProTarget parolni qanday tiklash mumkin",
                             questions=["parol esdan chiqdi protarget"], answer="Parolni tiklash: ...",
                             status=Entry.APPROVED)
        d = engine.decide("protarget parolimni unutdim, qanday tiklayman?", "uz")
        self.assertEqual(d.stage, "faq")
        self.assertIn("tiklash", d.text)
        # tasdiqlanmagan yozuv jonli rejimda ishlatilmaydi
        Entry.objects.filter(kind=Entry.FAQ).update(status=Entry.NEW)
        self.assertNotEqual(engine.decide("protarget parolimni unutdim, qanday tiklayman?", "uz").stage, "faq")
        self.assertEqual(engine.decide("protarget parolimni unutdim, qanday tiklayman?", "uz",
                                       allow_unapproved=True).stage, "faq")


class BotFlowTests(Base):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        patcher = mock.patch.dict(os.environ, {"ZONA_SUPPORT_MEDIA": media.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        call_command("support_setup", verbosity=0)
        self.team = Member.objects.create(name="Dasturchilar", role="Dasturchilar", is_team=True, level="L3")
        self.dev = TeamContact.objects.create(member=self.team, name="Ulug'bek", telegram="stargroupUlugbek")
        self.lead = Member.objects.create(name="Abdulbosit", role="DevOps", level="LEAD", telegram="@uzdev7")
        self.bot = Bot.objects.create(name="S", token_enc=encrypt("1:x"), mode=MODE_SHADOW, admin_chat_id=555)
        self.tg = FakeClient()
        self.h = Handler(self.bot, self.tg)

    def test_identify_staff_and_store_telegram_id(self):
        u = engine.identify(77, "StargroupUlugbek", "Ulugbek")
        self.assertEqual(u.contact, self.dev)
        self.dev.refresh_from_db()
        self.assertEqual(self.dev.telegram_id, 77)
        # username o'zgarsa ham ID orqali taniladi
        self.assertEqual(engine.identify(77, "new_name").contact, self.dev)
        self.assertEqual(engine.identify(78, "uzdev7").member, self.lead)
        self.assertFalse(engine.identify(79, "someone").is_staff)

    def test_private_start_sets_admin_chat_for_lead(self):
        self.bot.admin_chat_id = None
        self.bot.save()
        self.h.handle({"update_id": 1, "message": {"message_id": 1, "chat": {"id": 900, "type": "private"},
                                                   "from": {"id": 78, "username": "uzdev7"}, "text": "/start"}})
        self.bot.refresh_from_db()
        self.assertEqual(self.bot.admin_chat_id, 900)

    def test_shadow_mode_sends_draft_only_to_admin(self):
        with mock.patch("support.runner.ocr.read_text", return_value=OCR_PT):
            self.h.handle(group_msg(10, 1, "bu nima degani?", photo=True))
        q = Message.objects.get(message_id=10)
        self.assertEqual(q.status, Message.DRAFTED)
        self.assertEqual(q.stage, "template")
        self.assertEqual([s["chat"] for s in self.tg.sent], [555])  # guruhga hech narsa yozilmadi
        self.assertIn("send:", str(self.tg.sent[0]["buttons"]))

    def test_live_mode_replies_in_group(self):
        Entry.objects.update(status=Entry.APPROVED)
        Bot.objects.filter(pk=self.bot.pk).update(mode=MODE_LIVE)
        self.bot.refresh_from_db()
        self.h = Handler(self.bot, self.tg)
        self.h.handle(group_msg(11, 1, "Nuqta отправлена на модерацию, qachon tasdiqlanadi?"))
        q = Message.objects.get(message_id=11)
        self.assertEqual(q.status, Message.ANSWERED)
        self.assertEqual(self.tg.sent[0]["chat"], -100)
        self.assertEqual(self.tg.sent[0]["reply_to"], 11)

    def test_greeting_is_ignored_and_group_registered(self):
        self.h.handle(group_msg(12, 1, "rahmat"))
        self.assertFalse(Message.objects.filter(message_id=12).exists())
        self.assertTrue(Group.objects.filter(chat_id=-100, bot=self.bot).exists())

    def test_staff_reply_creates_candidate_and_telegram_approval(self):
        self.h.handle(group_msg(20, 1, "Agentga yangi marshrut qanday biriktiriladi?"))
        self.h.handle(group_msg(21, 77, "1C'da Marshrutlar → agentni tanlab → Saqlash", "stargroupUlugbek", reply_to=20))
        e = Entry.objects.get(source="staff")
        self.assertEqual(e.status, Entry.NEW)
        self.assertEqual(e.author, "Ulug'bek")
        q = Message.objects.get(message_id=20)
        self.assertEqual((q.status, q.answered_by), (Message.ANSWERED, "Ulug'bek"))
        self.assertIn(f"ap:{e.id}", str(self.tg.sent[-1]["buttons"]))
        # boshqa chatdan bosilsa — ruxsat yo'q
        cb = {"id": "c1", "data": f"ap:{e.id}", "from": {"id": 77, "username": "stargroupUlugbek"},
              "message": {"message_id": 5, "chat": {"id": 123}}}
        self.h.handle({"update_id": 30, "callback_query": cb})
        e.refresh_from_db()
        self.assertEqual(e.status, Entry.NEW)
        # admin chatidan L3 xodim tasdiqlaydi
        cb["message"]["chat"]["id"] = 555
        self.h.handle({"update_id": 31, "callback_query": cb})
        e.refresh_from_db()
        self.assertEqual((e.status, e.approved_by), (Entry.APPROVED, "Ulug'bek"))
        # endi bot shu savolga o'zi javob topadi
        self.assertEqual(engine.decide("agentga yangi marshrut qanday biriktiriladi", "uz").stage, "faq")

    def test_feedback_only_from_asker(self):
        Entry.objects.update(status=Entry.APPROVED)
        Bot.objects.filter(pk=self.bot.pk).update(mode=MODE_LIVE)
        self.bot.refresh_from_db()
        h = Handler(self.bot, self.tg)
        h.handle(group_msg(40, 1, "Nuqta отправлена на модерацию"))
        q = Message.objects.get(message_id=40)
        h.handle({"update_id": 41, "callback_query": {"id": "x", "data": f"fb:{q.id}:-1", "from": {"id": 2},
                                                      "message": {"message_id": 1, "chat": {"id": -100}}}})
        q.refresh_from_db()
        self.assertEqual(q.feedback, 0)
        h.handle({"update_id": 42, "callback_query": {"id": "y", "data": f"fb:{q.id}:1", "from": {"id": 1},
                                                      "message": {"message_id": 1, "chat": {"id": -100}}}})
        q.refresh_from_db()
        self.assertEqual(q.feedback, 1)
        self.assertEqual(q.entry.likes, 1)


class ApiTests(Base):
    def setUp(self):
        call_command("support_setup", verbosity=0)
        self.entry = Entry.objects.create(kind=Entry.FAQ, title="Savol", answer="Eski javob", status=Entry.APPROVED)

    def test_viewer_edit_waits_for_approval_and_bot_keeps_old_answer(self):
        self.login("viewer")
        r = self.call("patch", f"support/entries/{self.entry.id}/", {"answer": "Yangi javob"})
        self.assertEqual(r.status_code, 200, r.content)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.answer, "Eski javob")
        self.assertEqual(self.entry.pending["answer"], "Yangi javob")
        self.assertEqual(self.call("post", f"support/entries/{self.entry.id}/approve/").status_code, 403)
        self.login("editor")
        self.assertEqual(self.call("post", f"support/entries/{self.entry.id}/approve/").status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual((self.entry.answer, self.entry.pending), ("Yangi javob", None))
        v = self.entry.versions.first()
        self.assertEqual(v.answer, "Eski javob")
        # versiyaga qaytarish
        self.assertEqual(self.call("post", f"support/entries/{self.entry.id}/revert/{v.id}/").status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.answer, "Eski javob")

    def test_viewer_proposal_is_new_editor_can_approve_directly(self):
        self.login("viewer")
        r = self.call("post", "support/entries/", {"title": "T", "answer": "A", "kind": "faq", "approve": True})
        self.assertEqual(r.json()["status"], "new")
        self.login("editor")
        r = self.call("post", "support/entries/", {"title": "T2", "answer": "A", "kind": "faq", "approve": True})
        self.assertEqual(r.json()["status"], "approved")

    def test_bots_admin_only_and_token_hidden(self):
        self.login("editor")
        self.assertEqual(self.call("get", "support/bots/").status_code, 403)
        self.login("admin")
        r = self.call("post", "support/bots/", {"name": "B", "token": "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertNotIn("token", r.json())
        self.assertTrue(r.json()["token_masked"].endswith("AAAA"))
        self.assertNotIn("AAAAAAAAAAAA", str(self.call("get", "support/bots/").content))
        r = self.call("post", "support/bots/", {"name": "C", "token": "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"})
        self.assertEqual(r.status_code, 400)  # bir token ikki botda bo'lmaydi

    def test_settings_api_hash_masked(self):
        self.login("admin")
        r = self.call("patch", "support/settings/", {"api_id": "123", "api_hash": "abcdef0123456789"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["api_hash"], "••••6789")
        self.assertEqual(Settings.load().api_id, "123")

    def test_panel_answer_sends_reply_and_creates_candidate(self):
        bot = Bot.objects.create(name="S", token_enc=encrypt("1:x"))
        q = Message.objects.create(bot=bot, chat_id=-100, message_id=5, text="Savol matni bu yerda", kind="question")
        self.login("viewer")
        with mock.patch("support.views.Client") as C:
            C.return_value.send.return_value = {"message_id": 9}
            r = self.call("post", f"support/messages/{q.id}/answer/", {"text": "Javob"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(C.return_value.send.call_args.kwargs["reply_to"], 5)
        q.refresh_from_db()
        self.assertEqual(q.status, Message.ANSWERED)
        self.assertEqual(Entry.objects.get(pk=r.json()["entry"]).status, Entry.NEW)

    def test_test_endpoint(self):
        self.login("viewer")
        r = self.call("post", "support/entries/test/", {"text": OCR_1C, "all": True})
        self.assertEqual(r.json()["stage"], "template")


class ImportKbTests(Base):
    def test_import_from_question_base_is_idempotent_and_matches_examples(self):
        from zona.models import Task
        t = Task.objects.exclude(rule="").exclude(examples=[]).first() or Task.objects.first()
        if not t.rule:
            t.rule = "Supervayzerga yozing"
        t.examples = ["klientni menga ulab bering iltimos"]
        t.save()
        call_command("support_import_kb", verbosity=0)
        n = Entry.objects.count()
        self.assertGreater(n, 0)
        e = Entry.objects.get(title=" ".join(t.title.split())[:200])
        self.assertEqual((e.status, e.source), (Entry.APPROVED, "seed"))
        self.assertIn("klientni menga ulab bering iltimos", e.questions)
        call_command("support_import_kb", verbosity=0)
        self.assertEqual(Entry.objects.count(), n)  # qayta ishga tushirish dublikat yaratmaydi
        d = engine.decide("klientni menga ulab bering iltimos", "uz")
        self.assertEqual((d.stage, d.entry), ("faq", e))


class DistributionPackTests(Base):
    def test_pack_imports_once_for_review_and_matches_sales_questions(self):
        call_command("support_import_kb", pack="distribution", verbosity=0)
        n = Entry.objects.filter(author="distribution to'plami").count()
        self.assertGreaterEqual(n, 30)
        self.assertFalse(Entry.objects.filter(author="distribution to'plami").exclude(status=Entry.REVIEW).exists())
        call_command("support_import_kb", pack="distribution", verbosity=0)
        self.assertEqual(Entry.objects.filter(author="distribution to'plami").count(), n)
        for q, expect in [("plan qolib ketyapti savdoni qanday oshiraman", "Planni"),
                          ("клиент перестал брать товар", "Klient zakaz"),
                          ("srok o'tgan tovarni qaytarish kerak", "Muddati")]:
            d = engine.decide(q, engine.detect_lang(q), allow_unapproved=True)
            self.assertTrue(d.entry and d.entry.title.startswith(expect), (q, d.stage, d.entry))


class TeamContactTests(Base):
    def test_contacts_crud_and_reports_keep_team_whole(self):
        from zona.timeload import member_load
        team = Member.objects.filter(is_team=True).first() or Member.objects.create(name="T", role="T", is_team=True)
        self.login("editor")
        r = self.call("post", "team-contacts/", {"member": team.id, "name": "Guzel", "telegram": "@Guzel_Taipova"})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["telegram"], "Guzel_Taipova")
        state = self.call("get", "state/").json()
        m = next(x for x in state["members"] if x["id"] == team.id)
        self.assertEqual([c["name"] for c in m["contacts"]], ["Guzel"])
        # kontakt alohida xodim emas: yuklama hisobotida qatnashmaydi
        self.assertNotIn("Guzel", [v["member"].name for v in member_load().values()])
        person = Member.objects.filter(is_team=False).first()
        self.assertEqual(self.call("post", "team-contacts/", {"member": person.id, "name": "X"}).status_code, 400)
        self.login("viewer")
        self.assertEqual(self.call("post", "team-contacts/", {"member": team.id, "name": "Y"}).status_code, 403)


class PackUpdateTests(Base):
    def test_rerun_extends_questions_only_for_untouched_entries(self):
        call_command("support_import_kb", pack="distribution", verbosity=0)
        e = Entry.objects.get(title__startswith="Zakaz yetkazilmadi")
        e.questions = e.questions[:2]
        e.save()
        edited = Entry.objects.get(title__startswith="Minimal zakaz")
        edited.questions = ["x savol"]
        edited.save()
        from .runner import snapshot
        snapshot(edited, "editor")  # xodim tahrirlagan — tegilmasligi kerak
        call_command("support_import_kb", pack="distribution", verbosity=0)
        e.refresh_from_db()
        edited.refresh_from_db()
        self.assertIn("nedovoz bo'ldi", e.questions)
        self.assertEqual(edited.questions, ["x savol"])
        d = engine.decide("Когда привезут заказ?", "ru", allow_unapproved=True)
        self.assertTrue(d.entry.title.startswith("Zakaz qachon"), d.entry.title)
