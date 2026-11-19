"""O'z-o'zini o'qitish va tezlik tuzatishlari (fayl yuklash qotmasligi, yuborish navbati boshqa chatlarni to'smasligi)."""
import io
import threading
import time
from unittest import mock

from django.utils import timezone

from zona.models import Department, Member

from . import selflearn
from . import telegram as T
from .models import AIJob, Entry, Group, Message, Settings, TgUser
from .tests import group_msg
from .tests_v6 import FlowBase


class SelfLearningTests(FlowBase):
    def setUp(self):
        super().setUp()
        Settings.load()
        self.e = Entry.objects.create(kind=Entry.FAQ, title="Parolni tiklash", answer="Profil → Parolni tiklash.",
                                      questions=["parolni unutdim"], status=Entry.APPROVED)
        self.g = Group.objects.create(bot=self.bot, chat_id=-100, title="G")
        self.u = TgUser.objects.create(tg_id=5, name="Agent")

    def q(self, mid, text, **kw):
        return Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=mid, user=self.u, text=text,
                                      status=Message.ANSWERED, answered_by="bot", entry=self.e, **kw)

    def test_tick_learns_new_phrasing_but_not_disputed_ones(self):
        ok = self.q(1, "akkaunt parolini esdan chiqardim qanday kiraman")
        bad = self.q(2, "parol tiklash tugmasi ishlamayapti umuman", feedback=-1)
        Message.objects.filter(pk__in=[ok.pk, bad.pk]).update(created_at=timezone.now() - timezone.timedelta(hours=2))
        self.assertEqual(selflearn.tick(), 1)
        self.e.refresh_from_db()
        self.assertIn("akkaunt parolini esdan chiqardim qanday kiraman", self.e.questions)
        self.assertNotIn("parol tiklash tugmasi ishlamayapti umuman", self.e.questions)
        self.assertEqual(selflearn.tick(), 0)  # qayta ko'rilmaydi

    def test_like_adds_variant_immediately(self):
        q = self.q(3, "parolni qayta tiklash kerak edi yordam")
        q.feedback = 1
        selflearn.on_feedback(q)
        self.e.refresh_from_db()
        self.assertIn("parolni qayta tiklash kerak edi yordam", self.e.questions)

    def test_staff_correction_queues_ai_improvement(self):
        dep = Department.objects.create(name="IT s")
        lead = Member.objects.create(name="Lead", role="r", department=dep, level="LEAD", telegram="lead1")
        staff = TgUser.objects.create(tg_id=77, name="Lead", username="lead1", member=lead)
        self.q(10, "parolni unutdim")
        with mock.patch("zona.ai.service.status", return_value={"support": True}):
            self.h().handle(group_msg(11, 77, "Parolni faqat supervayzer tiklaydi, shu sababli unga murojaat qilish kerak.", username="lead1", reply_to=10))
        job = AIJob.objects.get()
        self.assertEqual((job.params["ids"], job.params["auto"]), ([self.e.id], True))
        self.assertIn("supervayzer", job.params["correction"]["staff"])

    def test_trusted_staff_new_answer_is_approved(self):
        dep = Department.objects.create(name="IT t")
        lead = Member.objects.create(name="Lead2", role="r", department=dep, level="L3", telegram="lead2")
        TgUser.objects.create(tg_id=78, name="Lead2", username="lead2", member=lead)
        with mock.patch("support.runner.ocr.read_text", return_value=""):
            h = self.h()
            h.handle(group_msg(20, 5, "Kassa apparati chek chiqarmayapti nima qilish kerak"))
            h.handle(group_msg(21, 78, "Kassani o'chirib yoqing, keyin 1C'da smenani qayta oching.", username="lead2", reply_to=20))
        e = Entry.objects.filter(answer__startswith="Kassani").first()
        self.assertIsNotNone(e)
        self.assertEqual(e.status, Entry.APPROVED)


class FastPathTests(FlowBase):
    def test_download_reads_exact_size_without_waiting_for_close(self):
        class Slow(io.BytesIO):
            def read(self, n=-1):
                if self.tell() >= len(self.getvalue()):
                    time.sleep(5)  # server ulanishni yopmay ushlab turadi
                return super().read(n)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        c = T.Client("1:x")
        with mock.patch.object(c, "call", return_value={"file_size": 10, "file_path": "a.jpg"}), \
                mock.patch("support.telegram.urllib.request.urlopen", return_value=Slow(b"0123456789")):
            t0 = time.time()
            self.assertEqual(c.download("f"), b"0123456789")
            self.assertLess(time.time() - t0, 1)

    def test_throttle_does_not_block_other_chats(self):
        c = T.Client("1:x")
        c._throttle(1)
        done = {}

        def same_chat():
            c._throttle(1)
            done["same"] = time.time()

        def other_chat():
            c._throttle(2)
            done["other"] = time.time()
        t0 = time.time()
        a = threading.Thread(target=same_chat)
        a.start()
        time.sleep(0.05)
        b = threading.Thread(target=other_chat)
        b.start()
        a.join()
        b.join()
        self.assertLess(done["other"] - t0, 0.5)  # boshqa chat 1.2 s kutib qolmadi
        self.assertGreater(done["same"] - t0, 1.0)
