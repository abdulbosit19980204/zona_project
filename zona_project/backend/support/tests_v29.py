"""Rad etilgan savol yechim chiqquncha qayta so'raladi; "К Саиду" — javob emas, savol kimga tegishli ekani;
mas'ul panelda ko'rinadi va tanlanadi; tahlildagi raqamdan aynan o'sha savollar ro'yxatiga o'tish."""
import datetime as dt

from zona.models import Department, Member, TeamContact

from . import engine, resolution
from .models import Entry, Group, Message, TgUser
from .tests import group_msg
from .tests_v20 import NOON
from .tests_v27 import OpenBase, press


class PeopleBase(OpenBase):
    def setUp(self):
        super().setUp()
        dep = Department.objects.create(name="Ops")
        # support_setup ham shu nomli mas'ullarni yaratadi — bitta odam bitta yozuv bo'lsin
        self.said, _ = Member.objects.update_or_create(name="Saidabror", defaults={"role": "Operator", "department": dep,
                                                                                  "telegram": "said_t"})
        self.pt, _ = Member.objects.update_or_create(name="Pro-target", defaults={"role": "Pro-target", "department": dep,
                                                                                 "is_team": True, "level": "EXT"})
        TeamContact.objects.filter(member=self.pt).delete()
        TeamContact.objects.create(member=self.pt, name="Eldar", telegram="eldar_t")
        TeamContact.objects.create(member=self.pt, name="Guzel Taipova", telegram="guzel_t")
        engine._PEOPLE_IDX.update(at=0.0, rows=[])
        engine._NAMES.update(at=0.0, set=set())


class HandoffTests(PeopleBase):
    def test_who_the_question_was_handed_to(self):
        self.assertEqual(engine.handoff_to("К Саиду"), self.said)
        self.assertEqual(engine.handoff_to("Saidabrorga"), self.said)
        self.assertEqual(engine.handoff_to("@said_t"), self.said)
        self.assertEqual(engine.handoff_to("Eldar можете помочь"), self.pt)
        self.assertEqual(engine.handoff_to("Гузель посмотрите пожалуйста"), self.pt)
        self.assertIsNone(engine.handoff_to("@kimdir посмотрите"))  # tanilmagan odam
        self.assertIsNone(engine.handoff_to("Saidabror va Eldar"))  # ikki xil mas'ul
        self.assertIsNone(engine.handoff_to("Перезайдите в приложение"))
        self.assertIsNone(engine.handoff_to("Вы супер"))  # maqtov — uzatish emas
        self.assertIsNone(engine.handoff_to("Said"))  # belgisiz bitta ism — aniq emas
        self.assertTrue(engine.not_an_answer("К Саиду"))

    def test_staff_handoff_is_not_learned_as_answer_but_as_owner(self):
        guzel = TgUser.objects.create(tg_id=3, username="guzel_t", name="Guzel")
        said_u = TgUser.objects.create(tg_id=4, username="said_t", name="Said")
        q = self.q()
        Message.objects.filter(pk=q.pk).update(text="Доставщик и дата доставкани танлаб булмаяпти куриб беринглар илтимос")
        with self.at(0):
            self.h().handle(group_msg(60, 3, "К Саиду", username="guzel_t", reply_to=5))
        q.refresh_from_db()
        self.assertEqual(q.status, Message.ESCALATED)  # javob emas — savol hali javob kutadi
        self.assertEqual(q.handler_id, said_u.pk)  # eslatmalar endi Saidabrorni belgilaydi
        e = Entry.objects.get(source="staff")
        self.assertEqual(e.responsible, self.said)
        self.assertIn("**Saidabror** bajaradi", e.answer)
        self.assertIn("Saidabror", e.answer_ru)
        self.assertNotIn("Саиду", e.answer)
        self.assertEqual(guzel.pk, TgUser.objects.get(tg_id=3).pk)


class PersistentTests(PeopleBase):
    def answered(self):
        h = TgUser.objects.create(tg_id=2, username="test_op", name="T", member=self.member)
        q = self.q(status=Message.ANSWERED, answered_by="Test Xodim", answered_at=NOON - dt.timedelta(minutes=15), handler=h)
        resolution.ask_pending(self.tg, now=NOON)
        return q

    def test_no_names_who_will_look_again(self):
        q = self.answered()
        with self.at(0):
            self.h().handle(press(1, f"rs:{q.id}:0", username="agent1"))
        closed = self.tg.edits[-1]["text"]
        self.assertIn("@test_op", closed)
        self.assertIn("qayta ko'rib chiqadi", closed)

    def test_not_resolved_is_asked_again_until_solved(self):
        q = self.answered()
        with self.at(0):
            self.h().handle(press(1, f"rs:{q.id}:0", username="agent1"))
        sent_group = lambda: [m for m in self.tg.sent if m["chat"] == -100]  # noqa: E731
        n0 = len(sent_group())
        for _ in range(4):  # remind_max=2 — lekin to'xtamaydi (ish vaqtida; kechasi — ertasi kuni)
            q.refresh_from_db()
            at = q.next_ask_at + dt.timedelta(minutes=1)
            if at.astimezone(resolution.TZ).hour >= 20:
                at = at.replace(hour=5, minute=0) + dt.timedelta(days=1)  # ertasi 10:00 (Toshkent)
            self.assertEqual(resolution.followups(self.tg, now=at), 1)
        t = (at - NOON).total_seconds() / 60 + 5
        self.assertEqual(len(sent_group()) - n0, 4)
        admin = [m for m in self.tg.sent if m["chat"] == 555 and "ochiq qolmoqda" in m["text"]]
        self.assertEqual(len(admin), 1)  # admin chatiga bir marta
        q.refresh_from_db()
        self.assertEqual(q.remind_count, 4)
        self.assertIsNotNone(q.next_ask_at)
        self.assertGreaterEqual(q.next_ask_at - at, dt.timedelta(minutes=239))  # oraliq uzaydi
        with self.at(t):
            self.h().handle(press(1, f"rs:{q.id}:1", username="agent1"))  # hal bo'ldi — to'xtaydi
        q.refresh_from_db()
        self.assertEqual((q.resolution, q.next_ask_at), ("yes", None))

    def test_silent_asker_keeps_being_followed_up(self):
        q = self.answered()
        for minutes in (61, 182, 423):
            resolution.followups(self.tg, now=NOON + dt.timedelta(minutes=minutes))
        q.refresh_from_db()
        self.assertIsNotNone(q.next_ask_at)  # savol ochiq qolib ketmaydi — xodimdan so'rash davom etadi
        admin = [m for m in self.tg.sent if m["chat"] == 555 and "ochiq qolmoqda" in m["text"]]
        self.assertEqual(len(admin), 1)


class OwnerApiTests(PeopleBase):
    def test_owners_and_entry_responsible(self):
        e = Entry.objects.create(kind=Entry.FAQ, title="Marshrut", answer="x", responsible=self.pt, status=Entry.NEW)
        self.login("viewer")
        owners = self.call("get", "support/owners/").json()
        pt = next(o for o in owners if o["name"] == "Pro-target")
        self.assertEqual(set(pt["telegram"]), {"eldar_t", "guzel_t"})
        r = self.call("get", "support/entries/?status=new&limit=20&offset=0").json()
        row = next(x for x in r["results"] if x["id"] == e.id)
        self.assertEqual((row["responsible_name"], set(row["responsible_tg"])), ("Pro-target", {"eldar_t", "guzel_t"}))
        self.login("admin")
        r = self.call("patch", f"support/entries/{e.id}/", {"responsible": self.said.id})
        self.assertEqual((r.status_code, r.json()["responsible_tg"]), (200, ["said_t"]))


class DrillTests(OpenBase):
    def test_drill_lists_exactly_what_analytics_counts(self):
        off = Group.objects.create(bot=self.bot, chat_id=-200, title="VAZIFALAR", in_analytics=False)
        mk = Message.objects.create
        rows = [(self.g, "live", Message.ANSWERED, "ai", "yes"), (self.g, "live", Message.ANSWERED, "staff", "asked"),
                (self.g, "live", Message.ESCALATED, "", "no"), (self.g, "live", Message.ANSWERED, "react", "work"),
                (self.g, "live", Message.ESCALATED, "", ""), (self.g, "history", Message.ANSWERED, "staff", "asked"),
                (off, "live", Message.ANSWERED, "ai", "asked"), (self.g, "live", Message.CLOSED, "dup", "asked"),
                (self.g, "live", Message.IGNORED, "", "")]
        for i, (g, src, st, stage, res) in enumerate(rows):
            mk(bot=self.bot, group=g, chat_id=g.chat_id, message_id=100 + i, kind="question", text=f"q{i}", source=src,
               status=st, stage=stage, resolution=res, answered_by="bot" if stage == "ai" else "")
        self.login("viewer")
        a = self.call("get", "support/analytics/?days=1").json()
        drill = {k: len(self.call("get", f"support/messages/?drill={k}&days=1").json())
                 for k in ("total", "bot", "staff", "unanswered", "open", "yes", "no", "work", "asked", "unknown")}
        s, r = a["summary"], a["resolution"]
        self.assertEqual(drill["total"], a["questions"])
        self.assertEqual((drill["bot"], drill["staff"], drill["unanswered"], drill["open"]),
                         (s["bot"], s["staff"], s["unanswered"], s["open"]))
        self.assertEqual((drill["yes"], drill["no"], drill["work"], drill["asked"], drill["unknown"]),
                         (r["yes"], r["no"], r["work"], r["asked"], r["unknown"]))
        self.assertEqual((drill["total"], drill["asked"]), (5, 1))
