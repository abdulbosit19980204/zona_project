"""Ma'lumot ekrani ("Торговая точка ... отправлена на модерацию!") + imzoda iltimos ("Кушиб беринг Навоий СРЗ"):
bot xodimga uzatmaydi — moderatsiya standart javobini beradi (nuqtani Pro-target tasdiqlaydi, o'zi qo'shiladi)."""
from unittest import mock

from django.test import TestCase

from . import engine, ocr
from .models import Entry, Message, Settings
from .tests import group_msg
from .tests_v6 import FlowBase

# prod'dagi aniq OCR (2026-11-26, BIC-SILVER-СХЗ ROP): "на" va "модерацию" alohida qatorda
OCR = ("09:52 ® all ©\nНовая торговая точка\nТорговая точка Прооо отправлена на\nмодерацию!\n"
       "После прохождения модерации вы сможете\nделать заказы для точки.\nШ O &lt;")
CAPTION = "Кушиб беринг\nНавоий СР3"


class InfoScreenTests(TestCase):
    def setUp(self):
        Settings.load()
        Settings.objects.update(ai_enabled=False, ai_primary=False, faq_threshold=60)
        self.moder = Entry.objects.create(
            kind=Entry.TEMPLATE, title="ProTarget: yangi nuqta moderatsiyaga yuborilgan", status=Entry.APPROVED, auto_close=30,
            triggers=["на модерацию", "отправлена на модерацию", "moderatsiyaga", "moderatsiya"],
            answer="Nuqta moderatsiyaga yuborilgan — bu normal holat.", answer_ru="Точка отправлена на модерацию — это нормально.")
        self.cash = Entry.objects.create(kind=Entry.FAQ, title="Klientga perechisleniya (bank o'tkazmasi) qo'shish",
                                         questions=["perechisleniya qo'shib bering", "bank o'tkazmasi qo'shish"],
                                         answer="Perechisleniya supervayzer orqali qo'shiladi.", status=Entry.APPROVED)

    def decide(self, text, ocr=OCR, images=None):
        return engine.decide(text + "\n" + ocr, "ru", text=text, ocr=ocr, images=images)

    def test_request_caption_gets_moderation_answer(self):
        for text in ["Кушиб беринг\nНавоий СР3", "Кушиб беринг Навоий СРЗ", "Салом алейкум шуни кушип беринг", "Qo'shib bering Navoiy SRZ", "Добавьте пожалуйста точку Самарканд",
                     "Tasdiqlab bering srochno Buxoro filial"]:
            d = self.decide(text)
            self.assertEqual(d.entry, self.moder, text)
            self.assertFalse(d.needs_human, text)
            self.assertIn("модерацию", d.text)

    def test_by_image_hash_without_ocr(self):
        d = self.decide("Кушиб беринг Навоий СРЗ", ocr="", images=[(self.moder, 88, 0)])
        self.assertEqual((d.stage, d.entry), ("image", self.moder))

    def test_clear_other_question_still_wins(self):
        d = self.decide("SR1 Navoi perechisleniya qo'shib bering")
        self.assertEqual(d.entry, self.cash)

    def test_non_info_screen_unchanged(self):
        Entry.objects.filter(pk=self.moder.pk).update(auto_close=0)
        d = self.decide("Кушиб беринг Навоий СРЗ")
        self.assertNotEqual(d.entry, self.moder)


class InfoScreenFlowTests(FlowBase):
    """To'liq oqim: rasm + imzo bitta xabarda — guruhga moderatsiya javobi, xodimga uzatilmaydi."""

    def test_photo_with_request_caption_is_answered(self):
        Entry.objects.filter(title="ProTarget: yangi nuqta moderatsiyaga yuborilgan").update(auto_close=30)
        Settings.objects.update(ai_enabled=False, ai_primary=False)
        with mock.patch("support.runner.ocr.read_text", return_value=OCR):
            self.h().handle(group_msg(1, 10, CAPTION, photo=True))
        q = Message.objects.get(kind=Message.QUESTION)
        self.assertEqual(q.status, Message.ANSWERED)
        self.assertEqual(q.entry.title, "ProTarget: yangi nuqta moderatsiyaga yuborilgan")
        sent = [x["text"] for x in self.tg.sent if x["chat"] == -100]
        self.assertEqual(len(sent), 1)
        self.assertNotIn("Ответит", sent[0])


class HomoglyphTests(TestCase):
    """OCR ruscha "на" ni lotincha "Ha" deb o'qiydi (prod, 2026-11-25) — shart topilishi uchun kirillchaga aylantiriladi."""
    OCR_HA = ("11:32 © - $ ани GD\nНовая торговая точка\nТорговая точка BABAYEVA AMINA\nMUHAMMATOVNA отправлена Ha\n"
              "модерацию!\nПосле прохождения модерации вы сможете\nделать заказы для точки.\nв © «4")

    def test_fix_short_latin_lookalike_next_to_cyrillic(self):
        out = ocr.fix_homoglyphs(self.OCR_HA)
        self.assertIn("отправлена На\nмодерацию!", out)
        self.assertIn("BABAYEVA AMINA\nMUHAMMATOVNA", out)  # lotincha nom tegmaydi
        self.assertEqual(ocr.fix_homoglyphs("Token has been expired OK"), "Token has been expired OK")

    def test_stored_ocr_with_latin_ha_gets_moderation_answer(self):
        Settings.load()
        Settings.objects.update(ai_enabled=False, ai_primary=False, faq_threshold=60)
        moder = Entry.objects.create(kind=Entry.TEMPLATE, title="ProTarget: yangi nuqta moderatsiyaga yuborilgan",
                                     status=Entry.APPROVED, auto_close=30, answer="Moderatsiyada.",
                                     triggers=["на модерацию", "отправлена на модерацию", "moderatsiyaga", "moderatsiya"])
        text = "Салом алейкум шуни кушип беринг"
        d = engine.decide(text + "\n" + self.OCR_HA, "ru", text=text, ocr=self.OCR_HA)
        self.assertEqual((d.entry, d.needs_human), (moder, False))
