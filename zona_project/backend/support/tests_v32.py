"""Konstruktor: istalgan guruhlash va filtr; tahlil bilan bir xil sanoq; savollar ro'yxatiga o'tish."""
import datetime as dt

from django.utils import timezone

from zona.models import Department, Member, StaffPerson, StaffProject

from .models import Activity, Group, Message, TgUser
from .tests_v27 import OpenBase


class ExploreTests(OpenBase):
    def setUp(self):
        super().setUp()
        self.off = Group.objects.create(bot=self.bot, chat_id=-200, title="VAZIFALAR", in_analytics=False)
        proj = StaffProject.objects.create(name="TEST_HEINZ")
        sp = StaffPerson.objects.create(project=proj, name="Agentov Ali", role="TP", territory="T1")
        self.asker.staff_person = sp
        self.asker.save()
        self.staff_u = TgUser.objects.create(tg_id=2, username="test_op", name="T", member=self.member)
        mk = Message.objects.create
        now = timezone.now()
        rows = [(self.g, "live", Message.ANSWERED, "ai", "yes", "bot"), (self.g, "live", Message.ANSWERED, "staff", "no", "Test Xodim"),
                (self.g, "live", Message.ESCALATED, "", "", ""), (self.g, "history", Message.ANSWERED, "staff", "", "x"),
                (self.off, "live", Message.ANSWERED, "ai", "yes", "bot")]
        self.qs = []
        for i, (g, src, st, stage, res, by) in enumerate(rows):
            q = mk(bot=self.bot, group=g, chat_id=g.chat_id, message_id=100 + i, kind="question", text=f"q{i}", source=src,
                   status=st, stage=stage, resolution=res, answered_by=by, user=self.asker,
                   answered_at=now + dt.timedelta(seconds=30) if stage == "ai" else None)
            self.qs.append(q)
        r = mk(bot=self.bot, group=self.g, chat_id=-100, message_id=200, kind="staff", text="Skidka yoqildi, 10 blokdan",
               question=self.qs[1], user=self.staff_u, source="live")
        Message.objects.filter(pk=r.pk).update(created_at=self.qs[1].created_at + dt.timedelta(minutes=4))
        Activity.objects.create(user=self.staff_u, group=self.g, date=timezone.localdate(), count=7, first_at=now, last_at=now,
                                hours=[0] * 24)
        self.login("viewer")

    def get(self, q):
        return self.call("get", "support/analytics/explore/?days=1&" + q).json()

    def test_totals_match_analytics_and_grouping(self):
        a = self.call("get", "support/analytics/?days=1").json()
        e = self.get("by=answer&metrics=count,bot,staff,unanswered,yes,no")
        self.assertEqual(e["totals"]["count"], a["questions"])
        self.assertEqual((e["totals"]["bot"], e["totals"]["staff"], e["totals"]["unanswered"]),
                         (a["summary"]["bot"], a["summary"]["staff"], a["summary"]["unanswered"]))
        self.assertEqual({r["k0"]: r["count"] for r in e["rows"]}, {"Bot": 1, "Xodim": 1, "Javobsiz": 1})
        self.assertEqual(self.get("scope=all&metrics=count")["totals"]["count"], 5)  # tarix va test guruh ham

    def test_two_dims_filters_and_meta(self):
        e = self.get("by=asker,resolution&metrics=count,median_s&f_role=Savdo vakili")
        self.assertEqual(sum(r["count"] for r in e["rows"]), 3)
        self.assertEqual(e["asker_meta"][str(self.asker.pk)]["project"], "TEST_HEINZ")
        no = next(r for r in e["rows"] if r["k1"] == "no")
        self.assertEqual(no["median_s"], 240.0)  # xodim 4 daqiqada javob berdi
        self.assertIn({"key": "Javobsiz", "label": "Javobsiz", "n": 1}, e["options"]["answer"])
        self.assertEqual(self.get("f_project=Boshqa&metrics=count")["totals"]["count"], 0)

    def test_inbox_list_uses_same_filters(self):
        ids = {m["id"] for m in self.call("get", "support/messages/?ex=1&days=1&f_answer=Bot,Javobsiz").json()}
        self.assertEqual(ids, {self.qs[0].pk, self.qs[2].pk})

    def test_staff_and_activity_datasets(self):
        s = self.get("dataset=staff&by=staff,kind&metrics=count,answers,questions,median_s")
        self.assertEqual(s["rows"][0]["l0"], "Test Xodim")
        self.assertEqual((s["rows"][0]["answers"], s["rows"][0]["median_s"]), (1, 240.0))
        a = self.get("dataset=activity&by=who&metrics=messages,people")
        self.assertEqual(a["rows"][0], {"k0": "Xodim", "l0": "Xodim", "messages": 7, "people": 1})
        bad = self.get("dataset=nope&by=zzz")
        self.assertEqual((bad["dataset"], bad["by"]), ("questions", []))
