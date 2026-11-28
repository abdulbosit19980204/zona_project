"""AI'siz semantik qidiruv (support.semantic): indeks, qidiruv, holdout, chegara, engine bosqichi — soxta embedder bilan
(haqiqiy model faqat serverda; bu yerda numpy/onnxruntime shart emas)."""
import math
import zlib

from . import engine, semantic
from .models import Entry, Message, Settings
from .tests_controls import ControlsBase


def fake_embed(texts, dim=256):
    """Harf uchliklari xeshi — o'xshash matnlar yaqin vektor."""
    out = []
    for t in texts:
        v = [0.0] * dim
        s = f"  {t.lower()}  "
        for i in range(len(s) - 2):
            v[zlib.crc32(s[i:i + 3].encode()) % dim] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


class SemanticTests(ControlsBase):
    def setUp(self):
        super().setUp()
        semantic.set_embedder(fake_embed)
        self.addCleanup(semantic.set_embedder, None)
        Settings.load()
        Settings.objects.update(ai_enabled=False)
        self.geo = Entry.objects.create(kind=Entry.FAQ, title="Nuqta joylashuvidan uzoqda deb tashrif qabul qilinmayapti",
                                        questions=["lokatsiya uzoq deyapti", "uzoqdasiz deyapti"], answer="Aniq joylashuvni yoqing",
                                        status=Entry.APPROVED)
        self.promo = Entry.objects.create(kind=Entry.FAQ, title="Aksiya yoki skidka chiqmayapti",
                                          questions=["skidka chiqmayapti", "aksiya ishlamayapti"], answer="Limitni tekshiring",
                                          status=Entry.APPROVED)

    def test_index_and_search(self):
        rows = semantic.ensure_index()
        self.assertIn((self.geo.pk, "lokatsiya uzoq deyapti"), rows)
        top = semantic.search("Assalomu alaykum, lokatsiyam uzoq deyapti nima qilay")
        self.assertEqual(top[0][0], self.geo.pk)
        self.assertGreater(top[0][1], 0.5)
        ex = semantic.search("skidka chiqmayapti", exclude=["skidka chiqmayapti"])
        self.assertLess(ex[0][1], 0.999)                           # o'zi bilan solishtirilmadi

    def test_confirmed_bot_answers_are_indexed(self):
        Message.objects.create(bot=self.bot, chat_id=-1, message_id=1, kind=Message.QUESTION, entry=self.promo,
                               text="Klientga 15% skidka bermayapti tekshiring", resolution=Message.YES)
        Message.objects.create(bot=self.bot, chat_id=-1, message_id=2, kind=Message.QUESTION, entry=self.promo,
                               text="Bu javob xato edi aksiya", resolution=Message.YES, review="wrong")
        texts = [t for e, t in semantic.ensure_index() if e == self.promo.pk]
        self.assertIn("Klientga 15% skidka bermayapti tekshiring", texts)
        self.assertNotIn("Bu javob xato edi aksiya", texts)

    def test_engine_stage_off_by_default_then_on(self):
        semantic.ensure_index()
        q = "lokatsiyam uzoqda deb vizit ochilmayapti"
        d = engine.decide(q, "uz", live=False)
        self.assertFalse(d is not None and d.entry == self.geo and "semantik" in d.note)
        Settings.objects.update(semantic_enabled=True, semantic_threshold=40)
        d = engine.decide(q, "uz", live=False)
        self.assertEqual((d.entry, d.stage, d.needs_human), (self.geo, "faq", False))
        self.assertIn("semantik", d.note)
        Settings.objects.update(semantic_threshold=99)
        d = engine.decide(q, "uz", live=False)
        self.assertFalse(d is not None and "semantik" in (d.note or ""))

    def test_forced_and_tune(self):
        semantic.ensure_index()
        with semantic.forced(40):
            d = engine.decide("skidkalar chiqmay qoldi klientda", "uz", live=False)
        self.assertEqual(d.entry, self.promo)
        rows = semantic.tune(pairs=[("skidkalar chiqmay qoldi", self.promo.pk), ("lokatsiyam uzoq", self.geo.pk)],
                             thresholds=[0.1, 0.99], margins=[0.0])
        self.assertEqual(rows[0]["total"], 2)
        self.assertEqual(rows[0]["correct"], 2)
        self.assertEqual(rows[0]["false_pos"], 100)                # to'g'ri yozuv yo'qdek — qolgan yozuv xato javob
        self.assertEqual(rows[0]["mixed"], 50)
        self.assertEqual(rows[1]["answered"], 0)
        self.assertIsNone(semantic.best(rows))

    def test_margin_between_two_close_entries(self):
        semantic.ensure_index()
        top = semantic.search("skidka chiqmayapti", k=2)
        self.assertEqual(top[0][0], self.promo.pk)
        self.assertEqual(semantic.decide_top(top, 0.1, 0.0)[0], self.promo.pk)
        gap = top[0][1] - top[1][1]
        self.assertIsNone(semantic.decide_top(top, 0.1, gap + 0.01))   # ikkilanish — javob yo'q
        self.assertIsNone(semantic.decide_top(top, top[0][1] + 0.01, 0.0))
        with semantic.forced(10, margin=gap + 0.01):
            d = engine.decide("skidka chiqmayapti", "uz", live=False)
        self.assertFalse(d is not None and "semantik" in (d.note or ""))

    def test_forced_excludes_own_text(self):
        """Baholashda savolning o'zi indeksda bo'lsa — o'zi bilan solishtirilmaydi (aks holda o'xshashlik 1.00)."""
        Message.objects.create(bot=self.bot, chat_id=-1, message_id=5, kind=Message.QUESTION, entry=self.geo,
                               text="Zakaz ketmay qoldi programma qotdi", resolution=Message.YES)
        semantic.ensure_index()
        self.assertGreater(semantic.search("Zakaz ketmay qoldi programma qotdi", k=1)[0][1], 0.99)
        with semantic.forced(99, margin=0.0):
            d = engine.decide("Zakaz ketmay qoldi programma qotdi", "uz", live=False)
        self.assertFalse(d is not None and "semantik" in (d.note or ""))

    def test_unavailable_or_meaningless_is_skipped(self):
        Settings.objects.update(semantic_enabled=True, semantic_threshold=10)
        semantic.ensure_index()
        d = engine.decide("Assalomu alaykum", "uz", live=False)
        self.assertTrue(d is None or d.entry is None)
        semantic.set_embedder(None)
        self.assertEqual(engine.semantic_decision("lokatsiya uzoq deyapti", "uz", [self.geo], Settings.load(),
                                                  lambda e: []) is None, not semantic.available())
