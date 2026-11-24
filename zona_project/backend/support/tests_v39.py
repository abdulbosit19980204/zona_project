"""Eski guruh havolasi, ishonchsiz qoida mas'uli, "qabul qilindi" xabarida ⚠️ tugma, AI muddati, "Xodim bajardi"."""
import time
from unittest import mock

from zona.ai import providers

from . import engine
from .models import Bot, Group, Message, Settings
from .tests import group_msg
from .tests_v27 import OpenBase


class OldGroupLinkTests(OpenBase):
    def setUp(self):
        super().setUp()
        from .runner import Handler
        Handler._redirected.clear()
        self.new = Group.objects.create(bot=self.bot, chat_id=-200, title="ROP yangi", is_admin=True)
        # admin eski guruh qatoriga yangi guruh havolasini kiritgan
        Group.objects.filter(pk=self.g.pk).update(redirect_to=self.new, invite_link="https://t.me/+OldRowLink")

    def test_link_entered_on_old_group_is_used(self):
        self.h().handle(group_msg(600, 1, "Скидка не выходит", username="agent1"))
        self.assertIn('href="https://t.me/+OldRowLink"', self.tg.sent[-1]["text"])

    def test_sees_all_flag(self):
        self.login("viewer")
        rows = {g["id"]: g for g in self.call("get", "support/groups/").json()}
        self.assertFalse(rows[self.g.id]["sees_all"])  # admin emas, privacy noma'lum
        self.assertTrue(rows[self.new.id]["sees_all"])
        Bot.objects.filter(pk=self.bot.pk).update(read_all=True)
        rows = {g["id"]: g for g in self.call("get", "support/groups/").json()}
        self.assertTrue(rows[self.g.id]["sees_all"])


class WeakRuleOwnerTests(OpenBase):
    def test_low_confidence_rule_person_not_assigned(self):
        weak = (mock.Mock(id=594, rule="", title="Antivirus"), 33,
                [{"id": 14, "name": "Jahongir", "telegram": ["Jo6777"], "is_team": False}])
        with mock.patch.object(engine, "rule_answer", return_value=weak), \
                mock.patch.object(engine, "ai_answer", return_value=None):
            d = engine.decide("Assalomu aleykum bez qoyomayman", "uz")
        self.assertTrue(d.needs_human)
        self.assertEqual(d.responsible, [])

    def test_escalation_ack_has_wrong_button(self):
        Settings.objects.update(escalation_ack=True, review_button=True, mention_responsible=True)
        with mock.patch.object(engine, "ai_answer", return_value=None):
            self.h().handle(group_msg(700, 1, "qandaydir mutlaqo notanish muammo xyzzy plugh", username="agent1"))
        q = Message.objects.get(message_id=700, kind=Message.QUESTION)
        ack = next(m for m in self.tg.sent if m["reply_to"] == 700 or m["text"].startswith("Savolingiz"))
        datas = [b["callback_data"] for row in (ack["buttons"] or []) for b in row]
        self.assertEqual(datas, [f"bad:{q.id}"])


class DeadlineTests(OpenBase):
    def test_deadline_caps_timeout_and_expires(self):
        with mock.patch("zona.conf.get", return_value=60):
            with providers.deadline(5):
                self.assertLessEqual(providers._timeout(), 5)
            self.assertEqual(providers._timeout(), 60)
            with providers.deadline(0.5):
                time.sleep(0.01)
                with self.assertRaises(providers.AIError):
                    providers._timeout()


class StaffDoneTests(OpenBase):
    def test_owner_confirmed_counts_as_staff_done(self):
        a = self.q(mid=800, status=Message.ANSWERED, stage="faq")
        Message.objects.filter(pk=a.pk).update(resolution=Message.YES, resolved_by="xodim: Saidabror")
        b = self.q(mid=801, status=Message.ANSWERED, stage="faq")
        c = self.q(mid=802)  # uzatilgan, savol egasi "hal bo'ldi" degan
        Message.objects.filter(pk=c.pk).update(resolution=Message.YES, resolved_by="savol egasi")
        from .explore import _q_metrics, _q_rows
        rows, _ = _q_rows(Message.objects.filter(pk__in=[a.pk, b.pk, c.pk]))
        m = _q_metrics([v for _k, v in rows])
        self.assertEqual((m["bot"], m["staff_done"], m["unanswered"]), (2, 1, 0))
        ans = {v["id"]: k["answer"] for k, v in rows}
        self.assertEqual((ans[a.pk], ans[b.pk]), ("Xodim bajardi", "Bot"))
