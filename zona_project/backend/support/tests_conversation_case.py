"""Suhbatni boshqarish — bitta savol = bitta holat (agent + obyekt + muammo): obyekt kalitlari, «hali ham», AI qaror."""
from unittest import mock

from . import conversation
from .models import Message, Settings, TgUser
from .tests_controls import ControlsBase


class CaseTests(ControlsBase):
    def setUp(self):
        super().setUp()
        self.agent = TgUser.objects.create(tg_id=900, username="agent", name="Agent")
        self.root = Message.objects.create(bot=self.bot, chat_id=-1, message_id=1, kind=Message.QUESTION,
                                           user=self.agent, text="UZ-00011111 klientga aksiya chiqmayapti",
                                           status=Message.ESCALATED)

    def nt(self, text, photo=False, ai=None):
        with mock.patch.object(conversation, "ai_case", return_value=ai) as m:
            r = conversation.new_topic(text, self.root, photo)
        return r, m.called

    def test_object_keys(self):
        self.assertEqual(self.nt("UZ-00011111 da hali ham skidka yo'q")[0], False)
        self.assertEqual(self.nt("UZ-00022222 klientga ham aksiya chiqmayapti")[0], True)
        self.assertEqual(self.nt("Assalomu alaykum, UZ-00011111 aksiya chiqmadi", photo=True), (False, False))

    def test_greeting_with_still_not_working_is_continuation_without_ai(self):
        self.assertEqual(self.nt("Assalomu alaykum, hali ham chiqmayapti"), (False, False))
        self.assertEqual(self.nt("Добрый день, до сих пор не вышло"), (False, False))

    def test_ambiguous_goes_to_ai_and_falls_back(self):
        self.assertEqual(self.nt("Assalomu alaykum, zakaz o'tmayapti klientda", ai=False), (False, True))
        self.assertEqual(self.nt("Assalomu alaykum, zakaz o'tmayapti klientda", ai=True), (True, True))
        self.assertEqual(self.nt("Assalomu alaykum, zakaz o'tmayapti klientda", ai=None), (True, True))  # avvalgi qoida
        self.assertEqual(self.nt("shu do'konda ham xuddi shunday", photo=True, ai=False), (False, True))

    def test_history_mode_never_calls_ai(self):
        with mock.patch.object(conversation, "ai_case") as m:
            conversation.action(self.root, "Assalomu alaykum, zakaz o'tmayapti klientda", False, use_ai=False)
        self.assertFalse(m.called)

    def test_ai_case_off_when_ai_disabled(self):
        Settings.load()
        Settings.objects.update(ai_enabled=False)
        self.assertIsNone(conversation.ai_case(self.root, "Assalomu alaykum, yana muammo", False))
