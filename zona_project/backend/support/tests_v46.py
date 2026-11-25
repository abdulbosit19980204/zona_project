"""Siyrak ekran: rasm o'xshashligi ekrandagi matnga zid bo'lsa — rasmga ishonilmaydi; standart javob AI'siz, aynan o'zi."""
import random
from unittest import mock

from django.test import TestCase

from . import ai_review, engine
from .engine import Decision
from .models import AIJob, Entry, Settings

THROTTLED = dict(kind=Entry.TEMPLATE, status=Entry.APPROVED,
                 title="PRBC: «Request was throttled» — kirish vaqtincha cheklangan",
                 triggers=["request was throttled", "was throttled", "expected available in"],
                 questions=["Не удалось войти Request was throttled. Expected available in 16 seconds"],
                 answer="PRBC serveri so'rovlarni vaqtincha cheklayapti. Kuting va qayta urining.")
AWAIT = dict(kind=Entry.TEMPLATE, status=Entry.APPROVED,
             title="PRBC: «Tasdiq kutilmoqda» — hisobni administrator faollashtirishi kerak",
             triggers=["tasdiq kutilmoqda", "awaiting approval", "administrator hisobingizni faollashtiradi"],
             answer="Faollashtirish uchun yozing:\n1. Ism Familiya\n2. Telefon raqam\n3. Region kodi (masalan, Toshkent — K1)")
OCR = "x PRBC 52 :\nTasdiq kutilmoqda\nв © 4"


class SparseScreenTests(TestCase):
    def test_image_match_rejected_when_screen_text_is_unrelated(self):
        thr = Entry.objects.create(**THROTTLED)
        d = engine.decide("", images=[(thr, 73, 0)], text="", ocr=OCR)
        self.assertFalse(d.entry is not None and d.entry.pk == thr.pk)  # throttled javobi berilmaydi
        self.assertTrue(engine.ocr_contradicts(thr, OCR))

    def test_taught_screen_answers_from_text(self):
        thr = Entry.objects.create(**THROTTLED)
        aw = Entry.objects.create(**AWAIT)
        d = engine.decide("", images=[(thr, 73, 0)], text="", ocr=OCR)
        self.assertEqual((d.entry.pk, d.stage), (aw.pk, "template"))
        self.assertIn("Region kodi", d.text)
        d2 = engine.decide("", images=[(thr, 73, 0)], text="", ocr="PRBC\nAwaiting approval\nYou've joined your organization")
        self.assertEqual(d2.entry.pk, aw.pk)

    def test_image_match_kept_when_text_agrees_or_screen_is_dense(self):
        thr = Entry.objects.create(**THROTTLED)
        self.assertFalse(engine.ocr_contradicts(thr, "Не удалось войти\nRequest was throttled. Expected available in 9 seconds"))
        self.assertFalse(engine.ocr_contradicts(thr, ""))  # matn o'qilmadi — rasm hal qiladi
        self.assertFalse(engine.ocr_contradicts(thr, "PRBC 4"))  # bitta so'z — baho berib bo'lmaydi
        dense = " ".join(f"soz{i}" for i in range(30))
        self.assertFalse(engine.ocr_contradicts(thr, dense))  # ko'p matnli ekran — OCR shovqini, rasm ishonchliroq
        faq = Entry.objects.create(kind=Entry.FAQ, status=Entry.APPROVED, title="Vapwe iwlamayapti", answer="x")
        self.assertFalse(engine.ocr_contradicts(faq, OCR))  # faqat shablonlar tekshiriladi
        d = engine.decide("", images=[(thr, 80, 0)], text="", ocr="Request was throttled")
        self.assertEqual(d.entry.pk, thr.pk)


class StrictTemplateTests(TestCase):
    def test_template_answer_is_exact_no_ai_variant_or_opener(self):
        s = Settings.load()
        s.answer_variety = True
        e = Entry.objects.create(**AWAIT, variants=[{"uz": "AI qayta yozgan matn", "ru": ""}])
        d = Decision("template", e, 95, e.answer, False)
        self.assertEqual({engine.vary(d, "uz", s, random.Random(i)) for i in range(30)}, {e.answer})
        img = Decision("image", e, 80, e.answer, False)
        self.assertEqual(engine.vary(img, "uz", s), e.answer)
        faq = Entry.objects.create(kind=Entry.FAQ, status=Entry.APPROVED, title="T", answer="Javob",
                                   variants=[{"uz": "Variant", "ru": ""}])
        outs = {engine.vary(Decision("faq", faq, 90, "Javob", False), "uz", s, random.Random(i)) for i in range(40)}
        self.assertGreater(len(outs), 1)  # savol-javoblar avvalgidek turlicha

    def test_variants_not_written_for_templates(self):
        Entry.objects.create(**AWAIT)
        job = AIJob.objects.create(kind=AIJob.VARIANTS, params={"limit": 25})
        with mock.patch("support.ai_review._run", return_value={"items": []}) as run:
            ai_review.write_variants(job)
        run.assert_not_called()  # yagona yozuv shablon — AI chaqirilmadi
