"""Admin nazorati: savol yopilganini admin o'zi tasdiqlaydi (savol egasini kutmasdan) — bu qaror yakuniy."""
from zona.crypto import encrypt

from . import resolution
from .models import Bot, Group, Message
from .tests import FakeClient, group_msg
from .tests_controls import ControlsBase
from .tests_v20 import cb


class AdminResolveTests(ControlsBase):
    def setUp(self):
        super().setUp()
        self.g = Group.objects.create(bot=self.bot, chat_id=-100, title="ROP")
        from .runner import Handler
        self.h = lambda: Handler(self.bot, self.tg)
        self.h().handle(group_msg(40, 1, "Nuqta отправлена на модерацию"))
        self.q = Message.objects.get(message_id=40)
        Message.objects.filter(pk=self.q.pk).update(resolution="asked", confirm_msg_id=555)
        self.q.refresh_from_db()

    def test_admin_mark_closes_prompt_and_is_final(self):
        tg = FakeClient()
        resolution.admin_mark(self.q, "yes", "Admin Test", tg)
        self.q.refresh_from_db()
        self.assertEqual((self.q.resolution, self.q.resolved_by), ("yes", "panel: Admin Test"))
        self.assertTrue(resolution.is_final(self.q))
        self.assertTrue(any(e["id"] == 555 for e in tg.edits))  # "hal bo'ldimi?" xabari yopildi
        # savol egasi keyin "❌ Yo'q" bossa ham — admin qarori o'zgarmaydi, adminga xabar ketadi
        self.bot.admin_chat_id = 777
        self.bot.save()
        self.h().handle(cb(1, f"rs:{self.q.id}:0"))
        self.q.refresh_from_db()
        self.assertEqual(self.q.resolution, "yes")
        self.assertTrue(any(m["chat"] == 777 for m in self.tg.sent))

    def test_asker_text_after_admin_decision_is_saved_but_does_not_change(self):
        resolution.admin_mark(self.q, "no", "Admin Test")
        self.h().handle(group_msg(41, 1, "Rahmat, boldi", reply_to=self.q.bot_reply_id))
        self.q.refresh_from_db()
        self.assertEqual(self.q.resolution, "no")
        fb = Message.objects.get(message_id=41)
        self.assertEqual((fb.kind, fb.question_id), (Message.FEEDBACK, self.q.pk))  # suhbatda saqlandi

    def test_api_single_and_bulk_editor_only(self):
        other = Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=90, kind=Message.QUESTION,
                                       text="Kassa ishlamayapti", status=Message.ANSWERED, resolution="asked")
        Message.objects.filter(pk=self.q.pk).update(confirm_msg_id=None)  # Telegram'ga fon so'rovi testda kerak emas
        self.login("viewer")
        self.assertEqual(self.call("post", f"support/messages/{self.q.id}/resolve/", {"value": "yes"}).status_code, 403)
        self.login("editor")
        r = self.call("post", f"support/messages/{self.q.id}/resolve/", {"value": "yes"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["resolved_by"].startswith("panel: "))
        r = self.call("post", "support/messages/resolve-bulk/", {"ids": [other.id], "value": "no"})
        self.assertEqual((r.status_code, r.json()["done"]), (200, 1))
        other.refresh_from_db()
        self.assertEqual((other.resolution, other.status), ("no", Message.ESCALATED))  # yana xodimga
        self.assertEqual(self.call("post", "support/messages/resolve-bulk/", {"ids": [], "value": "yes"}).status_code, 400)

    def test_admin_yes_stops_confirmation_prompts(self):
        Message.objects.filter(pk=self.q.pk).update(resolution="", confirm_msg_id=None)
        self.q.refresh_from_db()
        resolution.admin_mark(self.q, "yes", "Admin Test")
        self.assertNotIn(self.q.pk, [x.pk for x in resolution.due()])
        _ = (Bot, encrypt)
