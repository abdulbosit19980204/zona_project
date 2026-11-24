"""Ekran turlari, rasmlar joyi (eskiz / Telegram havolasi), ish vaqti bo'yicha javob vaqti, xodim/agent tahlilida turlar."""
import datetime as dt
import os
import tempfile
from pathlib import Path
from unittest import mock

from django.utils import timezone

from . import screens, slim, vision
from . import tags as T
from .models import Entry, Media, Message, ScreenType, Settings, TgUser
from .tests_images import screen
from .tests_v27 import OpenBase
from .workload import TZ, work_secs

H = (9, 19, frozenset(range(5)))


def at(*a):
    return dt.datetime(*a, tzinfo=TZ)


class WorkTimeTests(OpenBase):
    def test_only_working_hours_count(self):
        self.assertEqual(work_secs(at(2026, 11, 23, 21, 0), at(2026, 11, 24, 9, 10), H), 600)   # tun hisoblanmaydi
        self.assertEqual(work_secs(at(2026, 11, 27, 18, 0), at(2026, 11, 30, 10, 0), H), 7200)  # dam olish kunlari
        self.assertEqual(work_secs(at(2026, 11, 23, 21, 0), at(2026, 11, 23, 21, 5), H), 300)   # kechqurun darhol — haqiqiy
        self.assertEqual(work_secs(None, at(2026, 11, 23, 9, 0), H), None)

    def test_settings_drive_hours(self):
        from . import workload
        Settings.objects.update(work_from=8, work_to=17, work_days="0,1,2,3,4,5")
        workload._HOURS["key"] = None
        self.assertEqual(workload.work_hours(), (8, 17, frozenset(range(6))))

    def test_explore_staff_time_and_resolved_not_unanswered(self):
        q = self.q(mid=70)  # 11:00 da (OpenBase), uzatilgan
        Message.objects.filter(pk=q.pk).update(resolution=Message.YES, created_at=at(2026, 11, 23, 18, 50))
        staff = TgUser.objects.create(tg_id=9, name="Op", username="test_op")
        r = Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=71, user=staff, kind=Message.STAFF,
                                   question=q, text="Tayyor")
        Message.objects.filter(pk=r.pk).update(created_at=at(2026, 11, 24, 9, 20))
        from . import workload
        workload._HOURS.update(key=10 ** 12, v=H)
        from .explore import _q_metrics, _q_rows
        with mock.patch("time.time", return_value=10 ** 12 * 60 + 1):
            rows, _ = _q_rows(Message.objects.filter(pk=q.pk))
        m = _q_metrics([v for _k, v in rows])
        self.assertEqual((m["unanswered"], m["staff"]), (0, 1))
        self.assertEqual(m["median_s"], 1800.0)  # 18:50→19:00 (10 daq) + 9:00→9:20 (20 daq)


class MediaBase(OpenBase):
    def setUp(self):
        super().setUp()
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        p = mock.patch.dict(os.environ, {"ZONA_SUPPORT_MEDIA": media.name})
        p.start()
        self.addCleanup(p.stop)
        screens._CACHE["key"] = None

    def photo(self, kind="moderation", name="AGENT", ocr="Новая торговая точка\nТорговая точка «ABC SHOP» отправлена на модерацию", age_h=5,
              msg=None, **kw):
        m = vision.store(screen(kind=kind, name=name), source="question", message=msg)
        Media.objects.filter(pk=m.pk).update(ocr_text=ocr, created_at=timezone.now() - dt.timedelta(hours=age_h), **kw)
        m.refresh_from_db()
        return m


class ScreenTests(MediaBase):
    def test_rebuild_groups_names_and_assigns_new(self):
        mods = [self.photo(name=f"SHOP {i}") for i in range(6)]
        other = [self.photo(kind="prbc", name=f"X{i}", ocr="Оформление заказа\nПроверьте товары в корзине") for i in range(5)]
        res = screens.rebuild()
        self.assertEqual(res["types"], 2)
        t = ScreenType.objects.get(media=mods[0].pk)
        self.assertEqual(t.title, "Торговая точка отправлена на модерацию")
        self.assertEqual(t.count, 6)
        self.assertEqual(Media.objects.get(pk=other[0].pk).screen.title, "Проверьте товары в корзине")
        new = self.photo(name="YANGI DO'KON")
        self.assertEqual(screens.assign_new(), 1)
        self.assertEqual(Media.objects.get(pk=new.pk).screen_id, t.id)
        # admin nomlagani qayta guruhlashda saqlanadi
        t.title, t.title_locked = "Moderatsiyaga yuborildi", True
        t.save()
        screens.rebuild()
        self.assertEqual(ScreenType.objects.get(pk=t.pk).title, "Moderatsiyaga yuborildi")

    def test_name_ignores_status_bar_and_weekdays(self):
        self.assertEqual(screens.name_of(["all LTE 87%\nВизиты\nпн вт ср чт пт сб"] * 3), "Vizitlar (kalendar)")
        self.assertEqual(screens.name_of(["12:30\nВы не в активной зоне\nKLIENT MCHJ"] * 2), "Вы не в активной зоне")

    def test_api_assign_edit_and_listing(self):
        q = self.q(mid=80)
        ms = [self.photo(name=f"S{i}", msg=q if i == 0 else None) for i in range(3)]
        self.login("editor")
        r = self.call("post", "support/images/screens/assign/", {"ids": [m.id for m in ms], "title": "Moderatsiya"}).json()
        t = ScreenType.objects.get(pk=r["screen"])
        self.assertEqual((r["done"], t.count, t.title_locked), (3, 3, True))
        self.assertTrue(t.hashes)
        e = Entry.objects.create(kind=Entry.FAQ, title="Moderatsiyada", answer="Kuting", status=Entry.APPROVED)
        self.assertEqual(self.call("patch", f"support/images/screens/{t.id}/", {"tag": "moderation", "entry": e.id}).status_code, 200)
        d = self.call("get", "support/images/").json()
        row = next(x for x in d["screens"] if x["id"] == t.id)
        self.assertEqual((row["tag"], row["entry"], row["count"], row["questions"]), ("moderation", e.id, 3, 1))
        self.assertEqual(row["top"][0]["q"], "Skidka yoqib bering")
        self.assertIn("storage", d)


class SlimTests(MediaBase):
    def test_known_dropped_reps_thumbed_unknown_kept_then_thumbed(self):
        t = ScreenType.objects.create(title="Mod", count=0)
        known = [self.photo(name=f"K{i}", age_h=5 + i, screen=t) for i in range(8)]
        ScreenType.objects.filter(pk=t.pk).update(count=8)
        fresh_unknown = self.photo(kind="prbc", name="U1", age_h=5)
        old_unknown = self.photo(kind="prbc", name="U2", age_h=24 * 5)
        st = slim.run(pause=0)
        rows = {m.id: m for m in Media.objects.all()}
        thumbs = [m for m in known if rows[m.id].path]
        self.assertEqual(len(thumbs), slim.KEEP_PER_TYPE)  # turning so'nggi namunalari — eskiz
        self.assertTrue(all(rows[m.id].slim for m in known))
        self.assertTrue(all(rows[m.id].mime == "image/webp" or rows[m.id].mime == "image/jpeg" for m in thumbs))
        self.assertEqual(rows[fresh_unknown.id].slim, False)  # tanilmagan, yangi — to'liq
        self.assertTrue(rows[old_unknown.id].slim and rows[old_unknown.id].path)  # eski — eskiz
        self.assertGreaterEqual(st["drop"], 2)
        self.assertLess(rows[thumbs[0].id].size, rows[thumbs[0].id].full_size)
        self.assertTrue(rows[known[0].id].dhash)  # tanish izi qoladi

    def test_open_question_and_attachment_kept(self):
        q = self.q(mid=90)  # uzatilgan, hal bo'lmagan
        t = ScreenType.objects.create(title="Mod", count=1)
        a = self.photo(name="OPEN", msg=q, screen=t)
        b = self.photo(kind="prbc", name="ATT", age_h=24 * 10)
        Entry.objects.create(kind=Entry.FAQ, title="x", answer="y", status=Entry.APPROVED, attachments=[b.id])
        slim.run(pause=0)
        self.assertFalse(Media.objects.get(pk=a.pk).slim)
        self.assertFalse(Media.objects.get(pk=b.pk).slim)

    def test_media_dict_link_and_full_fallback(self):
        q = self.q(mid=95)
        t = ScreenType.objects.create(title="Mod", count=1)
        m = self.photo(name="L", msg=q, screen=t)
        slim.drop(m)
        m.refresh_from_db()
        from .views import media_dict
        d = media_dict(m)
        self.assertEqual((d["available"], d["slim"]), (False, True))
        self.assertTrue(d["link"].endswith("/95") or d["link"] == "")
        self.login("viewer")
        self.assertEqual(self.call("get", f"support/media/{m.id}/file/?full=1").status_code, 404)  # Telegram'da ham yo'q (test)
        self.assertFalse(Path(str(m.path or "/nonexistent")).exists())

    def test_thumb_bytes_small(self):
        data, mime = slim.thumb_bytes(screen(size=(1080, 2340)))
        self.assertIn(mime, ("image/webp", "image/jpeg"))
        self.assertLess(len(data), 60_000)


class PeopleTypeTests(OpenBase):
    def setUp(self):
        super().setUp()
        T.seed()
        T._CACHE["key"] = None

    def test_staff_evaluate_has_tags_and_slowest(self):
        staff = TgUser.objects.create(tg_id=9, name="Op", username="test_op")
        TgUser.objects.filter(pk=staff.pk).update(member=self.member)
        for i, tg in enumerate([["promo"], ["promo"], ["visit"]]):
            q = self.q(mid=100 + i)
            Message.objects.filter(pk=q.pk).update(tags=tg, resolution=Message.NO if i == 0 else Message.YES)
            r = Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=200 + i, user=staff, kind=Message.STAFF,
                                       question=q, text="javob")
            Message.objects.filter(pk=r.pk).update(created_at=q.created_at + dt.timedelta(minutes=10 * (i + 1)))
        from . import activity
        start, end = timezone.now() - dt.timedelta(days=3650), timezone.now() + dt.timedelta(days=1)
        res = activity.evaluate(staff, start, end)
        tags = {t["key"]: t for t in res["tags"]}
        self.assertEqual((tags["promo"]["n"], tags["promo"]["no"], tags["visit"]["n"]), (2, 1, 1))
        self.assertEqual(len(res["slowest"]), 3)
        self.assertGreaterEqual(res["slowest"][0]["secs"], res["slowest"][-1]["secs"])

    def test_agent_detail_has_tags(self):
        for i in range(5):
            q = self.q(mid=300 + i, status=Message.ANSWERED, stage="faq")
            Message.objects.filter(pk=q.pk).update(tags=["promo"] if i < 4 else ["visit"])
        from . import agents
        start, end = timezone.now() - dt.timedelta(days=3650), timezone.now() + dt.timedelta(days=1)
        d = agents.detail(self.asker, start, end)
        tags = {t["key"]: t["n"] for t in d["tags"]}
        self.assertEqual(tags, {"promo": 4, "visit": 1})
        self.assertTrue(any(i["code"] == "tag_often" for i in d["insights"]))


class RedirectTests(OpenBase):
    def setUp(self):
        super().setUp()
        from .runner import Handler
        Handler._redirected.clear()
        from .models import Group
        self.new = Group.objects.create(bot=self.bot, chat_id=-200, title="ROP yangi", username="rop_new", is_admin=True)
        Group.objects.filter(pk=self.g.pk).update(redirect_to=self.new)

    def test_old_group_replies_with_link_in_askers_language_once(self):
        from .tests import group_msg
        self.h().handle(group_msg(500, 1, "Почему не работает скидка?", username="agent1"))
        sent = self.tg.sent[-1]
        self.assertEqual((sent["chat"], sent["reply_to"]), (-100, 500))
        self.assertIn("@agent1", sent["text"])
        self.assertIn("новую группу", sent["text"])
        self.assertIn('href="https://t.me/rop_new"', sent["text"])
        self.assertFalse(Message.objects.filter(message_id=500, kind=Message.QUESTION).exists())  # javob berilmaydi
        n = len(self.tg.sent)
        self.h().handle(group_msg(501, 1, "ещё вопрос", username="agent1"))
        self.assertEqual(len(self.tg.sent), n)  # 10 daqiqa ichida qayta eslatilmaydi
        self.h().handle(group_msg(502, 2, "Скидка чиқмаяпти", username="agent2"))
        self.assertIn("янги гуруҳга", self.tg.sent[-1]["text"])  # o'zbek kirill — kirillda
        self.assertIn('href="https://t.me/rop_new"', self.tg.sent[-1]["text"])
        from .models import Group
        self.assertEqual(Group.objects.get(pk=self.g.pk).redirect_count, 2)

    def test_staff_not_redirected_and_admin_bulk_api(self):
        from .models import Group
        from .tests import group_msg
        n = len(self.tg.sent)
        self.h().handle(group_msg(510, 7, "Tayyor", username="test_op"))  # xodim (Member telegram)
        self.assertEqual(len(self.tg.sent), n)
        old2 = Group.objects.create(bot=self.bot, chat_id=-300, title="Eski 2", is_admin=False)
        Group.objects.filter(pk=self.new.pk).update(is_admin=True)
        self.login("admin")
        r = self.call("post", "support/groups-redirect/", {"target": self.new.id, "not_admin": True}).json()
        self.assertGreaterEqual(r["done"], 1)
        self.assertEqual(Group.objects.get(pk=old2.pk).redirect_to_id, self.new.id)
        self.assertIsNone(Group.objects.get(pk=self.new.pk).redirect_to_id)  # o'ziga yo'naltirilmaydi
        bad = self.call("patch", f"support/groups/{self.new.id}/", {"invite_link": "http://evil.example"})
        self.assertEqual(bad.status_code, 400)
        ok = self.call("patch", f"support/groups/{self.new.id}/", {"invite_link": "t.me/+AbCd"}).json()
        self.assertEqual(ok["link"], "https://t.me/+AbCd")


class InviteLinkTests(OpenBase):
    def test_creates_additional_link_never_revokes_primary(self):
        from .models import Group
        from .runner import invite_link
        g = Group.objects.create(bot=self.bot, chat_id=-400, title="ROP", is_admin=True)
        calls = []

        class TG:
            def call(self, method, params=None, **kw):
                calls.append(method)
                return {"invite_link": "https://t.me/+NewExtra"}
        self.assertEqual(invite_link(g, TG()), "https://t.me/+NewExtra")
        self.assertEqual(calls, ["createChatInviteLink"])
        self.assertEqual(Group.objects.get(pk=g.pk).invite_link, "https://t.me/+NewExtra")
        g.refresh_from_db()
        self.assertEqual(invite_link(g, TG()), "https://t.me/+NewExtra")  # saqlangan — qayta yaratilmaydi
        self.assertEqual(len(calls), 1)
