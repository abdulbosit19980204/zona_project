"""«Bu raqam boshqa PRBC akkauntiga bog'langan» (prbc.binding): tanish, G1–G7, ruxsat bilan bog'lash, rollback, ortga
qaytarish, sinov, nazorat va botdagi to'liq oqim — soxta PRBC bilan. Javob shakllari prbc.uz'dagi haqiqiy
/auth/admin/users/, user detail va /hr/persons/ javoblaridan (2026-11-27, faqat GET bilan o'qilgan; ismlar va raqamlar
o'zgartirilgan)."""
import copy
import re
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from support.models import Message, Settings
from support.tests import group_msg, visible
from support.tests_v6 import FlowBase
from zona.crypto import encrypt

from . import access, binding, modules
from .client import PrbcError
from .models import AccessLog, Connection

TG = 6838190467
PHONE = "+998912697707"
CORE = {k: True for k in binding.CORE}
ALL = {k: True for k in binding.ORDER}


def days_ago(n):
    return (timezone.now() - timezone.timedelta(days=n)).isoformat()


class FakeHr:
    """PRBC: A (hr_, 1C, Kutilmoqda, Telegramsiz) va B (tg_, 1C siz) — bitta odam."""

    def __init__(self):
        self.timeout = 30
        self.writes = []
        self.fail = {}   # amal -> PrbcError (masalan "link", "phone")
        self.users = [
            {"id": 20, "username": "hr_20", "source": "web", "full_name": "ABDRAXMANOVA ARZAYI'M AZATOVNA",
             "telegram_id": None, "telegram_full_name": "", "status": "pending", "is_active": True, "phone": PHONE,
             "employee_id": 120, "employee_active": True, "role_codes": ["employee"], "position": "Торговый представитель",
             "date_joined": days_ago(31), "is_superuser": False},
            {"id": 21, "username": f"tg_{TG}", "source": "telegram", "full_name": "Arzayim Abdraxmanova",
             "telegram_id": TG, "telegram_full_name": "Arzayim Abdraxmanova", "status": "pending", "is_active": True,
             "phone": "", "employee_id": 121, "employee_active": True, "role_codes": ["employee"], "position": "",
             "date_joined": days_ago(1), "is_superuser": False},
            {"id": 30, "username": "tg_30", "source": "telegram", "full_name": "BOSHQA XODIM", "telegram_id": 30,
             "status": "active", "is_active": True, "phone": "+998901112233", "employee_id": 130, "role_codes": ["employee"],
             "date_joined": days_ago(100), "is_superuser": False},
        ]
        self.hr = {20: True, 21: False, 30: True}
        self.persons = [
            {"id": 756, "full_name": "ABDRAXMANOVA ARZAYI'M AZATOVNA", "phone": PHONE, "match_state": "created",
             "employee": {"id": 120, "user": 20, "full_name": "ABDRAXMANOVA ARZAYI'M AZATOVNA", "position": ""},
             "planned_state": "active", "telegram_bound": False,
             "employments": [{"status": "hired", "dismissal_date": "", "kind": "main"}]},
            {"id": 800, "full_name": "BOSHQA XODIM", "phone": "+998901112233", "match_state": "linked",
             "employee": {"id": 130, "user": 30}, "planned_state": "active", "telegram_bound": True,
             "employments": [{"status": "hired", "dismissal_date": ""}]},
        ]

    def user(self, uid):
        return next(u for u in self.users if u["id"] == uid)

    def person(self, pid):
        return next(p for p in self.persons if p["id"] == pid)

    def get(self, path, params=None):
        if path == "/auth/admin/users/":
            return copy.deepcopy(self.users)
        m = re.match(r"/auth/admin/users/(\d+)/$", path)
        if m:
            u = copy.deepcopy(self.user(int(m.group(1))))
            return {**u, "hr_managed": self.hr.get(u["id"], False), "assignments": [], "role_assignments": []}
        if path == "/hr/persons/":
            return {"count": len(self.persons), "next": None, "results": copy.deepcopy(self.persons)}
        raise AssertionError(path)

    def _maybe_fail(self, key):
        if key in self.fail:  # bir martalik xato (qayta urinish / rollback o'tadi)
            raise PrbcError(self.fail.pop(key), status=400)

    def post(self, path, body=None):
        self.writes.append(("POST", path, body))
        m = re.match(r"/hr/persons/(\d+)/(link|unlink)/$", path)
        if m:
            self._maybe_fail(m.group(2))
            p = self.person(int(m.group(1)))
            if m.group(2) == "unlink":
                p["employee"] = None
            else:
                if p["employee"]:
                    raise PrbcError("already linked", status=400)
                emp = body["employee"]
                u = next(x for x in self.users if x["employee_id"] == emp)
                p["employee"] = {"id": emp, "user": u["id"]}
            return {}
        m = re.match(r"/auth/admin/users/(\d+)/active/$", path)
        if m:
            self._maybe_fail("active")
            self.user(int(m.group(1)))["is_active"] = body["is_active"]
            return {}
        raise AssertionError(path)

    def patch(self, path, body=None):
        self.writes.append(("PATCH", path, body))
        m = re.match(r"/auth/admin/users/(\d+)/profile/$", path)
        assert m, path
        self._maybe_fail("phone")
        uid = int(m.group(1))
        if body.get("phone") and any(u["id"] != uid and u["phone"] == body["phone"] for u in self.users):
            raise PrbcError("phone taken", status=400)
        self.user(uid)["phone"] = body["phone"]
        return {}


class Base(TestCase):
    actions = {}

    def setUp(self):
        Connection.objects.update_or_create(pk=1, defaults={"enabled": True, "phone": "998900000000",
                                                            "password_enc": encrypt("x"),
                                                            "auto_actions": dict(self.actions)})
        self.p = FakeHr()

    def run_bind(self, text="Этот номер привязан к другой учётной записи PRBC", question=7, **kw):
        return binding.handle(text, "", tg_id=kw.pop("tg_id", TG), name=kw.pop("name", "Arzayim"), question=question,
                              client=self.p, conn=Connection.get(), **kw)

    def verify(self, question=7, phone=PHONE, tg=TG, user_id=TG):
        return binding.record_contact(question, tg, {"phone_number": phone, "user_id": user_id})


class DetectTests(TestCase):
    def test_texts_and_screens(self):
        yes = ["⚠️ Этот номер привязан к другой учётной записи PRBC. Обратитесь к администратору.",
               "This number belongs to another PRBC account. Please contact your administrator.",
               "Bu raqam boshqa PRBC akkauntiga bog'langan",
               "Бу ракам бошка аккаунтга богланган дейапти",
               "PRBC botda raqam band deyapti"]
        for t in yes:
            self.assertTrue(binding.is_binding_question(t), t)
            self.assertTrue(binding.is_binding_question("", t), "ocr: " + t)
        ocr = "Complete your profile\nTwo short steps before you start\nShare via Telegram\nThis number belongs to " \
              "another PRBC account. Please contact your administrator."
        self.assertTrue(binding.is_binding_question("yordam bering", ocr))
        for t in ["yangi tochka qo'sha olmayapman", "PRBC da vazifalar ko'rinmayapti", "raqamim o'zgardi",
                  "Не удалось подключиться к серверу"]:
            self.assertFalse(binding.is_binding_question(t), t)

    def test_other_flows_step_aside(self):
        t = "Этот номер привязан к другой учётной записи PRBC, кнопка не работает"
        with mock.patch("prbc.access.connection", return_value=mock.Mock(access_bot=True)):
            self.assertIsNone(access.handle(t, client=mock.Mock()))
            self.assertIsNone(modules.handle(t, client=mock.Mock(), conn=mock.Mock(access_bot=True)))

    def test_phones_in(self):
        self.assertEqual(binding.phones_in("Ulugbek +998 90 390 39 01", "tel 91-269-77-07"), ["903903901", "912697707"])


class DefaultDiagnoseTests(Base):
    def test_only_diagnoses_and_writes_nothing(self):
        r = self.run_bind(text="Этот номер привязан к другой учётной записи PRBC +998 91 269 77 07")
        self.assertEqual(r.kind, "escalate")
        self.assertEqual(self.p.writes, [])
        self.assertIn("✅ G2.", r.text)
        self.assertNotIn("G1.", r.text)                       # raqam so'ralmagan — G1 tekshirilmaydi
        self.assertIn("kerak: /staff → «Bog'lanishni uzish»", r.text)
        self.assertIn("Avtomatik o'zgartirish o'chiq", r.text)
        self.assertIn("settings?tab=users&user=20", r.note)
        self.assertIn("settings?tab=users&user=21", r.note)

    def test_name_fallback_without_phone(self):
        r = self.run_bind()
        self.assertIn("✅ G6.", r.text)
        self.assertEqual(self.p.writes, [])


class FixTests(Base):
    actions = CORE

    def test_asks_contact_first(self):
        r = self.run_bind()
        self.assertEqual(r.kind, "contact")
        self.assertEqual(AccessLog.objects.filter(action="bind_ask").count(), 1)
        self.assertEqual(self.p.writes, [])

    def test_full_fix_in_order(self):
        self.assertTrue(self.verify())
        r = self.run_bind()
        self.assertEqual(r.kind, "answer", r.text)
        self.assertEqual([(m, p) for m, p, _b in self.p.writes],
                         [("POST", "/hr/persons/756/unlink/"), ("PATCH", "/auth/admin/users/20/profile/"),
                          ("POST", "/hr/persons/756/link/")])
        self.assertEqual(self.p.writes[1][2], {"phone": ""})
        self.assertEqual(self.p.writes[2][2], {"employee": 121})
        self.assertEqual(self.p.person(756)["employee"]["id"], 121)
        self.assertEqual(self.p.user(20)["phone"], "")
        self.assertIn("1C ma'lumotlaringiz bilan bog'landi", r.text)
        self.assertIn("«📱 Поделиться номером» ni qayta bosing", r.text)
        logs = AccessLog.objects.filter(action__startswith="bind_", ok=True, reversible=True)
        self.assertEqual(sorted(x.action for x in logs), sorted(binding.CORE))
        self.assertEqual(logs.get(action="bind_free_phone").before["phone"], PHONE)

    def test_optional_steps(self):
        Connection.objects.filter(pk=1).update(auto_actions=ALL)
        self.verify()
        r = self.run_bind()
        self.assertEqual(r.kind, "answer")
        self.assertEqual(self.p.user(21)["phone"], "+998912697707")
        self.assertFalse(self.p.user(20)["is_active"])
        self.assertNotIn("Endi PRBC botida", r.text)
        self.assertNotIn("kerak:", r.text)
        self.assertEqual(len(self.p.writes), 5)

    def test_partial_permissions_change_nothing(self):
        Connection.objects.filter(pk=1).update(auto_actions={"bind_unlink_old": True, "bind_link_new": True})
        self.verify()
        r = self.run_bind()
        self.assertEqual(r.kind, "escalate")
        self.assertEqual(self.p.writes, [])

    def test_foreign_contact_rejected(self):
        self.assertFalse(self.verify(user_id=555))
        self.assertFalse(self.verify(user_id=None))
        phone, bad = binding.verified_phone(7)
        self.assertEqual((phone, bad), ("", 2))
        r = self.run_bind()
        self.assertEqual(r.kind, "contact")
        self.verify(user_id=1)
        r = self.run_bind()                                   # 3 marta begona kontakt — mutaxassisga
        self.assertEqual(r.kind, "escalate")
        self.assertIn("❌ G1.", r.text)
        self.assertEqual(self.p.writes, [])

    def test_contact_phone_must_match_old_account(self):
        self.verify(phone="+998 90 000 00 00")
        r = self.run_bind()
        self.assertEqual(r.kind, "escalate")
        self.assertEqual(self.p.writes, [])


class GateTests(Base):
    actions = ALL

    def setUp(self):
        super().setUp()
        self.verify()

    def assert_stops(self, code, **kw):
        r = self.run_bind(**kw)
        self.assertEqual(r.kind, "escalate", r.text)
        self.assertIn(f"❌ {code}.", r.text)
        self.assertEqual(self.p.writes, [])
        self.assertIn("hech narsa o'zgartirilmadi", r.text)
        return r

    def test_g2_old_has_telegram(self):
        self.p.user(20)["telegram_id"] = 999
        self.assert_stops("G2")

    def test_g3_old_is_used(self):
        self.p.user(20)["status"] = "active"
        self.assert_stops("G3")

    def test_g4_person_dismissed(self):
        self.p.person(756)["employments"][0].update(status="dismissed", dismissal_date="2026-11-01")
        self.p.person(756)["planned_state"] = "blocked"
        self.assert_stops("G4")

    def test_g4_no_person(self):
        self.p.person(756)["employee"] = None
        self.assert_stops("G4")

    def test_g5_new_is_old_or_linked(self):
        self.p.user(21)["date_joined"] = days_ago(60)
        self.assert_stops("G5")
        self.p.user(21)["date_joined"] = days_ago(1)
        self.p.hr[21] = True
        self.assert_stops("G5")

    def test_g6_many_accounts(self):
        self.p.users.append({**self.p.user(20), "id": 22, "username": "hr_22", "employee_id": 122})
        self.assert_stops("G6")

    def test_g7_name(self):
        self.p.user(21).update(full_name="Boshqa Odam", telegram_full_name="Boshqa Odam")
        self.assert_stops("G7", name="Boshqa Odam")
        Connection.objects.filter(pk=1).update(bind_strict_name=False)
        self.assertEqual(self.run_bind(name="Boshqa Odam").kind, "answer")


class RollbackTests(Base):
    actions = CORE

    def setUp(self):
        super().setUp()
        self.verify()

    def test_link_error_rolls_back(self):
        self.p.fail["link"] = "server error"
        r = self.run_bind()
        self.assertEqual(r.kind, "escalate")
        self.assertIn("ortga qaytarildi", r.text)
        self.assertEqual(self.p.person(756)["employee"]["id"], 120)   # yarim holat qolmadi
        self.assertEqual(self.p.user(20)["phone"], PHONE)
        self.assertEqual(AccessLog.objects.filter(action__startswith="bind_", reverted_at__isnull=False).count(), 2)

    def test_phone_refused_rolls_back_unlink(self):
        self.p.fail["phone"] = "This field may not be blank."
        r = self.run_bind()
        self.assertEqual(r.kind, "escalate")
        self.assertEqual(self.p.person(756)["employee"]["id"], 120)
        self.assertNotIn(("POST", "/hr/persons/756/link/", {"employee": 121}), self.p.writes)


class RevertTests(Base):
    actions = ALL

    def test_revert_each(self):
        self.verify()
        self.assertEqual(self.run_bind().kind, "answer")
        logs = {x.action: x for x in AccessLog.objects.filter(action__startswith="bind_", reversible=True)}
        ok, msg = binding.revert(logs["bind_unlink_old"], "admin", client=self.p)    # avval bog'lash qaytarilishi kerak
        self.assertFalse(ok)
        self.assertIn("avval", msg)
        for key in ("bind_archive_old", "bind_set_phone", "bind_link_new", "bind_free_phone", "bind_unlink_old"):
            ok, msg = access.revert(logs[key], "admin", client=self.p)
            self.assertTrue(ok, f"{key}: {msg}")
        self.assertEqual(self.p.person(756)["employee"]["id"], 120)
        self.assertEqual(self.p.user(20)["phone"], PHONE)
        self.assertEqual(self.p.user(21)["phone"], "")
        self.assertTrue(self.p.user(20)["is_active"])
        ok, _m = binding.revert(AccessLog.objects.get(pk=logs["bind_link_new"].pk), "admin", client=self.p)
        self.assertFalse(ok)                                   # ikki marta qaytarilmaydi


class PanelTests(Base):
    actions = ALL

    def test_simulate_writes_nothing(self):
        with mock.patch("prbc.binding.make_client", return_value=self.p):
            out = binding.simulate(phone=PHONE, tg_id=TG, conn=Connection.get())
        self.assertEqual(out["kind"], "answer")
        self.assertIn("🧪", out["text"])
        self.assertEqual({p["key"] for p in out["planned"]}, set(binding.ORDER))
        self.assertEqual(self.p.writes, [])
        self.assertFalse(AccessLog.objects.exclude(action="bind_contact").exists())

    def test_check_one_by_phone(self):
        with mock.patch("prbc.binding.make_client", return_value=self.p):
            out = binding.check_one("91 269 77 07")
        self.assertEqual(out["a"]["id"], 20)
        self.assertEqual(out["b"]["id"], 21)
        self.assertTrue(all(g["ok"] for g in out["gates"] if g["code"] != "G1"))

    def test_scan_reports_pairs(self):
        with mock.patch("prbc.binding.make_client", return_value=self.p):
            rep = binding.scan()
        self.assertEqual(rep["pairs"], 1)
        self.assertEqual(Connection.get().bind_report["rows"][0]["a"]["id"], 20)
        self.assertEqual(self.p.writes, [])


class BotFlowTests(FlowBase):
    """Guruhda savol -> botga o'tish tugmasi -> shaxsiy chatda o'z kontakti -> guruhda «bog'landi»."""

    def setUp(self):
        super().setUp()
        Settings.objects.update(ai_enabled=False, ai_primary=False)
        self.bot.username = "savolbot"
        self.bot.save()
        Connection.objects.update_or_create(pk=1, defaults={"enabled": True, "phone": "998900000000",
                                                            "password_enc": encrypt("x"), "auto_actions": dict(CORE)})
        self.p = FakeHr()
        for target in ("prbc.binding.make_client", "prbc.access.make_client"):
            patcher = mock.patch(target, return_value=self.p)
            patcher.start()
            self.addCleanup(patcher.stop)

    def private(self, mid, uid, text="", contact=None):
        m = {"message_id": mid, "chat": {"id": uid, "type": "private"}, "from": {"id": uid, "first_name": "Arzayim"}}
        if contact:
            m["contact"] = contact
        else:
            m["text"] = text
        return {"message": m}

    def test_full_flow(self):
        h = self.h()
        h.handle(group_msg(1, TG, "Этот номер привязан к другой учётной записи PRBC. Обратитесь к администратору."))
        q = Message.objects.get(kind=Message.QUESTION)
        self.assertEqual((q.stage, q.status), ("bind", Message.NEW))
        btn = visible(self.tg)[-1]["buttons"][0][0]
        self.assertEqual(btn["url"], f"https://t.me/savolbot?start=bind{q.pk}")
        h.handle(self.private(2, TG, f"/start bind{q.pk}"))
        self.assertTrue(self.tg.sent[-1]["markup"]["keyboard"][0][0]["request_contact"])
        h.handle(self.private(3, TG, contact={"phone_number": "998912697707", "user_id": 777}))   # begona kontakt
        self.assertIn("не ваш контакт", self.tg.sent[-1]["text"])
        self.assertEqual(self.p.writes, [])
        h.handle(self.private(4, TG, contact={"phone_number": "998912697707", "user_id": TG}))
        q.refresh_from_db()
        self.assertEqual(q.status, Message.ANSWERED, q.answer_text)
        self.assertEqual(q.stage, "prbc")
        self.assertEqual(self.p.person(756)["employee"]["id"], 121)
        group = [x for x in visible(self.tg) if x["chat"] == -100]
        self.assertIn("связан с данными 1С", group[-1]["text"])
        self.assertIn("связан с данными 1С", self.tg.sent[-1]["text"])          # shaxsiy chatga ham
        self.assertEqual(self.tg.sent[-1]["chat"], TG)

    def test_default_goes_to_staff_without_asking(self):
        Connection.objects.filter(pk=1).update(auto_actions={})
        self.h().handle(group_msg(1, TG, "This number belongs to another PRBC account"))
        q = Message.objects.get(kind=Message.QUESTION)
        self.assertEqual(q.status, Message.ESCALATED)
        self.assertIn("kerak:", visible(self.tg)[-1]["text"])
        self.assertEqual(self.p.writes, [])

    def test_plain_private_message_unaffected(self):
        self.h().handle(self.private(1, TG, "/start"))
        self.assertIn("support botman", self.tg.sent[-1]["text"])
