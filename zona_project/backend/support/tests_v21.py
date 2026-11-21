"""Bitta mavzu — bitta suhbat: ketma-ket xabarlar (lokatsiya, rasmlar, "hali ham") ochiq savolga biriktiriladi;
yangi savol faqat aniq belgisi bilan; bot javobidan keyingi davomga butun suhbat bilan qayta javob; tezlik sozlamalari."""
from unittest import mock

from django.utils import timezone

from zona.models import Department, Member

from . import conversation, engine
from .models import Entry, Message, Settings
from .telegram import Client
from .tests import group_msg
from .tests_v6 import FlowBase

PROBLEM = "Do'konning lokatsiyasi xaritada noto'g'ri ko'rsatilyapti"


def location(mid, uid, lat=41.311081, lon=69.240562):
    m = group_msg(mid, uid, "")
    m["message"].pop("text")
    m["message"]["location"] = {"latitude": lat, "longitude": lon}
    return m


class ThreadBase(FlowBase):
    def setUp(self):
        super().setUp()
        Settings.load()
        Settings.objects.update(thread_window=15, escalation_ack=True)

    def escalated(self, mid=10, uid=1):
        self.h().handle(group_msg(mid, uid, PROBLEM))
        q = Message.objects.get(message_id=mid)
        self.assertEqual(q.status, Message.ESCALATED)
        return q

    def questions(self):
        return Message.objects.filter(kind=Message.QUESTION).count()


class FollowupTests(ThreadBase):
    def test_location_photos_and_more_text_join_the_open_question(self):
        q = self.escalated()
        sent = len(self.tg.sent)
        h = self.h()
        h.handle(location(11, 1))
        h.handle(group_msg(12, 1, "", photo=True))
        h.handle(group_msg(13, 1, "", photo=True))
        h.handle(group_msg(14, 1, "hali ham shunday turibdi"))
        self.assertEqual(self.questions(), 1)  # bitta mavzu — bitta savol
        infos = list(Message.objects.filter(kind=Message.INFO, question=q).order_by("message_id"))
        self.assertEqual([m.message_id for m in infos], [11, 12, 13, 14])
        self.assertIn("maps.google.com/?q=41.311081,69.240562", infos[0].text)
        self.assertEqual(len(self.tg.sent), sent)  # bot har bir xabarga qayta "qabul qilindi" yozmaydi
        ctx = conversation.context(q)
        self.assertIn(PROBLEM, ctx)
        self.assertIn("📍 Lokatsiya", ctx)
        self.assertIn("hali ham shunday", ctx)

    def test_greeting_starts_a_new_question(self):
        self.escalated()
        self.h().handle(group_msg(11, 1, "Assalomu alaykum, klient qo'shishda STIR xato deb chiqyapti"))
        self.assertEqual(self.questions(), 2)

    def test_explicit_new_question_marker(self):
        self.escalated()
        self.h().handle(group_msg(11, 1, "Yana bir savol: zakaz qanday bekor qilinadi"))
        self.assertEqual(self.questions(), 2)

    def test_photo_with_its_own_caption_is_a_new_question(self):
        self.escalated()
        self.h().handle(group_msg(11, 1, "SR1 Navoi perechisleniya qo'shib bering", photo=True))
        self.assertEqual(self.questions(), 2)

    def test_other_people_are_separate(self):
        self.escalated(uid=1)
        self.h().handle(group_msg(11, 2, "hali ham shunday turibdi xaritada"))
        self.assertFalse(Message.objects.filter(kind=Message.INFO).exists())

    def test_window_expired_means_new_conversation(self):
        q = self.escalated()
        Message.objects.filter(pk=q.pk).update(created_at=timezone.now() - timezone.timedelta(minutes=40))
        self.h().handle(group_msg(11, 1, "Kassada chek chiqmayapti nima qilish kerak"))
        self.assertEqual(self.questions(), 2)

    def test_disabled_window_keeps_old_behaviour(self):
        Settings.objects.update(thread_window=0)
        self.escalated()
        self.h().handle(group_msg(11, 1, "Kassada chek chiqmayapti nima qilish kerak"))
        self.assertEqual(self.questions(), 2)

    def test_lonely_location_is_not_a_question(self):
        self.h().handle(location(20, 1))
        self.assertEqual(self.questions(), 0)

    def test_staff_answer_then_user_continues_reopens(self):
        q = self.escalated()
        it = Department.objects.create(name="IT t")
        Member.objects.create(name="Test Xodim", role="r", department=it, telegram="test_op")
        self.h().handle(group_msg(11, 2, "Xaritada manzilni qayta saqlang, keyin sinxronlang", username="test_op", reply_to=10))
        q.refresh_from_db()
        self.assertEqual(q.status, Message.ANSWERED)
        self.h().handle(group_msg(12, 1, "qildim lekin baribir eski joyda ko'rsatyapti"))
        q.refresh_from_db()
        self.assertEqual(q.status, Message.ESCALATED)  # odam hali yozyapti — savol yana javob kutadi
        self.assertEqual(self.questions(), 1)


class ReanswerTests(ThreadBase):
    def answered(self):
        self.h().handle(group_msg(40, 1, "Nuqta отправлена на модерацию"))
        q = Message.objects.get(message_id=40)
        self.assertEqual((q.status, q.answered_by), (Message.ANSWERED, "bot"))
        return q

    def test_followup_after_bot_answer_gets_one_answer_with_the_whole_conversation(self):
        q = self.answered()
        d = engine.Decision("ai", None, 90, "Unda moderatorga yozing: nuqta 24 soatda tasdiqlanadi.", False, [])
        with mock.patch("support.engine.followup", return_value=d) as f, mock.patch("support.engine.allowed", return_value=True):
            self.h().handle(group_msg(41, 1, "Нету его, там только старые точки показывает"))
        self.assertEqual(self.questions(), 1)
        history = f.call_args[0][2]
        self.assertIn("Nuqta отправлена на модерацию", history)
        self.assertIn("Нету его", history)
        last = self.tg.sent[-1]
        self.assertEqual(last["reply_to"], 41)
        self.assertIn("moderatorga", last["text"])
        q.refresh_from_db()
        self.assertEqual(q.answer_text, d.text)
        self.assertEqual(q.status, Message.ANSWERED)

    def test_second_followup_goes_to_a_specialist(self):
        q = self.answered()
        d = engine.Decision("ai", None, 90, "Boshqa javob matni shu yerda.", False, [])
        with mock.patch("support.engine.followup", return_value=d), mock.patch("support.engine.allowed", return_value=True):
            self.h().handle(group_msg(41, 1, "Нету его, там только старые точки показывает"))
            self.h().handle(group_msg(42, 1, "всё равно не видно нового магазина в списке"))
        q.refresh_from_db()
        self.assertEqual(q.status, Message.ESCALATED)
        self.assertIn("специалист", self.tg.sent[-1]["text"])
        self.assertEqual(self.questions(), 1)

    def test_ai_unsure_escalates(self):
        q = self.answered()
        with mock.patch("support.engine.followup", return_value=engine.Decision("", None, 0, "", True, [])):
            self.h().handle(group_msg(41, 1, "Нету его, там только старые точки показывает"))
        q.refresh_from_db()
        self.assertEqual(q.status, Message.ESCALATED)

    def test_short_ok_is_just_saved(self):
        q = self.answered()
        n = len(self.tg.sent)
        self.h().handle(group_msg(41, 1, "ok"))
        self.assertEqual(len(self.tg.sent), n)
        q.refresh_from_db()
        self.assertEqual(q.status, Message.ANSWERED)


class StaffLooseTests(ThreadBase):
    def test_staff_message_without_reply_links_to_the_only_waiting_question(self):
        q = self.escalated()
        it = Department.objects.create(name="IT t")
        Member.objects.create(name="Test Xodim", role="r", department=it, telegram="test_op")
        before = Entry.objects.count()
        self.h().handle(group_msg(11, 2, "Manzilni tekshirdim, hozir to'g'riladim", username="test_op"))
        a = Message.objects.get(message_id=11)
        self.assertEqual((a.kind, a.question_id), (Message.STAFF, q.pk))
        q.refresh_from_db()
        self.assertEqual(q.status, Message.ANSWERED)
        self.assertEqual(Entry.objects.count(), before)  # taxminiy bog'lanish — o'rganilmaydi

    def test_two_people_waiting_is_ambiguous(self):
        self.escalated(10, 1)
        self.escalated(11, 3)
        it = Department.objects.create(name="IT t")
        Member.objects.create(name="Test Xodim", role="r", department=it, telegram="test_op")
        self.h().handle(group_msg(12, 2, "Manzilni tekshirdim, hozir to'g'riladim", username="test_op"))
        self.assertFalse(Message.objects.filter(message_id=12).exists())


class SpeedTests(FlowBase):
    def test_short_long_poll_and_timeouts(self):
        c = Client("1:x")
        self.assertLessEqual(c.timeout, 12)
        with mock.patch.object(c, "call", return_value=[]) as call:
            c.get_updates(5)
        self.assertLessEqual(call.call_args.kwargs["timeout"], 15)

    def test_network_retry_is_fast(self):
        import time
        c = Client("1:x")
        calls = []

        def boom(*a, **k):
            calls.append(1)
            raise TimeoutError("timed out")
        with mock.patch("urllib.request.urlopen", side_effect=boom):
            t = time.monotonic()
            with self.assertRaises(Exception):
                c.call("getMe", retries=2)
        self.assertEqual(len(calls), 3)
        self.assertLess(time.monotonic() - t, 2.5)
