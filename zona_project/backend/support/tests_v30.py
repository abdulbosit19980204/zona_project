"""Claude belgisi va standartga qo'shish; xodimlar faolligi (kunlik), ish grafigi va to'liq statistikasi."""
import datetime as dt
from unittest import mock

from django.utils import timezone

from zona.models import Department, Member

from . import activity
from .dedupe import absorb, generic_phrase
from .models import Activity, Entry, EntryVersion, Group, Media, Message, TgUser
from .runner import approve
from .tests import group_msg
from .tests_v6 import FlowBase


class StandardTests(FlowBase):
    def test_generic_phrase_strips_client_parts(self):
        self.assertEqual(generic_phrase("D17 Afsona makon lokatsiyasini to'g'rilab bering"),
                         "Afsona makon lokatsiyasini to'g'rilab bering")
        self.assertEqual(generic_phrase('Торговая точка "SALOXIDDIN MAXMUDOVLAR" OILAVIY KORXONA отправлена на модерацию!'),
                         "Торговая точка отправлена на модерацию")
        self.assertEqual(generic_phrase("Uz-00030104 Тогирлап берила\n📍 Lokatsiya: https://maps.google.com/?q=1,2"),
                         "Тогирлап берила")
        self.assertEqual(generic_phrase("Ассалому алейкум"), "")

    def test_absorb_and_bulk(self):
        std = Entry.objects.create(kind=Entry.FAQ, title="Lokatsiyani o'zgartirish", answer="Std javob", status=Entry.APPROVED,
                                   questions=["lokatsiyani o'zgartiring"])
        a = Entry.objects.create(kind=Entry.FAQ, title="D17 shu dokon lokatsiyasini to'g'rilab bering", answer="Tekshiring",
                                 status=Entry.NEW, source="history", claude_kind="same", claude_target=std)
        b = Entry.objects.create(kind=Entry.FAQ, title="UZ-0001 lokatsiyasini to'g'rilab bering", answer="x",
                                 status=Entry.NEW, source="history", claude_kind="same", claude_target=std)
        self.login("admin")
        r = self.call("get", "support/entries/?status=new&claude=same&limit=20&offset=0").json()
        self.assertEqual(r["count"], 2)
        self.assertEqual(r["results"][0]["claude_target_title"], "Lokatsiyani o'zgartirish")
        self.assertEqual(self.call("post", "support/entries/bulk/", {"ids": [a.id, b.id], "action": "absorb"}).json()["done"], 2)
        std.refresh_from_db()
        a.refresh_from_db()
        self.assertEqual((a.status, std.answer, std.status), (Entry.ARCHIVED, "Std javob", Entry.APPROVED))
        self.assertIn("shu dokon lokatsiyasini to'g'rilab bering", std.questions)
        self.assertEqual(sum("lokatsiyasini to'g'rilab bering" == q for q in std.questions), 1)  # takror qo'shilmadi
        self.assertTrue(EntryVersion.objects.filter(entry=std).exists())

    def test_approving_general_entry_absorbs_covers(self):
        g = Entry.objects.create(kind=Entry.FAQ, title="Umumiy", answer="Umumiy javob", status=Entry.REVIEW, claude_kind="general")
        c = Entry.objects.create(kind=Entry.FAQ, title="Afsona makon dostavka chiqmayapti", answer="x", status=Entry.NEW,
                                 source="history", claude_kind="same", claude_target=g)
        Media.objects.create(kind=Media.PHOTO, label=c, path="")
        approve(g, "admin")
        c.refresh_from_db()
        self.assertEqual(c.status, Entry.ARCHIVED)
        self.assertEqual(Media.objects.get().label_id, g.pk)


class ActivityTests(FlowBase):
    def setUp(self):
        super().setUp()
        dep = Department.objects.create(name="d")
        self.m = Member.objects.create(name="Test Xodim", role="r", department=dep, telegram="test_op")
        self.g = Group.objects.create(bot=self.bot, chat_id=-100, title="ROP")
        self.u = TgUser.objects.create(tg_id=2, username="test_op", name="T", member=self.m)

    def test_live_messages_are_recorded_per_day(self):
        at = timezone.make_aware(dt.datetime(2026, 11, 20, 9, 5))
        with mock.patch.object(timezone, "now", return_value=at):
            self.h().handle(group_msg(1, 2, "salom hammaga", username="test_op"))
        with mock.patch.object(timezone, "now", return_value=at + dt.timedelta(hours=8)):
            self.h().handle(group_msg(2, 2, "bugun ish tugadi", username="test_op"))
        row = Activity.objects.get(user=self.u)
        self.assertEqual(row.count, 2)
        self.assertEqual(sum(row.hours), 2)
        self.assertEqual(row.last_at - row.first_at, dt.timedelta(hours=8))

    def test_backfill_board_and_detail(self):
        q = Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=1, kind="question", text="Aksiya yoqing",
                                   source="history")
        base = timezone.make_aware(dt.datetime(2026, 11, 18, 9, 0))
        Message.objects.filter(pk=q.pk).update(created_at=base)
        for i, (text, kind, mins) in enumerate([("Kod tt bering?", "clarify", 2), ("Aksiya yoqildi, 10 blokdan", "staff", 30),
                                                 ("К Саиду", "staff", 600)]):
            m = Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=10 + i, kind=kind, text=text,
                                       question=q, user=self.u, source="history")
            Message.objects.filter(pk=m.pk).update(created_at=base + dt.timedelta(minutes=mins))
        Member.objects.update_or_create(name="Saidabror", defaults={"role": "o", "department": self.m.department,
                                                                    "telegram": "said_t"})
        from . import engine
        engine._PEOPLE_IDX.update(at=0.0, rows=[])
        self.assertEqual(activity.backfill(timezone.now()), 3)  # egasiz xabar hisobga olinmaydi
        self.assertEqual(Activity.objects.get(user=self.u).count, 3)
        self.login("viewer")
        r = self.call("get", "support/analytics/staff/?from=2026-11-18&to=2026-11-18").json()
        row = next(x for x in r["staff"] if x["id"] == self.u.pk)
        self.assertEqual((row["messages"], row["answers"], row["clarifications"], row["handoffs"], row["active_days"]),
                         (3, 1, 1, 1, 1))
        self.assertEqual((row["start"], row["end"]), ("09:02", "19:00"))
        self.assertEqual(row["median_s"], 120.0)  # birinchi javob (aniqlashtirish) — 2 daqiqa
        d = self.call("get", f"support/analytics/staff/{self.u.pk}/?from=2026-11-18&to=2026-11-18").json()
        self.assertEqual(d["timeline"][0]["first"], "09:02")
        self.assertEqual(d["timeline"][0]["work"], 3)
        self.assertEqual(len(d["recent"]), 3)
        self.assertEqual(sum(map(sum, d["heatmap"])), 3)
        self.assertEqual(self.call("get", "support/analytics/staff/999999/").status_code, 404)
