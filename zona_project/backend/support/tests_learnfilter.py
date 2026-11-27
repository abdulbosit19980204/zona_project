"""O'rganish filtri: salomlashuv va mazmunsiz savollar ("Assalomu alaykum", "Нукус к3", "Тут тоже самое",
"@Guzel_Taipova", "Почему так ?") hamda aniq holatga yozilgan javoblar ("Готово", "отвязала, переподключите",
"Tuzatildi ✅", botning "Bu so'rovni … bajaradi") bilim bazasiga nomzod bo'lmaydi; standartga qo'shishda ham."""
from . import engine
from .dedupe import absorb
from .models import Entry, Message
from .runner import learn
from .tests_controls import ControlsBase

ANSWER = "Telefon sozlamalarida ProTarget uchun aniq joylashuvni yoqing, keyin qayta urinib ko'ring"


class LearnFilterTests(ControlsBase):
    def q(self, text, mid=1):
        return Message.objects.create(bot=self.bot, chat_id=-1, message_id=mid, kind=Message.QUESTION, text=text)

    def test_empty_questions_are_not_learned(self):
        for i, text in enumerate(["Assalomu alaykum", "Нукус к3", "Тут тоже самое", "@Guzel_Taipova", "Почему так ?",
                                  "Добрый день, почему так?", "Assalom aleykum yaxshimisiz"]):
            entry, new = learn(self.q(text, i + 1), ANSWER, "Guzel")
            self.assertIsNone(entry, text)
            self.assertFalse(new)
        self.assertFalse(Entry.objects.filter(status=Entry.NEW).exists())

    def test_real_question_is_learned(self):
        entry, new = learn(self.q("Lokatsiyani to'g'rilab bering"), ANSWER, "Guzel")
        self.assertTrue(new)
        self.assertEqual(entry.status, Entry.NEW)
        entry, new = learn(self.q("Assalomu alaykum, vizit ochilmayapti", 2), "Ochiq vizitni «Магазин закрыт» bilan yoping",
                           "Eldar")
        self.assertTrue(new)

    def test_case_specific_answers_are_not_learned(self):
        for i, ans in enumerate(["отвязала, переподключите", "Tuzatildi ✅", "Готово", "qo'shdim",
                                 "Bu so'rovni Pro-target bajaradi — so'rov unga yuborildi",
                                 "✅ So'rovingiz Saidabrorga yetkazildi."]):
            entry, _new = learn(self.q("Nuqtani ulab bering, moderatsiyada turibdi", i + 1), ans, "Guzel")
            self.assertIsNone(entry, ans)

    def test_panel_source_is_not_filtered(self):
        entry, new = learn(self.q("Тоже самое"), ANSWER, "admin", source="panel")
        self.assertTrue(new)

    def test_absorb_skips_greetings(self):
        std = Entry.objects.create(kind=Entry.FAQ, title="Geolokatsiya: uzoqdasiz", questions=["uzoqdasiz deyapti"],
                                   answer=ANSWER, status=Entry.APPROVED)
        a = Entry.objects.create(kind=Entry.FAQ, title="Assalom aleykum", questions=["Тут тоже самое"], answer="x",
                                 status=Entry.NEW)
        b = Entry.objects.create(kind=Entry.FAQ, title="D17 Afsona makon lokatsiyasini to'g'rilab bering",
                                 questions=[], answer="x", status=Entry.NEW)
        self.assertEqual(absorb(std.pk, [a.pk, b.pk], "test"), 2)
        std.refresh_from_db()
        self.assertTrue(any("lokatsiyasini to'g'rilab bering" in x for x in std.questions))
        self.assertNotIn("Assalom aleykum", std.questions)
        self.assertNotIn("Тут тоже самое", std.questions)

    def test_helpers(self):
        self.assertTrue(engine.learnable_question("Заказ не оформлен"))
        self.assertFalse(engine.learnable_question("Vot shu"))
        self.assertTrue(engine.learnable_answer("Перезайдите в приложение"))
        self.assertFalse(engine.learnable_answer("Подключила ✅"))


class CloseReviewTests(ControlsBase):
    def test_dry_run_then_apply(self):
        import os
        import tempfile

        from django.core.management import call_command
        std = Entry.objects.create(kind=Entry.FAQ, title="Geolokatsiya: uzoqdasiz deb tashrif qabul qilinmayapti",
                                   questions=[], answer=ANSWER, status=Entry.APPROVED)
        good = Entry.objects.create(kind=Entry.FAQ, title="Lokatsiyani to'g'rilab bering, uzoqdasiz deyapti",
                                    answer="x", status=Entry.NEW, claude_kind="same", claude_target=std)
        greet = Entry.objects.create(kind=Entry.FAQ, title="Assalom aleykum, yaxshimisiz", answer="x",
                                     status=Entry.NEW, claude_kind="same", claude_target=std)
        case = Entry.objects.create(kind=Entry.FAQ, title="Nuqtani ulab bering", answer="отвязала, переподключите",
                                    status=Entry.REVIEW, claude_kind="status")
        ok = Entry.objects.create(kind=Entry.FAQ, title="Boshqa", answer="y", status=Entry.APPROVED)
        ids_file = os.path.join(tempfile.mkdtemp(), "ids.txt")
        call_command("support_close_review", "--dry-run", "--ids-file", ids_file, stdout=open(os.devnull, "w"))
        self.assertEqual(Entry.objects.filter(status=Entry.NEW).count(), 2)
        call_command("support_close_review", "--ids-file", ids_file, stdout=open(os.devnull, "w"))
        for e in (good, greet, case, ok, std):
            e.refresh_from_db()
        self.assertEqual(good.status, Entry.ARCHIVED)
        self.assertEqual((greet.status, case.status, ok.status), (Entry.REJECTED, Entry.REJECTED, Entry.APPROVED))
        self.assertEqual(sorted(open(ids_file).read().split()), sorted([str(greet.pk), str(case.pk)]))
        self.assertTrue(any("uzoqdasiz" in x for x in std.questions))

    def test_only_same_rejects_nothing(self):
        from support import review_close
        Entry.objects.create(kind=Entry.FAQ, title="Nuqtani ulab bering", answer="z", status=Entry.NEW)
        self.assertEqual(review_close.plan(reject_rest=False)["reject"], [])
