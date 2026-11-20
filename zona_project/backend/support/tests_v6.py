"""Albom va takroriy rasmlar, forward, guruhni topish, savol beruvchilar tahlili, havola, AI asosiy javob, Claude buyrug'i."""
import asyncio
import os
import tempfile
from unittest import mock

from django.core.management import call_command

from zona.crypto import decrypt, encrypt
from zona.models import AIProvider, AITaskConfig
from zona.tests import Base

from . import engine
from .models import MODE_LIVE, Bot, Entry, Group, Media, Message, Settings
from .runner import Handler
from .tests import FakeClient, group_msg, visible


class FlowBase(Base):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        p = mock.patch.dict(os.environ, {"ZONA_SUPPORT_MEDIA": media.name})
        p.start()
        self.addCleanup(p.stop)
        call_command("support_setup", verbosity=0)
        Entry.objects.update(status=Entry.APPROVED)
        self.bot = Bot.objects.create(name="S", token_enc=encrypt("1:x"), mode=MODE_LIVE)
        self.tg = FakeClient()

    def h(self):
        return Handler(self.bot, self.tg)


def album(mid, uid, gid, caption=""):
    m = group_msg(mid, uid, caption, photo=True)
    m["message"]["media_group_id"] = gid
    return m


class AlbumTests(FlowBase):
    def test_album_is_one_question_with_one_answer(self):
        with mock.patch("support.runner.ocr.read_text", return_value="Торговая точка \"X\" отправлена на модерацию"):
            h = self.h()
            h.handle(album(1, 10, "g1", "bu nima?"))
            h.handle(album(2, 10, "g1"))
            h.handle(album(3, 10, "g1"))
        self.assertEqual(Message.objects.filter(kind="question").count(), 1)
        q = Message.objects.get(kind="question")
        self.assertEqual(Media.objects.filter(message=q).count(), 3)
        self.assertEqual(len([x for x in self.tg.sent if x["chat"] == -100]), 1)

    def test_repeated_screens_from_same_user_get_one_answer(self):
        with mock.patch("support.runner.ocr.read_text", return_value="Торговая точка \"X\" отправлена на модерацию"):
            h = self.h()
            h.handle(group_msg(1, 10, "", photo=True))
            h.handle(group_msg(2, 10, "", photo=True))
        answers = [x for x in visible(self.tg) if x["chat"] == -100]
        self.assertEqual(len(answers), 2)  # javob + qisqa "javobi yuqorida" eslatmasi
        self.assertIn("☝️", answers[1]["text"])
        self.assertEqual(Message.objects.get(message_id=2).stage, "dup")

    def test_forwarded_message_is_answered(self):
        m = group_msg(5, 10, "Nuqta отправлена на модерацию, qachon?")
        m["message"]["forward_origin"] = {"type": "user"}
        self.h().handle(m)
        self.assertEqual(Message.objects.get(message_id=5).status, Message.ANSWERED)

    def test_message_link(self):
        g = Group(chat_id=-1004410351675, title="G")
        self.assertEqual(g.message_link(77), "https://t.me/c/4410351675/77")
        g.username = "stargroup_support"
        self.assertEqual(g.message_link(77), "https://t.me/stargroup_support/77")


class ResolveTests(Base):
    def test_group_found_via_dialogs_when_not_cached(self):
        from . import history

        class Ent:
            id = 4410351675

        class Dialog:
            entity = Ent()

        class FakeTelethon:
            async def get_entity(self, peer):
                raise ValueError("Could not find the input entity")

            async def iter_dialogs(self):
                yield Dialog()

        with mock.patch.object(history, "_peer", return_value="peer"):
            ent = asyncio.run(history._resolve(FakeTelethon(), -1004410351675))
            self.assertEqual(ent.id, 4410351675)
            with self.assertRaisesRegex(ValueError, "guruhda emas"):
                asyncio.run(history._resolve(FakeTelethon(), -1009999999999))


class AnalyticsV6Tests(FlowBase):
    def test_askers_and_top_types(self):
        h = self.h()
        h.handle(group_msg(1, 10, "Nuqta отправлена на модерацию, qachon?"))
        h.handle(group_msg(2, 11, "Prbc da kilent qoshish chiqmayapti"))
        h.handle(group_msg(3, 11, "Nuqta отправлена на модерацию, tasdiqlanmayapti"))
        self.login("viewer")
        d = self.call("get", "support/analytics/?days=30").json()
        top = {x["user"]: x for x in d["askers"]}
        self.assertEqual(max(x["questions"] for x in top.values()), 2)
        self.assertTrue(d["top_types"][0]["n"] >= 2)
        msgs = self.call("get", "support/messages/?status=all").json()
        self.assertTrue(all("link" in m for m in msgs))


class AIPrimaryTests(FlowBase):
    def test_ai_composes_answer_when_kb_match_is_not_exact(self):
        Settings.load()
        Settings.objects.update(ai_enabled=True, ai_primary=True, ai_primary_below=95)
        Entry.objects.create(kind=Entry.FAQ, title="Klient agentda ko'rinmayapti", answer="Supervayzer marshrutga qo'shadi.",
                             status=Entry.APPROVED)
        fake = {"text": "Klient marshrutingizda yo'q — supervayzeringiz uni marshrutga qo'shadi.", "confidence": 88,
                "needs_human": False, "reason": "bazadagi javob asosida", "meta": {}}
        with mock.patch.object(engine, "ai_answer", return_value=fake) as ai:
            d = engine.decide("kilentim agentda korinmayapti kecha", "uz")
        self.assertEqual(d.stage, "ai")
        self.assertIn("marshrut", d.text)
        self.assertEqual(ai.call_args.args[2][0].title, "Klient agentda ko'rinmayapti")  # kontekstda eng yaqin javob
        with mock.patch.object(engine, "ai_answer", return_value=None):  # AI ishlamasa — bazadagi javob
            self.assertEqual(engine.decide("kilentim agentda korinmayapti kecha", "uz").stage, "faq")

    def test_use_claude_command(self):
        AIProvider.objects.create(name="Google Gemini (bepul)", kind="gemini", is_active=True, api_key_enc=encrypt("g"))
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            call_command("support_use_claude", verbosity=0)
        cfg = AITaskConfig.objects.get(task="support")
        self.assertEqual((cfg.provider.kind, cfg.model, cfg.fallback_provider.kind), ("anthropic", "claude-opus-5-5", "gemini"))
        self.assertEqual(decrypt(cfg.provider.api_key_enc), "sk-ant-test")
        self.assertTrue(Settings.load().ai_enabled)
