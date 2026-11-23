"""Toifa mas'uli: masalan, butun tizimda barcha aksiya savollari — operatorga (dasturchi/supervayzer emas);
o'rganilgan savollar mas'ul bilan saqlanadi."""
from zona.models import Department, Member

from . import engine, tasks
from .models import Entry, Message, Settings
from .runner import learn
from .tests_controls import ControlsBase


class OwnerTests(ControlsBase):
    def setUp(self):
        super().setUp()
        dep = Department.objects.create(name="Test bo'lim")
        self.op = Member.objects.create(name="TEST_OPERATOR", role="Operator", department=dep, telegram="test_op")
        self.sv = Member.objects.create(name="Supervayzerlar", role="Supervayzer", department=dep, is_team=True)
        self.dev = Member.objects.create(name="Dasturchilar jamoasi", role="Dasturchi", department=dep, is_team=True)
        Settings.load()
        Settings.objects.update(category_owners={"promo": self.op.pk})

    def test_promo_question_goes_to_operator_not_supervisor(self):
        e = Entry.objects.create(kind=Entry.FAQ, title="Agentda aksiya ko'rinmayapti", questions=["aksiya chiqmayapti"],
                                 answer="Supervayzeringizga yozing", status=Entry.APPROVED, responsible=self.sv)
        d = engine.decide("Agentda aksiya chiqmayapti", "uz")
        self.assertEqual(d.entry, e)
        self.assertTrue(d.owner)
        self.assertEqual(d.responsible[0]["name"], "TEST_OPERATOR")
        self.assertFalse(engine.needs_supervisor(d))  # javobda "supervayzer" bo'lsa ham — supervayzer belgilanmaydi

    def test_other_categories_keep_their_owner(self):
        Entry.objects.create(kind=Entry.FAQ, title="Marshrutga klient qo'shilmayapti", questions=["marshrut ochilmayapti"],
                             answer="1C da tekshiring", status=Entry.APPROVED, responsible=self.dev)
        d = engine.decide("marshrut ochilmayapti", "uz")
        self.assertFalse(d.owner)

    def test_task_assignee_is_operator(self):
        Settings.objects.update(tasks_enabled=True, task_members=[self.op.pk, self.dev.pk])
        e = Entry.objects.create(kind=Entry.FAQ, title="Yangi aksiya kerak", questions=["yangi aksiya kerak"], answer="x",
                                 status=Entry.APPROVED, responsible=self.dev, creates_task=True)
        q = Message(kind=Message.QUESTION, text="yangi aksiya kerak")
        d = engine.decide("yangi aksiya kerak", "uz")
        need, assignee, _reason = tasks.decide_task(q, d)
        self.assertEqual((need, assignee), (True, "test_op"))
        _ = e

    def test_learned_promo_candidate_gets_operator(self):
        q = Message.objects.create(bot=self.bot, chat_id=-1, message_id=1, kind=Message.QUESTION,
                                   text="Klientda skidka bermayapti, aksiya o'tmadi")
        entry, new = learn(q, "1C da aksiyani klientga biriktirdim, qayta sinxronlang", "Test Xodim")
        self.assertTrue(new)
        self.assertEqual(entry.responsible, self.op)

    def test_settings_api_validates(self):
        self.login("admin")
        r = self.call("patch", "support/settings/", {"category_owners": {"promo": self.op.pk, "nope": 1}})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Settings.load().category_owners, {"promo": self.op.pk})
        self.assertEqual(self.call("patch", "support/settings/", {"category_owners": {"promo": 999999}}).status_code, 400)
        self.call("patch", "support/settings/", {"category_owners": {}})
        self.assertIsNone(Settings.load().category_owners)


class ScreenTextBeatsLookalikeTests(ControlsBase):
    def test_ocr_trigger_of_another_template_wins_over_similar_screen(self):
        inactive = Entry.objects.create(kind=Entry.TEMPLATE, title="ProTarget: Inactive user account", triggers=["inactive user account"],
                                        answer="Akkaunt faol emas", answer_ru="Аккаунт неактивен", status=Entry.APPROVED)
        token = Entry.objects.create(kind=Entry.TEMPLATE, title="ProTarget: Token has been expired", triggers=["token has been expired"],
                                     answer="Ilovani to'liq yoping va qaytadan kiring.",
                                     answer_ru="Закройте приложение полностью и снова зайдите.", status=Entry.APPROVED)
        # rasm bo'yicha "Inactive" ga o'xshash (80%), lekin ekrandagi matn — "Token has been expired"
        d = engine.decide("", "ru", images=[(inactive, 80, 0)], text="", ocr="Визиты\nToken has been expired\nПопробовать снова")
        self.assertEqual((d.stage, d.entry), ("template", token))
        self.assertIn("Закройте приложение", d.text)
        # o'z ekrani — o'zi (matn ham shuni aytadi)
        d2 = engine.decide("", "ru", images=[(inactive, 80, 0)], text="", ocr="Inactive user account\nПопробовать снова")
        self.assertEqual(d2.entry, inactive)
