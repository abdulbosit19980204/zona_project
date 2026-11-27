"""«Yangi tochka» ruxsatlari (prbc.access): tanish, tekshirish, to'g'rilash, xodimdan so'rash, nazorat — soxta PRBC bilan.
Javob shakllari prbc.uz'dagi haqiqiy /auth/admin/users/, integration-access, employee-mappings va refs javoblaridan
(2026-11-27, faqat GET bilan o'qilgan; ismlar o'zgartirilgan)."""
import copy
import re
from unittest import mock

from django.test import TestCase

from support.models import Message, Settings
from support.tests import group_msg, visible
from support.tests_v6 import FlowBase
from zona.crypto import encrypt

from . import access
from .client import PrbcError
from .models import AccessLog, Connection

NODES = [{"id": 37, "parent_id": 1, "name": "MDLZ TASHKENT", "code": "", "node_type": "department", "is_active": True},
         {"id": 50, "parent_id": 2, "name": "LOREAL ROP", "code": "", "node_type": "department", "is_active": True},
         {"id": 51, "parent_id": 2, "name": "Support", "code": "", "node_type": "department", "is_active": True}]


def user(uid, name, position="Торговый представитель", tg=None, username="", node=None, roles=("employee",),
         status="active"):
    n = next((x for x in NODES if x["id"] == node), None)
    return {"id": uid, "full_name": name, "position": position, "telegram_id": tg, "telegram_username": username,
            "is_active": status == "active", "employee_active": status == "active", "status": status,
            "role_codes": list(roles), "primary_node_id": node, "primary_node_name": n["name"] if n else "",
            "primary_node_path": f"HD / {n['name']}" if n else "", "organization_id": 3}


class FakePrbc:
    def __init__(self):
        self.timeout = 30
        self.calls, self.writes = [], []
        self.break_put = False
        self.users = [
            user(10, "ISMOILOV SHOHRUH", tg=10, username="shohruh", node=37),
            user(11, "ABDIRAIMOVA MUHSINA", tg=11, username="muhsina", node=37),
            user(12, "KETGAN XODIM", tg=12, status="disabled", node=37),
            user(13, "SAID IT", position="IT mutaxassis", tg=13, username="StargroupSaid", node=51),
            user(14, "ALI TP", tg=14, username="ali_tp", node=None, roles=()),
            user(15, "LOLA TP", tg=15, username="lola", node=50),
        ]
        self.seats = {11: "employee", 13: "admin", 14: "viewer"}
        self.rows = {1: [{"id": 1, "employee": 225, "employee_name": "ABDIRAIMOVA MUHSINA", "employee_user_id": 11,
                          "employee_position": "Торговый представитель", "external_guid": "G1",
                          "external_name": "2.3 Карши К-3"}],
                     2: [], 3: [{"employee_user_id": 13, "external_guid": "T1", "external_name": "test"}]}
        self.reps = {1: [{"guid": "G1", "name": "2.3 Карши К-3", "active": True},
                         {"guid": "G2", "name": "3.2 Фергана К-4", "active": True},
                         {"guid": "G3", "name": "2.1 Навои SR3", "active": True},
                         {"guid": "G4", "name": "2.1 Навои SR31", "active": True},
                         {"guid": "G5", "name": "SR8 Tashkent", "active": True}],
                     2: [{"guid": "N1", "name": "3.2 Фергана К-4", "active": True},
                         {"guid": "N2", "name": "5.1 Самарканд К-1", "active": True},
                         {"guid": "N3", "name": "ТП1", "active": True},
                         {"guid": "N4", "name": "SR-8 Tashkent", "active": True}],
                     3: [{"guid": "T9", "name": "9.9 Test K-9", "active": True}]}
        self.details = {14: {"assignments": [{"id": 77, "hierarchy_node_id": 50, "hierarchy_node_name": "LOREAL ROP",
                                              "is_primary": False}]}}

    def get(self, path, params=None):
        self.calls.append(("GET", path))
        if path == "/integrations/connections/":
            return {"count": 3, "results": [{"id": 1, "code": "food", "organization": 3, "is_enabled": True},
                                            {"id": 3, "code": "food_copy", "organization": 3, "is_enabled": True},
                                            {"id": 2, "code": "nonfood", "organization": 3, "is_enabled": True}]}
        if path == "/auth/admin/users/":
            return copy.deepcopy(self.users)
        if path == "/admin/organization-modules/3/integration-access/":
            return self.roster()
        m = re.match(r"/integrations/connections/(\d)/employee-mappings/$", path)
        if m:
            return {"rows": copy.deepcopy(self.rows[int(m.group(1))]), "candidates": [], "nodes": NODES}
        m = re.match(r"/integrations/connections/(\d)/refs/$", path)
        if m:
            return {"connection": int(m.group(1)), "groups": {"employees": {"count": 1, "items": self.reps[int(m.group(1))]}}}
        m = re.match(r"/auth/admin/users/(\d+)/$", path)
        if m:
            return self.details.get(int(m.group(1)), {"assignments": []})
        raise AssertionError(path)

    def roster(self):
        return {"members": [{"id": i, "full_name": "", "position": "", "level": lv} for i, lv in self.seats.items()],
                "candidates": []}

    def post(self, path, body=None):
        self.writes.append(("POST", path, body))
        if path.endswith("/integration-access/"):
            for i in body["user_ids"]:
                self.seats[i] = body["level"]
            return self.roster()
        return {}

    def request(self, method, path, params=None, body=None):
        if method == "GET":
            return self.get(path, params)
        self.writes.append((method, path, body))
        cid = int(re.match(r"/integrations/connections/(\d)/employee-mappings/$", path).group(1))
        names = {r["guid"]: r["name"] for r in self.reps[cid]}
        rows = [{"employee_user_id": r["user_id"], "external_guid": r["external_guid"],
                 "external_name": names.get(r["external_guid"], ""), "employee_name": ""} for r in body["rows"]]
        if self.break_put:
            self.break_put = False
            return {"rows": rows[1:]}  # PRBC kutilmaganda qatorni yo'qotdi
        self.rows[cid] = rows
        return {"rows": rows}

    def puts(self):
        return [w for w in self.writes if w[0] == "PUT"]


SCREEN = "Заявок пока нет\nДля вашей организации ещё не включено ни одно подключение к 1С."


class Base(TestCase):
    def setUp(self):
        self.conn, _ = Connection.objects.update_or_create(pk=1, defaults={
            "enabled": True, "phone": "998900000000", "password_enc": encrypt("x")})
        self.p = FakePrbc()

    def run_(self, text, tg=10, ocr="", asked=False, username="", group=""):
        return access.handle(text, ocr, tg_id=tg, username=username, group_title=group, asked=asked, client=self.p,
                             conn=Connection.get())


class DetectTests(TestCase):
    def test_questions(self):
        for t in ("yangi tochka qo'sha olmayapman", "Янги точка кушолмаяпман", "new client qoshish ishlamayapti",
                  "Не могу добавить новую точку", "tochka qo'shish funksiyasi yo'q", "Yangi klient ochib bo'lmayapti",
                  "нету кнопки добавить точку"):
            self.assertTrue(access.is_access_question(t), t)
        for t in ("yangi tochka qo'shib bering", "Akciya qo'shilmayapti", "Salom, kod kelmayapti", "zakaz o'tmayapti"):
            self.assertFalse(access.is_access_question(t), t)
        self.assertTrue(access.is_access_question("", SCREEN))
        self.assertTrue(access.is_access_question("shu chiqyapti", SCREEN))

    def test_fold(self):
        self.assertEqual(access.fold("Qarshi K-3", spaces=False), access.fold("Карши К3", spaces=False))
        self.assertEqual(access.fold("qo'sha"), access.fold("қўша"))


class HandleTests(Base):
    def test_not_access_question_touches_nothing(self):
        self.assertIsNone(self.run_("aksiya qo'shilmayapti"))
        self.assertEqual(self.p.calls, [])

    def test_fixes_seat_and_mapping_from_text(self):
        r = self.run_("yangi tochka qo'sha olmayapman, pozivnoy 2.1 Навои SR3")
        self.assertEqual(r.kind, "answer")
        self.assertIn("🔧", r.text)
        self.assertIn("2.1 Навои SR3 (food)", r.text)
        self.assertIn("yopib qayta oching", r.text)
        self.assertEqual(self.p.seats[10], "employee")
        put = self.p.puts()
        self.assertEqual(len(put), 1)
        self.assertEqual(put[0][1], "/integrations/connections/1/employee-mappings/")
        self.assertEqual(put[0][2]["rows"], [{"user_id": 11, "external_guid": "G1"}, {"user_id": 10, "external_guid": "G3"}])
        self.assertEqual(set(AccessLog.objects.filter(ok=True).values_list("action", flat=True)),
                         {"seat", "mapping", "check"})
        self.assertNotIn(("GET", "/integrations/connections/3/employee-mappings/"), self.p.calls)  # food_copy — hech qachon
        self.assertNotIn(("GET", "/integrations/connections/3/refs/"), self.p.calls)

    def test_latin_pozivnoy_without_code(self):
        r = self.run_("yangi tochka qo'sha olmayapman\nNavoi SR3")
        self.assertEqual(r.kind, "answer")
        self.assertEqual(self.p.puts()[0][2]["rows"][-1], {"user_id": 10, "external_guid": "G3"})  # SR31 emas

    def test_asks_pozivnoy_then_fixes(self):
        r = self.run_("yangi tochka qo'sha olmayapman")
        self.assertEqual(r.kind, "ask")
        self.assertIn("Pozivnoyingizni yozing", r.text)
        self.assertIn("🔧", r.text)  # ruxsat shu zahoti berildi
        self.assertEqual(self.p.puts(), [])
        r = self.run_("yangi tochka qo'sha olmayapman\n2.1 Навои SR3", asked=True)
        self.assertEqual(r.kind, "answer")
        self.assertEqual(len(self.p.puts()), 1)

    def test_unknown_pozivnoy_after_ask_goes_to_it(self):
        r = self.run_("yangi tochka qo'sha olmayapman\nbilmayman", asked=True)
        self.assertEqual(r.kind, "escalate")
        self.assertIn("IT mutaxassisi", r.text)
        self.assertEqual(self.p.puts(), [])

    def test_taken_pozivnoy_is_not_reassigned(self):
        r = self.run_("yangi tochka qo'sha olmayapman 2.3 Карши К-3")
        self.assertEqual(r.kind, "escalate")
        self.assertIn("ABDIRAIMOVA MUHSINA", r.text)
        self.assertEqual(self.p.puts(), [])

    def test_same_name_in_both_bases_follows_project(self):
        r = self.run_("yangi tochka qo'sha olmayapman 3.2 Фергана К-4")  # MDLZ bo'limi -> food
        self.assertEqual(r.kind, "answer")
        self.assertEqual(self.p.puts()[0][1], "/integrations/connections/1/employee-mappings/")
        r = self.run_("yangi tochka qo'sha olmayapman 3.2 Фергана К-4", tg=15)  # LOREAL ROP -> nonfood
        self.assertEqual(r.kind, "answer")
        self.assertEqual(self.p.puts()[1][1], "/integrations/connections/2/employee-mappings/")

    def test_short_name_and_base_choice(self):
        r = self.run_("yangi tochka qo'sha olmayapman ТП1", tg=15)
        self.assertEqual(r.kind, "answer")
        self.assertEqual(self.p.puts()[0][2]["rows"][-1], {"user_id": 15, "external_guid": "N3"})
        self.p.details[14] = {"assignments": []}
        r = self.run_("yangi tochka qo'sha olmayapman SR-8 Tashkent", tg=14)  # bo'limsiz: ikkala bazada bor
        self.assertEqual(r.kind, "ask")
        self.assertIn("SR8 Tashkent (food)", r.text)
        self.assertIn("SR-8 Tashkent (nonfood)", r.text)
        r = self.run_("yangi tochka qo'sha olmayapman SR-8 Tashkent\nnonfood", tg=14, asked=True)
        self.assertEqual(r.kind, "answer")
        self.assertEqual(self.p.puts()[-1][2]["rows"][-1], {"user_id": 14, "external_guid": "N4"})

    def test_inactive_is_not_touched(self):
        r = self.run_("yangi tochka qo'sha olmayapman 2.1 Навои SR3", tg=12)
        self.assertEqual(r.kind, "escalate")
        self.assertEqual(self.p.writes, [])

    def test_unexpected_save_restores_list(self):
        self.p.break_put = True
        r = self.run_("yangi tochka qo'sha olmayapman 2.1 Навои SR3")
        self.assertEqual(r.kind, "escalate")
        puts = self.p.puts()
        self.assertEqual(len(puts), 2)
        self.assertEqual(puts[1][2]["rows"], [{"user_id": 11, "external_guid": "G1"}])  # avvalgi ro'yxat qaytarildi
        self.assertEqual([r["external_guid"] for r in self.p.rows[1]], ["G1"])

    def test_all_ok(self):
        r = self.run_("shu chiqyapti", tg=11, ocr=SCREEN)
        self.assertEqual(r.kind, "answer")
        self.assertNotIn("🔧", r.text)
        self.assertIn("2.3 Карши К-3 (food)", r.text)
        self.assertIsNone(self.run_("yangi tochka qo'shdim lekin chiqmayapti", tg=11))  # ekransiz — oddiy javob
        self.assertEqual(self.p.writes, [])

    def test_mentions(self):
        r = self.run_("@StargroupSaid yangi tochka qo'sha olmayapman 2.1 Навои SR3", tg=10)  # IT xodimi tekshirilmaydi
        self.assertIn("ISMOILOV SHOHRUH", r.text)
        r = self.run_("@ali_tp ga yangi tochka qo'shish funksiyasi yo'q", tg=13, username="StargroupSaid")
        self.assertIn("ALI TP", r.text)

    def test_role_node_seat_for_new_tp(self):
        r = self.run_("yangi tochka qo'sha olmayapman 5.1 Самарканд К-1", tg=14)
        self.assertEqual(r.kind, "answer")
        paths = [w[1] for w in self.p.writes]
        self.assertIn("/auth/admin/users/14/roles/", paths)
        self.assertIn("/auth/admin/users/14/nodes/77/primary/", paths)
        self.assertEqual(self.p.seats[14], "employee")  # Ko'ruvchi -> Xodim
        self.assertEqual(self.p.puts()[0][1], "/integrations/connections/2/employee-mappings/")

    def test_node_from_group_title(self):
        self.p.details[14] = {"assignments": []}
        self.run_("yangi tochka qo'sha olmayapman 5.1 Самарканд К-1", tg=14, group="LOREAL ROP")
        self.assertIn(("POST", "/auth/admin/users/14/nodes/", {"hierarchy_node_id": 50, "is_primary": True}), self.p.writes)

    def test_autofix_off_only_reports(self):
        Connection.objects.filter(pk=1).update(access_autofix=False)
        r = self.run_("yangi tochka qo'sha olmayapman 2.1 Навои SR3")
        self.assertEqual(r.kind, "escalate")
        self.assertEqual(self.p.writes, [])

    def test_bot_switch_and_prbc_down(self):
        Connection.objects.filter(pk=1).update(access_bot=False)
        self.assertIsNone(self.run_("yangi tochka qo'sha olmayapman"))
        Connection.objects.filter(pk=1).update(access_bot=True)
        with mock.patch.object(self.p, "get", side_effect=PrbcError("timeout")):
            self.assertIsNone(self.run_("yangi tochka qo'sha olmayapman"))

    def test_unknown_telegram(self):
        r = self.run_("yangi tochka qo'sha olmayapman", tg=999)
        self.assertEqual(r.kind, "escalate")
        self.assertEqual(self.p.writes, [])


class ScanTests(Base):
    def test_scan_fixes_seat_role_node_not_mapping(self):
        rep = access.scan(Connection.get(), client=self.p)
        seat_posts = [w for w in self.p.writes if w[1].endswith("/integration-access/")]
        self.assertEqual(len(seat_posts), 1)  # bitta so'rov bilan
        self.assertEqual(sorted(seat_posts[0][2]["user_ids"]), [10, 14, 15])  # faol savdo vakillari; IT va ketgan emas
        self.assertIn(("POST", "/auth/admin/users/14/roles/", {"role_code": "employee", "organization_id": 3}), self.p.writes)
        self.assertIn(("POST", "/auth/admin/users/14/nodes/77/primary/", None), self.p.writes)
        self.assertEqual(self.p.puts(), [])  # pozivnoy taxmin qilinmaydi
        self.assertEqual(rep["counts"]["active"], 4)
        self.assertEqual(rep["counts"]["mapping"], 3)
        self.assertEqual(rep["counts"]["ok"], 1)
        row = next(r for r in rep["rows"] if r["id"] == 14)
        self.assertEqual(sorted(row["fixed"]), ["node", "role", "seat"])
        self.assertEqual(row["issues"], ["mapping"])
        c = Connection.get()
        self.assertIsNotNone(c.access_scan_at)
        self.assertEqual(c.access_report["counts"]["active"], 4)

    def test_scan_without_autofix_writes_nothing(self):
        rep = access.scan(Connection.get(), client=self.p, autofix=False)
        self.assertEqual(self.p.writes, [])
        self.assertEqual(rep["counts"]["seat"], 3)

    def test_scan_due(self):
        c = Connection.get()
        self.assertTrue(access.scan_due(c))
        access.scan(c, client=self.p, autofix=False)
        c = Connection.get()
        self.assertFalse(access.scan_due(c))
        c.access_scan_minutes = 0
        self.assertFalse(access.scan_due(c))
        c.access_scan_requested = True
        self.assertTrue(access.scan_due(c))


class BotFlowTests(FlowBase):
    """To'liq oqim: guruhda savol -> bot ruxsat beradi va pozivnoy so'raydi -> xodim javob qiladi -> biriktiriladi."""

    def setUp(self):
        super().setUp()
        Settings.objects.update(ai_enabled=False, ai_primary=False)
        Connection.objects.update_or_create(pk=1, defaults={"enabled": True, "phone": "998900000000",
                                                            "password_enc": encrypt("x")})
        self.p = FakePrbc()
        patcher = mock.patch("prbc.access.make_client", return_value=self.p)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ask_then_fix(self):
        h = self.h()
        h.handle(group_msg(1, 10, "Assalomu alaykum yangi tochka qo'sha olmayapman"))
        q = Message.objects.get(kind=Message.QUESTION)
        self.assertEqual(q.stage, "ask")
        self.assertTrue(q.bot_reply_id)
        texts = [x["text"] for x in visible(self.tg)]
        self.assertTrue(any("Pozivnoyingizni yozing" in t for t in texts), texts)
        self.assertEqual(self.p.seats[10], "employee")
        h.handle(group_msg(2, 10, "2.1 Навои SR3", reply_to=q.bot_reply_id))
        q.refresh_from_db()
        self.assertEqual(q.status, Message.ANSWERED)
        self.assertEqual(q.stage, "prbc")
        self.assertIn("2.1 Навои SR3 (food)", q.answer_text)
        self.assertEqual(len(self.p.puts()), 1)
        self.assertTrue(any("yopib qayta oching" in x["text"] for x in visible(self.tg)))

    def test_taken_goes_to_staff_with_findings(self):
        self.h().handle(group_msg(1, 10, "yangi tochka qo'sha olmayapman 2.3 Карши К-3"))
        q = Message.objects.get(kind=Message.QUESTION)
        self.assertEqual(q.status, Message.ESCALATED)
        last = visible(self.tg)[-1]["text"]
        self.assertIn("ABDIRAIMOVA MUHSINA", last)
        self.assertIn("qabul qilindi", last)
        self.assertEqual(self.p.puts(), [])
