"""Takror savol-javoblarni tozalash (qo'lda, avto, AI) va noto'g'ri rasmni rad etish."""
from unittest import mock

from zona.tests import Base

from . import ai_review, dedupe
from .models import AIJob, Entry, EntryVersion, Media, Suggestion


def mk(title, answer, questions=(), status=Entry.APPROVED, **kw):
    return Entry.objects.create(kind=Entry.FAQ, title=title, questions=list(questions), answer=answer, status=status, **kw)


class DedupeTests(Base):
    def setUp(self):
        self.short = mk("Klient qo'shish bo'limi ko'rinmayapti", "Rolni tekshiring.",
                        ["yangi klient qo'shish bo'limi ko'rinmayapti"])
        self.long = mk("PRBC: yangi klient qo'shish bo'limi ko'rinmayapti",
                       "1. Profil → Rol ni oching.\n2. Rol Employee bo'lsa, supervayzeringizga yozing.\n3. Rol Agent bo'lgach "
                       "ilovani qayta oching — «Klient qo'shish» bo'limi chiqadi.", ["klient qo'shish bo'limi yo'q"], uses=4, likes=2)
        self.other = mk("Zakaz 1C ga tushmayapti", "Sinxronizatsiya tugmasini bosing.", ["zakaz 1c da ko'rinmayapti"])

    def test_groups_pick_detailed_answer(self):
        groups = dedupe.find_groups(60)
        g = next(g for g in groups if self.short.id in [r["id"] for r in g["entries"]])
        self.assertEqual(g["keep"], self.long.id)
        self.assertNotIn(self.other.id, [r["id"] for r in g["entries"]])
        self.assertGreater(dedupe.quality(self.long), dedupe.quality(self.short))

    def test_merge_archives_and_keeps_everything(self):
        m = Media.objects.create(kind=Media.PHOTO, path="x.jpg", label=self.short)
        keep, n = dedupe.merge_group(self.long.id, [self.short.id, self.long.id], "editor")
        self.assertEqual(n, 1)
        self.short.refresh_from_db()
        m.refresh_from_db()
        self.assertEqual(self.short.status, Entry.ARCHIVED)  # o'chirilmadi
        self.assertEqual(m.label_id, keep.id)  # rasm namunasi yo'qolmadi
        self.assertIn(self.short.title, keep.questions)
        self.assertTrue(EntryVersion.objects.filter(entry=keep).exists())  # eski holat versiyada

    def test_api_list_merge_and_permissions(self):
        self.login("viewer")
        self.assertEqual(self.call("get", "support/entries/duplicates/?threshold=60").status_code, 200)
        self.assertEqual(self.call("post", "support/entries/dedupe-merge/", {"keep": self.long.id, "merge": [self.short.id]}).status_code, 403)
        self.login("editor")
        r = self.call("post", "support/entries/dedupe-merge/", {"keep": self.long.id, "merge": [self.short.id], "answer": "Yangi optimal javob"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["entry"]["answer"], "Yangi optimal javob")

    def test_auto_clean_only_near_identical(self):
        twin = mk("Zakaz 1C ga tushmayapti", "Admin bilan bog'laning.", ["zakaz 1c da ko'rinmayapti"], status=Entry.REVIEW)
        res = dedupe.auto_clean("editor", 92, dry_run=True)
        self.assertEqual(Entry.objects.get(pk=twin.pk).status, Entry.REVIEW)  # dry run hech narsani o'zgartirmaydi
        self.assertGreaterEqual(res["groups"], 1)
        dedupe.auto_clean("editor", 92)
        self.assertEqual(Entry.objects.get(pk=twin.pk).status, Entry.ARCHIVED)
        self.assertEqual(Entry.objects.get(pk=self.other.pk).status, Entry.APPROVED)
        self.assertEqual(Entry.objects.get(pk=self.short.pk).status, Entry.APPROVED)  # 92% dan past — tegilmadi

    def test_ai_job_suggests_and_auto_applies(self):
        def fake(groups):
            return [{"index": i, "same": True, "keep": g[-1].id if g[-1].id == self.long.id else g[0].id,
                     "merge": [e.id for e in g if e.id != self.long.id], "title": "", "answer": "AI javobi",
                     "answer_ru": "", "reason": "bir xil"} for i, g in enumerate(groups) if self.long in g]
        with mock.patch.object(ai_review, "ai_merge_groups", side_effect=fake):
            job = AIJob.objects.create(kind=AIJob.DEDUPE, params={"threshold": 60, "auto": True}, created_by="editor")
            ai_review.run_job(job.id)
        self.long.refresh_from_db()
        self.assertEqual(self.long.answer, "AI javobi")
        self.assertEqual(Entry.objects.get(pk=self.short.pk).status, Entry.ARCHIVED)
        self.assertEqual(Suggestion.objects.get(kind=Suggestion.DEDUPE).status, Suggestion.APPROVED)


class ImageIgnoreTests(Base):
    def test_ignore_hides_and_restore(self):
        e = mk("X", "javob")
        m = Media.objects.create(kind=Media.PHOTO, path="a.jpg", dhash="0f0f0f0f0f0f0f0f", dhash_mid="0f0f0f0f0f0f0f0f")
        self.login("editor")
        ids = lambda key: [i for g in self.call("get", "support/images/").json()[key] for i in g["ids"]]  # noqa: E731
        self.assertIn(m.id, ids("unlabeled"))
        self.assertEqual(self.call("post", "support/images/ignore/", {"ids": [m.id]}).json()["done"], 1)
        self.assertNotIn(m.id, ids("unlabeled"))
        self.assertIn(m.id, ids("ignored"))
        from . import vision
        vision.label(Media.objects.filter(pk=m.pk), e, "bot", auto=True)  # rad etilgan rasm avtomatik o'rgatilmaydi
        self.assertIsNone(Media.objects.get(pk=m.pk).label_id)
        self.call("post", "support/images/ignore/", {"ids": [m.id], "ignored": False})
        self.assertIn(m.id, ids("unlabeled"))
