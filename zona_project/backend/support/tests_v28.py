"""Mantiqli javob: qizil xato yozuvi ustun; supervayzerga "supervayzeringizga yozing" demaslik; xodimning holat xabari
("Проверьте", "qayta tekshiring") bilim emas; guruh uzun javoblar bilan to'lmasin — javob yig'iladi, tugmalar ixcham."""
import datetime as dt
import io
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from zona.models import Department, Member, StaffPerson, StaffProject

from . import engine, ocr, review
from .models import Entry, Group, Message, Settings, TgUser
from .runner import learn
from .tests import group_msg
from .tests_v6 import FlowBase

RED = "Для данной ТТ не найдены активные маршруты доставки. Обратитесь к своему администратору"
SCREEN = ("Оформление заказа\nСпособ оплаты\nНаличными Терминал\nБезналичными\nРассрочка\nДоставка\nДоставщик\n"
          "Выберите доставщика\nДата доставки\nВыберите дату доставки\n" + RED + "\nСкидка -26 500 UZS")


def delivery_entry():
    return Entry.objects.create(
        kind=Entry.TEMPLATE, title="ProTarget: nuqta uchun yetkazib berish marshruti topilmadi", status=Entry.APPROVED,
        triggers=["активные маршруты доставки", "маршруты доставки не найдены"],
        answer="Nuqtaga yetkazib berish marshruti biriktirilmagan.\n1) Nuqta kodini yozing.\n2) So'rov Saidabrorga boradi.",
        answer_ru="Для точки не задан маршрут доставки.\n1) Напишите код ТТ.\n2) Запрос уходит Саидаброру.")


class StatusReplyTests(TestCase):
    def test_status_only_messages(self):
        for t in ["Проверьте", "Tekwiring", "Добрый день! Проверьте пожалуйста ещё раз", "Готово, прошу проверить",
                  "Qayta tekwiring, limit qowildi", "Можете проверить? На сегодняшний день закрепил", "Сейчас проверить",
                  "Assalomu aleykum. Qayta tekshiringchi", "ГОТОВ ПРОВЕРАЙТЕ", "Uzur, tekshiring"]:
            self.assertTrue(engine.status_reply(t), t)

    def test_real_instructions_are_not_status(self):
        for t in ["Перезайдите в приложение и проверьте", "programmadan chiqib qayta kirib tekshirib koring",
                  "В уведомлениях проверьте", "Assalomu aleykum. Programmani yopib qayta kiringchi",
                  "Кредитный лимит клиента исчерпан, нужна оплата долга — тогда заказ пройдёт",
                  "Aksiya faqat 10 ta blokdan keyin yonadi, savatni tekshiring"]:
            self.assertFalse(engine.status_reply(t), t)

    def test_named_staff_call_is_not_an_answer(self):
        dep = Department.objects.create(name="d")
        Member.objects.create(name="Eldar", role="r", department=dep)
        engine._NAMES["at"] = 0
        self.assertTrue(engine.not_an_answer("Eldar можете помочь"))
        self.assertTrue(engine.not_an_answer("Qayta tekwiring, limit qowildi"))
        self.assertFalse(engine.not_an_answer("Klientga limit 5 mln qo'shildi, zakazni qayta yuboring"))


class LearnFilterTests(FlowBase):
    def test_status_reply_is_not_learned_nor_used_as_example(self):
        q = Message.objects.create(bot=self.bot, chat_id=-100, message_id=5, kind=Message.QUESTION,
                                   text="Navoiy K1 aksiyani yoqib bering iltimos")
        entry, new = learn(q, "Qayta tekwiring, aksiya yoqildi", "Saidabror")
        self.assertIsNone(entry)
        staff = TgUser.objects.create(tg_id=77, name="S")
        Message.objects.create(bot=self.bot, chat_id=-100, message_id=6, kind=Message.STAFF, question=q, user=staff,
                               text="Добрый день! Проверьте пожалуйста ещё раз")
        Message.objects.create(bot=self.bot, chat_id=-100, message_id=7, kind=Message.STAFF, question=q, user=staff,
                               text="Aksiya 10 ta blokdan keyin avtomatik yonadi")
        engine._STAFF["key"] = None
        answers = [a for _q, a in engine.staff_examples("aksiyani yoqib bering", min_score=0)]
        self.assertIn("Aksiya 10 ta blokdan keyin avtomatik yonadi", answers)
        self.assertNotIn("Добрый день! Проверьте пожалуйста ещё раз", answers)

    def test_status_answer_from_kb_goes_to_responsible(self):
        dep = Department.objects.create(name="d")
        said = Member.objects.create(name="Saidabror", role="Operator", department=dep, telegram="said_t")
        Entry.objects.create(kind=Entry.FAQ, title="Aksiyani yoqib bering", questions=["aksiyani yoqib bering"],
                             answer="Qayta tekshiring", status=Entry.APPROVED, responsible=said)
        d = engine.decide("aksiyani yoqib bering", "uz", fast=True)
        self.assertTrue(d.needs_human)  # agentga "qayta tekshiring" yuborilmaydi — mas'ul belgilanadi
        self.assertEqual(d.responsible[0]["telegram"], ["said_t"])


class AlertTests(FlowBase):
    def setUp(self):
        super().setUp()
        self.delivery = delivery_entry()
        self.cashless = Entry.objects.create(
            kind=Entry.TEMPLATE, title="Buyurtmada «Безналичными» to'lov turini yoqish", status=Entry.APPROVED,
            triggers=["безналичными"], answer="Perechisleniya Saidabror yoqadi.")

    def test_red_text_wins_over_other_screen_words(self):
        raw = SCREEN
        d = engine.decide(raw, "ru", text="", ocr=SCREEN, alert=RED, fast=True)
        self.assertEqual((d.stage, d.entry.pk), ("template", self.delivery.pk))
        self.assertIn("qizil", d.note)

    def test_red_text_with_related_question_text(self):
        text = "Доставщик и дата даставкани танлаб булмаяпти куриб беринглар илтимос"
        d = engine.decide(text + "\n" + SCREEN, "ru", text=text, ocr=SCREEN, alert=RED, fast=True)
        self.assertEqual(d.entry.pk, self.delivery.pk)

    def test_explicit_text_template_still_wins(self):
        d = engine.decide("безналичными qo'shib bering\n" + SCREEN, "uz", text="безналичными qo'shib bering", ocr=SCREEN,
                          alert="Для данной ТТ не найдены точки", fast=True)
        self.assertEqual(d.entry.pk, self.cashless.pk)

    def test_photo_question_uses_red_text_end_to_end(self):
        Settings.objects.update(ocr_enabled=True, image_match=False, merge_window=0, progress_messages=False)
        with mock.patch("support.runner.ocr.read_text", return_value=SCREEN), \
                mock.patch("support.runner.ocr.red_text", return_value=RED) as red:
            self.h().handle(group_msg(1, 10, "", photo=True))
        red.assert_called_once()
        q = Message.objects.get(kind="question")
        self.assertEqual(q.alert_text, RED)
        self.assertEqual(q.entry_id, self.delivery.pk)


class RedTextImageTests(TestCase):
    def image(self, red=True):
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (600, 900), "white")
        d = ImageDraw.Draw(img)
        for y in range(100, 500, 40):
            d.text((20, y), "Оформление заказа Доставщик Наличными", fill=(30, 30, 30))
        d.rectangle((20, 780, 580, 840), fill=(220, 40, 40))  # qizil tugma (matn emas)
        if red:
            d.text((20, 600), "Для данной ТТ не найдены активные маршруты", fill=(225, 45, 45))
            d.text((20, 615), "доставки. Обратитесь к администратору", fill=(225, 45, 45))
        out = io.BytesIO()
        img.save(out, "PNG")
        return out.getvalue()

    def test_bands_find_red_lines_and_skip_buttons(self):
        bands = ocr.red_bands(ocr.red_mask(self.image()))
        self.assertEqual(len(bands), 1)
        self.assertTrue(590 <= bands[0][0] <= 605 and 620 <= bands[0][1] <= 640, bands)
        self.assertEqual(ocr.red_bands(ocr.red_mask(self.image(red=False))), [])

    def test_red_text_filters_labels(self):
        with mock.patch.object(ocr, "languages", return_value="rus"), \
                mock.patch.object(ocr, "_tesseract", return_value=RED):
            self.assertEqual(ocr.red_text(self.image()), RED)
        with mock.patch.object(ocr, "languages", return_value="rus"), \
                mock.patch.object(ocr, "_tesseract", return_value="Скидка на корзину"):
            self.assertEqual(ocr.red_text(self.image()), "")  # qizil yorliq — xato emas


class LeaderTests(FlowBase):
    def setUp(self):
        super().setUp()
        dep = Department.objects.create(name="d")
        self.sv_team = Member.objects.create(name="Supervayzerlar", role="Supervayzer", department=dep, is_team=True)
        self.entry = Entry.objects.create(kind=Entry.FAQ, title="Marshrutni o'zgartirish",
                                          questions=["как исправить маршруты", "marshrutni o'zgartirish"],
                                          answer="Bu savolni **Supervayzerlar** hal qiladi.",
                                          answer_ru="Этот вопрос решает **Supervayzerlar**.",
                                          status=Entry.APPROVED, responsible=self.sv_team)
        proj = StaffProject.objects.create(name="TEST_P")
        self.svr = StaffPerson.objects.create(project=proj, name="Testov Jasur Lazizovich", role="SVR")

    def test_username_and_first_name_link_supervisor(self):
        u = engine.identify(501, username="Testov010", name="Жасур")
        self.assertEqual(u.staff_person_id, self.svr.pk)
        self.assertTrue(engine.is_leader(u))
        self.assertIsNone(engine.identify(502, username="Ali77", name="Жасур").staff_person_id)  # bitta so'z — yo'q

    def test_supervisor_is_not_sent_to_supervisor(self):
        q = "как исправить маршруты"
        self.assertEqual(engine.decide(q, "ru", fast=True).entry.pk, self.entry.pk)  # agentga — odatdagidek
        self.assertIsNone(engine.decide(q, "ru", fast=True, leader=True))  # supervayzerga — AI kerak
        good = {"text": "Откройте маршрут агента в ProTarget и измените дни визита.", "confidence": 90,
                "needs_human": False, "reason": "r", "meta": {}}
        with mock.patch.object(engine, "ai_answer", return_value=good) as ai:
            d = engine.decide(q, "ru", leader=True, asker="Supervayzer")
        self.assertEqual((d.stage, d.needs_human), ("ai", False))
        self.assertIn("O'ZI SUPERVAYZER", ai.call_args.kwargs["asker"])
        bad = dict(good, text="Этот вопрос решает ваш супервайзер.")
        with mock.patch.object(engine, "ai_answer", return_value=bad):
            d = engine.decide(q, "ru", leader=True)
        self.assertTrue(d.needs_human)
        self.assertFalse(any(engine.SUPERVISOR_HINT.search(r["name"]) for r in d.responsible))


class CollapseTests(FlowBase):
    NOW = timezone.make_aware(dt.datetime(2026, 11, 23, 12, 0))

    def setUp(self):
        super().setUp()
        Settings.load()
        Settings.objects.update(collapse_after=3, feedback_buttons=True, review_button=True, answer_test_note=True)
        self.g = Group.objects.create(bot=self.bot, chat_id=-100, title="ROP")

    def q(self, html_text, minutes_ago=5, **kw):
        q = Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=5, kind=Message.QUESTION,
                                   source="live", status=Message.ANSWERED, answered_by="bot", bot_reply_id=50,
                                   answer_text="x", reply_html=html_text, lang="uz",
                                   answered_at=self.NOW - dt.timedelta(minutes=minutes_ago), **kw)
        Message.objects.filter(pk=q.pk).update(created_at=self.NOW - dt.timedelta(minutes=minutes_ago))
        return q

    LONG = ("@agent1, <b>💳 Perechisleniya</b>\n\nBu to'lov turi 1C'da yoqilgan bo'lsa ishlaydi.\n\n1. Klient kodini yozing."
            "\n2. So'rov <b>Saidabror</b>ga boradi.\n3. Yoqilgach, ilovani sinxronlang." + review.note_html("uz"))

    def test_buttons_are_one_compact_row(self):
        s = Settings.load()
        q = self.q(self.LONG)
        rows = review.buttons(q, s)
        self.assertEqual(len(rows), 1)
        self.assertEqual([b["text"] for b in rows[0]], ["👍", "👎", "⚠️ Xato"])

    def test_collapse_html(self):
        out = review.collapse_html(self.LONG)
        self.assertTrue(out.startswith("@agent1, <b>💳 Perechisleniya</b>\n<blockquote expandable>"))
        self.assertTrue(out.endswith("sinxronlang.</blockquote>"))
        self.assertNotIn("Avto-javob", out)  # test rejimi izohi yig'ilganda olib tashlanadi
        self.assertIsNone(review.collapse_html("@a, Qisqa javob."))
        self.assertIsNone(review.collapse_html(out))  # ikki marta yig'ilmaydi
        self.assertTrue(review.collapse_html("<b>bir\nikki</b>\n" + "x" * 300).startswith("<blockquote expandable>"))

    def test_collapse_due_after_minutes(self):
        early = self.q(self.LONG, minutes_ago=1)
        old = Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=6, kind=Message.QUESTION,
                                     source="live", status=Message.ANSWERED, bot_reply_id=60, reply_html=self.LONG,
                                     answered_at=self.NOW - dt.timedelta(minutes=5))
        short = Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=7, kind=Message.QUESTION,
                                       source="live", status=Message.ANSWERED, bot_reply_id=70, reply_html="@a, ok",
                                       answered_at=self.NOW - dt.timedelta(minutes=5))
        self.assertEqual(review.collapse_due(self.tg, now=self.NOW), 1)
        edit = self.tg.edits[-1]
        self.assertEqual(edit["id"], 60)
        self.assertIn("<blockquote expandable>", edit["text"])
        self.assertEqual(len(edit["buttons"]), 1)  # tugmalar saqlanadi (bitta qator)
        for m in (early, old, short):
            m.refresh_from_db()
        self.assertIsNone(early.collapsed_at)
        self.assertIsNotNone(old.collapsed_at)
        self.assertIsNotNone(short.collapsed_at)  # qisqa — tahrirlanmaydi, qayta tekshirilmaydi
        self.assertEqual(review.collapse_due(self.tg, now=self.NOW), 0)

    def test_disabled_and_hidden(self):
        self.q(self.LONG, answer_hidden=True)
        self.assertEqual(review.collapse_due(self.tg, now=self.NOW), 0)
        Settings.objects.update(collapse_after=0)
        Message.objects.update(answer_hidden=False)
        self.assertEqual(review.collapse_due(self.tg, now=self.NOW), 0)

    def test_fixed_answer_is_collapsed_later_again(self):
        q = self.q(self.LONG, collapsed_at=self.NOW)
        with mock.patch.object(timezone, "now", return_value=self.NOW):
            review.fix(q, "To'g'ri javob:\n1) birinchi qadam juda uzun matn bilan\n2) ikkinchi qadam\n3) uchinchi\n4) to'rt",
                       "admin", tg=self.tg)
        q.refresh_from_db()
        self.assertIsNone(q.collapsed_at)
        self.assertIn("Aniqlashtirilgan", q.reply_html)
        self.assertEqual(review.collapse_due(self.tg, now=self.NOW + dt.timedelta(minutes=4)), 1)

    def test_bot_answer_stores_html(self):
        Settings.objects.update(progress_messages=False)
        self.h().handle(group_msg(1, 10, "parolni unutdim, qanday tiklayman?"))
        q = Message.objects.get(kind="question")
        if q.status == Message.ANSWERED and q.answered_by == "bot":
            self.assertTrue(q.reply_html)
            self.assertIsNone(q.collapsed_at)
