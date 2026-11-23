"""Teglar (savol turlari): avtomatik qo'yish, qo'lda tahrir, tahlilda o'lchov, savollar ro'yxati filtri."""
from . import tags as T
from .models import Message, Tag
from .tests import group_msg
from .tests_v27 import OpenBase


class TagTests(OpenBase):
    def setUp(self):
        super().setUp()
        T.seed()
        T._CACHE["key"] = None

    def test_detect_multiple(self):
        self.assertEqual(set(T.detect("Aksiya chiqmayapti, 1C da limit tugagan")), {"promo", "1c"})
        self.assertIn("visit", T.detect("Не могу начать визит"))
        self.assertEqual(T.detect("salom"), [])

    def test_live_question_gets_tags_and_manual_lock(self):
        self.h().handle(group_msg(30, 1, "protarget da vizit ochilmayapti", username="agent1"))
        q = Message.objects.get(message_id=30, kind="question")
        self.assertTrue({"protarget", "visit"} <= set(q.tags))
        self.login("editor")
        r = self.call("post", f"support/messages/{q.id}/tags/", {"tags": ["login", "nope"]})
        self.assertEqual(r.json()["tags"], ["login"])
        T.backfill()
        q.refresh_from_db()
        self.assertEqual((q.tags, q.tags_locked), (["login"], True))  # qo'lda — avtomatik qayta yozilmaydi

    def test_explore_by_tag_and_inbox_filter(self):
        a = self.q(mid=40)
        Message.objects.filter(pk=a.pk).update(tags=["promo", "1c"])
        b = self.q(mid=41)
        Message.objects.filter(pk=b.pk).update(tags=["promo"])
        self.login("viewer")
        e = self.call("get", "support/analytics/explore/?scope=all&days=3650&by=tag&metrics=count").json()
        rows = {r["k0"]: r["count"] for r in e["rows"]}
        self.assertEqual((rows["promo"], rows["1c"]), (2, 1))
        self.assertEqual(next(r["l0"] for r in e["rows"] if r["k0"] == "promo"), "Aksiya / skidka")
        ids = {m["id"] for m in self.call("get", "support/messages/?ex=1&scope=all&days=3650&f_tag=1c").json()}
        self.assertEqual(ids, {a.id})

    def test_tags_api_admin_save_and_backfill(self):
        q = self.q(mid=42)
        Message.objects.filter(pk=q.pk).update(text="Narx noto'g'ri chiqyapti")
        self.login("viewer")
        self.assertEqual(self.call("post", "support/tags/", {"tags": []}).status_code, 403)
        self.login("admin")
        r = self.call("post", "support/tags/", {"tags": [{"key": "price", "title": "Narx", "keywords": ["narx"]}]})
        self.assertEqual([t["key"] for t in r.json()], ["price"])
        self.assertEqual(Tag.objects.count(), 1)
        q.refresh_from_db()
        self.assertEqual(q.tags, ["price"])
