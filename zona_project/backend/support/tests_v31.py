"""Qayta so'ralganda oldingi "hal bo'ldimi?" xabarlari o'chiriladi; ma'lumot xabari (moderatsiya) avtomatik yopiladi."""
import datetime as dt

from . import resolution
from .models import Entry, Message, TgUser
from .tests_v20 import NOON
from .tests_v27 import OpenBase, press


class DropPromptTests(OpenBase):
    def test_old_prompts_are_deleted_on_reask(self):
        h = TgUser.objects.create(tg_id=2, username="test_op", name="T", member=self.member)
        q = self.q(status=Message.ANSWERED, answered_by="Test Xodim", answered_at=NOON - dt.timedelta(minutes=15), handler=h)
        resolution.ask_pending(self.tg, now=NOON)
        q.refresh_from_db()
        first = q.confirm_msg_id
        with self.at(0):
            self.h().handle(press(1, f"rs:{q.id}:0", username="agent1"))  # hal bo'lmadi
        self.assertEqual(resolution.followups(self.tg, now=NOON + dt.timedelta(minutes=121)), 1)
        q.refresh_from_db()
        self.assertIn(first, self.tg.deleted)  # eski so'rov o'chirildi
        self.assertNotEqual(q.confirm_msg_id, first)
        second = q.confirm_msg_id
        resolution.followups(self.tg, now=q.next_ask_at + dt.timedelta(minutes=1))
        self.assertIn(second, self.tg.deleted)


class AutoCloseTests(OpenBase):
    def test_info_message_is_not_asked_and_closes_itself(self):
        e = Entry.objects.create(kind=Entry.TEMPLATE, title="Nuqta moderatsiyaga yuborildi", answer="Kuting", status=Entry.APPROVED,
                                 auto_close=30)
        q = self.q(status=Message.ANSWERED, answered_by="bot", stage="template", entry=e,
                   answered_at=NOON - dt.timedelta(minutes=50))
        Message.objects.filter(pk=q.pk).update(created_at=NOON - dt.timedelta(minutes=20), confirm_msg_id=777)
        self.assertNotIn(q.pk, [x.pk for x in resolution.due(now=NOON)])  # "hal bo'ldimi?" so'ralmaydi
        self.assertEqual(resolution.auto_close_due(self.tg, now=NOON), 0)  # hali 30 daqiqa o'tmagan
        self.assertEqual(resolution.auto_close_due(self.tg, now=NOON + dt.timedelta(minutes=11)), 1)
        q.refresh_from_db()
        self.assertEqual((q.resolution, q.resolved_by, q.confirm_msg_id), ("yes", resolution.AUTO, None))
        self.assertIn(777, self.tg.deleted)
        self.assertEqual(resolution.auto_close_due(self.tg, now=NOON + dt.timedelta(minutes=12)), 0)
