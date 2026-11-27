"""«Yangi tochka» ruxsatlari (prbc.access): tanish, tekshirish, ruxsat bilan to'g'rilash, xodimdan so'rash, ortga
qaytarish, sinov, nazorat — soxta PRBC bilan. Javob shakllari prbc.uz'dagi haqiqiy /auth/admin/users/, user detail
(assignments, role_assignments), integration-access, employee-mappings va refs javoblaridan (2026-11-27, faqat GET
bilan o'qilgan; ismlar o'zgartirilgan)."""
import copy
import re
from unittest import mock

from django.test import TestCase

from support.models import Message, Settings
from support.tests import group_msg, visible
from support.tests_v6 import FlowBase
from zona.crypto import encrypt

from . import access, outlets
from .actions import KEYS
from .client import PrbcError
from .models import AccessLog, Connection

NODES = [{"id": 37, "parent_id": 1, "name": "MDLZ TASHKENT", "code": "", "node_type": "department", "is_active": True},
         {"id": 50, "parent_id": 2, "name": "LOREAL ROP", "code": "", "node_type": "department", "is_active": True},
         {"id": 51, "parent_id": 2, "name": "Support", "code": "", "node_type": "department", "is_active": True}]
ALL = {k: True for k in KEYS}


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
                         {"guid": "G5", "name": "SR8 Tashkent", "active": True},
                         {"guid": "G6", "name": "1 Ташкент SR1", "active": True},
                         {"guid": "G7", "name": "2 Ташкент SR11", "active": True}],
                     2: [{"guid": "N1", "name": "3.2 Фергана К-4", "active": True},
                         {"guid": "N2", "name": "5.1 Самарканд К-1", "active": True},
                         {"guid": "N3", "name": "ТП1", "active": True},
                         {"guid": "N4", "name": "SR-8 Tashkent", "active": True}],
                     3: [{"guid": "T9", "name": "9.9 Test K-9", "active": True}]}
        self.details = {}
        for u in self.users:
            a = [{"id": 300 + u["id"], "hierarchy_node_id": u["primary_node_id"], "hierarchy_node_name": u["primary_node_name"],
                  "is_primary": True}] if u["primary_node_id"] else []
            r = [{"id": 400 + u["id"], "role_code": c, "organization_id": 3} for c in u["role_codes"]]
            self.details[u["id"]] = {"assignments": a, "role_assignments": r}
        self.details[14]["assignments"] = [{"id": 77, "hierarchy_node_id": 37, "hierarchy_node_name": "MDLZ TASHKENT",
                                            "is_primary": False}]
        self.next_id = 900

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
            return copy.deepcopy(self.details.get(int(m.group(1)), {"assignments": []}))
        m = re.match(r"/admin/organization-modules/3/(task|chat)-access/$", path)
        if m:
            return self.mod_roster(m.group(1))
        raise AssertionError(path)

    mod_seats = None

    def mod_roster(self, mod):
        self.mod_seats = self.mod_seats or {"task": {11: "member", 13: "admin"}, "chat": {}}
        return {"members": [{"id": i, "level": lv} for i, lv in self.mod_seats[mod].items() if lv != "none"], "candidates": []}

    def roster(self):
        return {"members": [{"id": i, "full_name": "", "position": "", "level": lv} for i, lv in self.seats.items() if lv != "none"],
                "candidates": []}

    def post(self, path, body=None):
        self.writes.append(("POST", path, body))
        if path.endswith("/integration-access/"):
            for i in body["user_ids"]:
                self.seats[i] = body["level"]
            return self.roster()
        m = re.match(r"/admin/organization-modules/3/(task|chat)-access/$", path)
        if m:
            self.mod_roster(m.group(1))
            for i in body["user_ids"]:
                self.mod_seats[m.group(1)][i] = body["level"]
            return self.mod_roster(m.group(1))
        m = re.match(r"/auth/admin/users/(\d+)/(roles|nodes)/$", path)
        if m:
            uid, kind = int(m.group(1)), m.group(2)
            self.next_id += 1
            if kind == "roles":
                self.details[uid].setdefault("role_assignments", []).append({"id": self.next_id, "role_code": body["role_code"]})
            else:
                n = next(x for x in NODES if x["id"] == body["hierarchy_node_id"])
                self.details[uid]["assignments"].append({"id": self.next_id, "hierarchy_node_id": n["id"],
                                                         "hierarchy_node_name": n["name"], "is_primary": body["is_primary"]})
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
    actions = ALL

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.conn, _ = Connection.objects.update_or_create(pk=1, defaults={
            "enabled": True, "phone": "998900000000", "password_enc": encrypt("x"), "auto_actions": dict(self.actions)})
        self.p = FakePrbc()

    def run_(self, text, tg=10, ocr="", asked=False, username="", group="", question=None):
        return access.handle(text, ocr, tg_id=tg, username=username, group_title=group, asked=asked, client=self.p,
                             conn=Connection.get(), question=question)


class DetectTests(TestCase):
    def test_questions(self):
        for t in ("yangi tochka qo'sha olmayapman", "Янги точка кушолмаяпман", "new client qoshish ishlamayapti",
                  "Не могу добавить новую точку", "tochka qo'shish funksiyasi yo'q", "Yangi klient ochib bo'lmayapti",
                  "нету кнопки добавить точку"):
            self.assertTrue(access.is_access_question(t), t)
        for t in ("yangi tochka qo'shib bering", "Akciya qo'shilmayapti", "Salom, kod kelmayapti", "zakaz o'tmayapti",
                  "Долго грузит и выдает ошибку"):
            self.assertFalse(access.is_access_question(t), t)
        self.assertTrue(access.is_access_question("", SCREEN))
        self.assertTrue(access.is_access_question("shu chiqyapti", SCREEN))

    def test_fold(self):
        self.assertEqual(access.fold("Qarshi K-3", spaces=False), access.fold("Карши К3", spaces=False))
        self.assertEqual(access.fold("qo'sha"), access.fold("қўша"))


class DefaultOnlyDiagnoseTests(Base):
    """Standart: hech bir amal yoqilmagan — bot aniqlaydi, javobda yozadi, mutaxassisga uzatadi; PRBC o'zgarmaydi."""
    actions = {}

    def test_finds_but_changes_nothing(self):
        r = self.run_("yangi tochka qo'sha olmayapman 2.1 Навои SR3", group="LOREAL ROP")
        self.assertEqual(r.kind, "escalate")
        self.assertEqual(self.p.writes, [])
        self.assertIn("kerak: yo'q → Xodim", r.text)
        self.assertIn("kerak: 2.1 Навои SR3 (food bazasi) biriktirish", r.text)
        self.assertIn("LOREAL ROP bo'limiga qo'shish", r.text)
        self.assertIn("avtomatik o'zgartirish o'chiq", r.text)
        self.assertEqual({k for k, _n in r.planned}, {"seat", "mapping", "node"})
        self.assertFalse(AccessLog.objects.filter(ok=True).exclude(action__in=["check", "ask"]).exists())

    def test_still_asks_missing_pozivnoy(self):
        r = self.run_("yangi tochka qo'sha olmayapman", question=1)
        self.assertEqual(r.kind, "ask")  # avval yetmagan ma'lumot so'raladi — mutaxassis to'liq ma'lumot bilan oladi
        r = self.run_("yangi tochka qo'sha olmayapman\n2.1 Навои SR3", asked=True, question=1)
        self.assertEqual(r.kind, "escalate")
        self.assertIn("kerak: 2.1 Навои SR3 (food bazasi) biriktirish", r.text)
        self.assertEqual(self.p.writes, [])

    def test_only_mapping_missing_asks(self):
        self.p.seats[10] = "employee"
        r = self.run_("yangi tochka qo'sha olmayapman", question=1)
        self.assertEqual(r.kind, "ask")
        self.assertIn("to'liq yozing", r.text)


class HandleTests(Base):
    def test_not_access_question_touches_nothing(self):
        self.assertIsNone(self.run_("aksiya qo'shilmayapti"))
        self.assertEqual(self.p.calls, [])

    def test_fixes_seat_and_mapping_with_details(self):
        r = self.run_("yangi tochka qo'sha olmayapman, pozivnoy 2.1 Навои SR3")
        self.assertEqual(r.kind, "answer")
        self.assertIn("🔧 «Integratsiyalar» ruxsati: yo'q → Xodim (berildi)", r.text)
        self.assertIn("🔧 1C pozivnoy (savdo vakili): 2.1 Навои SR3 (food bazasi) biriktirildi", r.text)
        self.assertIn("yopib qayta oching", r.text)
        put = self.p.puts()
        self.assertEqual(len(put), 1)
        self.assertEqual(put[0][2]["rows"], [{"user_id": 11, "external_guid": "G1"}, {"user_id": 10, "external_guid": "G3"}])
        seat = AccessLog.objects.get(action="seat")
        self.assertEqual((seat.before, seat.after, seat.reversible), ({"level": "none"}, {"level": "employee"}, True))
        m = AccessLog.objects.get(action="mapping")
        self.assertEqual(m.after["guid"], "G3")
        self.assertNotIn(("GET", "/integrations/connections/3/employee-mappings/"), self.p.calls)  # food_copy — hech qachon

    def test_latin_pozivnoy_without_code(self):
        r = self.run_("yangi tochka qo'sha olmayapman\nNavoi SR3")
        self.assertEqual(r.kind, "answer")
        self.assertEqual(self.p.puts()[0][2]["rows"][-1], {"user_id": 10, "external_guid": "G3"})  # SR31 emas

    def test_partial_pozivnoy_asks_full_then_links(self):
        r = self.run_("yangi tochka qo'sha olmayapman", question=5)
        self.assertEqual(r.kind, "ask")
        r = self.run_("yangi tochka qo'sha olmayapman\nsr1", asked=True, question=5)
        self.assertEqual(r.kind, "ask")
        self.assertIn("to'liq nomini aynan yozing", r.text)
        self.assertIn("1 Ташкент SR1 (food)", r.text)
        self.assertIn("2 Ташкент SR11 (food)", r.text)
        self.assertEqual(self.p.puts(), [])
        r = self.run_("yangi tochka qo'sha olmayapman\nsr1\n1 Ташкент SR1", asked=True, question=5)
        self.assertEqual(r.kind, "answer")
        self.assertEqual(self.p.puts()[0][2]["rows"][-1], {"user_id": 10, "external_guid": "G6"})

    def test_unknown_pozivnoy_reasks_then_it(self):
        r = self.run_("yangi tochka qo'sha olmayapman\nbilmayman", asked=True, question=7)
        self.assertEqual(r.kind, "ask")
        self.assertIn("topilmadi", r.text)
        self.run_("yangi tochka qo'sha olmayapman\nbilmayman\nyo'q", asked=True, question=7)
        self.run_("yangi tochka qo'sha olmayapman\nbilmayman\nyo'q\nhali", asked=True, question=7)
        r = self.run_("yangi tochka qo'sha olmayapman\nbilmayman\nyo'q\nhali\nxx", asked=True, question=7)
        self.assertEqual(r.kind, "escalate")  # 3 marta so'raldi — mutaxassis
        self.assertIn("IT mutaxassisi", r.text)
        self.assertEqual(self.p.puts(), [])

    def test_refresh_refs_when_not_found(self):
        def refresh(path, body=None):
            self.p.writes.append(("POST", path, body))
            self.p.reps[1].append({"guid": "G9", "name": "7.7 Янги К-7", "active": True})
            return {}
        with mock.patch.object(self.p, "post", side_effect=lambda path, body=None: refresh(path, body)
                               if "refresh-refs" in path else FakePrbc.post(self.p, path, body)):
            r = self.run_("yangi tochka qo'sha olmayapman\n7.7 Янги К-7", asked=True, question=9)
        self.assertEqual(r.kind, "answer")
        self.assertEqual(self.p.puts()[0][2]["rows"][-1], {"user_id": 10, "external_guid": "G9"})

    def test_taken_pozivnoy_is_not_reassigned(self):
        r = self.run_("yangi tochka qo'sha olmayapman 2.3 Карши К-3")
        self.assertEqual(r.kind, "escalate")
        self.assertIn("ABDIRAIMOVA MUHSINA", r.text)
        self.assertEqual(self.p.puts(), [])

    def test_same_name_in_both_bases_follows_project_or_group(self):
        r = self.run_("yangi tochka qo'sha olmayapman 3.2 Фергана К-4")  # MDLZ bo'limi -> food
        self.assertEqual(self.p.puts()[0][1], "/integrations/connections/1/employee-mappings/")
        r = self.run_("yangi tochka qo'sha olmayapman 3.2 Фергана К-4", tg=15)  # LOREAL ROP -> nonfood
        self.assertEqual(r.kind, "answer")
        self.assertEqual(self.p.puts()[1][1], "/integrations/connections/2/employee-mappings/")

    def test_short_name_and_base_choice(self):
        r = self.run_("yangi tochka qo'sha olmayapman ТП1", tg=15)
        self.assertEqual(r.kind, "answer")
        self.assertEqual(self.p.puts()[0][2]["rows"][-1], {"user_id": 15, "external_guid": "N3"})
        self.p.details[14]["assignments"] = []
        r = self.run_("yangi tochka qo'sha olmayapman SR-8 Tashkent", tg=14, question=3)  # bo'limsiz: ikkala bazada
        self.assertEqual(r.kind, "ask")
        self.assertIn("SR8 Tashkent (food)", r.text)
        self.assertIn("SR-8 Tashkent (nonfood)", r.text)
        r = self.run_("yangi tochka qo'sha olmayapman SR-8 Tashkent\nnonfood", tg=14, asked=True, question=3)
        self.assertEqual(r.kind, "answer")
        self.assertEqual(self.p.puts()[-1][2]["rows"][-1], {"user_id": 14, "external_guid": "N4"})

    def test_node_by_group(self):
        r = self.run_("yangi tochka qo'sha olmayapman 2.1 Навои SR3", group="LOREAL ROP")
        self.assertIn(("POST", "/auth/admin/users/10/nodes/", {"hierarchy_node_id": 50, "is_primary": False}), self.p.writes)
        self.assertIn("LOREAL ROP bo'limiga qo'shildi", r.text)  # asosiy bo'lim (MDLZ TASHKENT) o'zgarmaydi
        e = AccessLog.objects.get(action="node")
        self.assertEqual((e.after["node_id"], e.after["primary"]), (50, False))
        self.assertTrue(e.after["assignment_id"])
        self.p.writes.clear()
        self.run_("yangi tochka qo'sha olmayapman", tg=15, group="LOREAL ROP")  # allaqachon shu bo'limda
        self.assertFalse([w for w in self.p.writes if "/nodes/" in w[1]])

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
        r = self.run_("@ali_tp ga yangi tochka qo'shish funksiyasi yo'q", tg=13, username="StargroupSaid", question=2)
        self.assertIn("ALI TP", r.text)

    def test_role_primary_seat_for_new_tp(self):
        r = self.run_("yangi tochka qo'sha olmayapman 5.1 Самарканд К-1", tg=14)
        self.assertEqual(r.kind, "answer")
        paths = [w[1] for w in self.p.writes]
        self.assertIn("/auth/admin/users/14/roles/", paths)
        self.assertIn("/auth/admin/users/14/nodes/77/primary/", paths)
        self.assertEqual(self.p.seats[14], "employee")  # Ko'ruvchi -> Xodim
        self.assertIn("Ko'ruvchi → Xodim (berildi)", r.text)
        self.assertEqual(AccessLog.objects.get(action="role").after["assignment_id"], 901)

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


class RevertTests(Base):
    def test_revert_each_change(self):
        self.run_("yangi tochka qo'sha olmayapman 5.1 Самарканд К-1", tg=14, group="LOREAL ROP")
        self.run_("yangi tochka qo'sha olmayapman 2.1 Навои SR3", tg=10, group="LOREAL ROP")
        self.p.writes.clear()
        for e in AccessLog.objects.filter(ok=True, reversible=True).order_by("id"):
            ok, text = access.revert(e, actor="admin", client=self.p)
            self.assertTrue(ok, (e.action, text))
        paths = [w[1] for w in self.p.writes]
        self.assertIn("/auth/admin/users/14/roles/901/remove/", paths)
        self.assertIn(("POST", "/admin/organization-modules/3/integration-access/",
                       {"level": "viewer", "user_ids": [14], "include_subtree": False}), self.p.writes)
        self.assertEqual(self.p.seats[10], "none")
        self.assertEqual([r["external_guid"] for r in self.p.rows[1]], ["G1"])  # Muhsinaniki joyida
        self.assertEqual(self.p.rows[2], [])
        self.assertTrue(any(p.startswith("/auth/admin/users/10/nodes/") and p.endswith("/remove/") for p in paths))
        self.assertEqual(AccessLog.objects.filter(action="revert", ok=True).count(), 7)
        e = AccessLog.objects.filter(action="seat").first()
        self.assertEqual(access.revert(e, client=self.p), (False, "Allaqachon qaytarilgan"))

    def test_primary_flag_is_not_auto_reverted(self):
        self.run_("yangi tochka qo'sha olmayapman 5.1 Самарканд К-1", tg=14)
        e = AccessLog.objects.get(action="node")
        ok, text = access.revert(e, client=self.p)
        self.assertFalse(ok)
        self.assertIn("qo'lda", text)


class SimulateTests(Base):
    actions = {"seat": True}

    def test_simulate_writes_nothing(self):
        r = access.simulate(10, "yangi tochka qo'sha olmayapman 2.1 Навои SR3", "LOREAL ROP", client=self.p,
                            conn=Connection.get())
        self.assertEqual(self.p.writes, [])
        self.assertIn("🧪 Sinov", r["text"])
        planned = {x["key"]: x["enabled"] for x in r["planned"]}
        self.assertEqual(planned, {"node": False, "seat": True, "mapping": False})
        self.assertFalse(AccessLog.objects.exists())


class OutletResendTests(Base):
    BUSY = {"id": 5, "status": "failed", "can_send": True, "outlet_name": "Do'kon", "inn": "301111111",
            "last_error": "DMS refused: База занята другим пользователем"}
    DATA = {"id": 6, "status": "failed", "can_send": True, "outlet_name": "Boshqa", "inn": "301111112",
            "last_error": "DMS refused: REF_MISMATCH Подразделение не относится к сотруднику"}

    def test_resend_only_transient_and_only_when_allowed(self):
        found = {"301111111": {"requests": [self.BUSY]}, "301111112": {"requests": [self.DATA]}}
        lines = outlets.resend_failed(found, client=self.p, conn=Connection.get())
        self.assertEqual(self.p.writes, [("POST", "/integrations/outlet-requests/5/send/", None)])
        self.assertEqual(len(lines), 1)
        self.assertIn("qayta yuborildi", lines[0])
        Connection.objects.filter(pk=1).update(auto_actions={})
        self.p.writes.clear()
        lines = outlets.resend_failed(found, client=self.p, conn=Connection.get())
        self.assertEqual(self.p.writes, [])
        self.assertIn("mutaxassis bajaradi", lines[0])


class ScanTests(Base):
    def test_scan_reports_only(self):
        rep = access.scan(Connection.get(), client=self.p)
        self.assertEqual(self.p.writes, [])  # nazorat hech narsa o'zgartirmaydi — faqat savoldan kelib chiqib
        self.assertEqual(rep["counts"]["active"], 4)
        self.assertEqual(rep["counts"]["mapping"], 3)
        self.assertEqual(rep["counts"]["seat"], 3)
        self.assertEqual(rep["counts"]["ok"], 1)
        c = Connection.get()
        self.assertIsNotNone(c.access_scan_at)
        self.assertEqual(c.access_report["counts"]["active"], 4)

    def test_scan_due(self):
        c = Connection.get()
        self.assertTrue(access.scan_due(c))
        access.scan(c, client=self.p)
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
                                                            "password_enc": encrypt("x"), "auto_actions": dict(ALL)})
        self.p = FakePrbc()
        patcher = mock.patch("prbc.access.make_client", return_value=self.p)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ask_partial_then_fix(self):
        h = self.h()
        h.handle(group_msg(1, 10, "Assalomu alaykum yangi tochka qo'sha olmayapman"))
        q = Message.objects.get(kind=Message.QUESTION)
        self.assertEqual(q.stage, "ask")
        self.assertEqual(self.p.seats[10], "employee")
        h.handle(group_msg(2, 10, "sr1", reply_to=q.bot_reply_id))
        q.refresh_from_db()
        self.assertEqual(q.stage, "ask")
        self.assertTrue(any("1 Ташкент SR1 (food)" in x["text"] for x in visible(self.tg)))
        h.handle(group_msg(3, 10, "1 Ташкент SR1", reply_to=q.bot_reply_id))
        q.refresh_from_db()
        self.assertEqual(q.status, Message.ANSWERED)
        self.assertEqual(q.stage, "prbc")
        self.assertIn("1 Ташкент SR1 (food bazasi) biriktirildi", q.answer_text)
        self.assertEqual(len(self.p.puts()), 1)

    def test_default_diagnose_goes_to_staff_with_findings(self):
        Connection.objects.filter(pk=1).update(auto_actions={})
        self.h().handle(group_msg(1, 10, "yangi tochka qo'sha olmayapman 2.1 Навои SR3"))
        q = Message.objects.get(kind=Message.QUESTION)
        self.assertEqual(q.status, Message.ESCALATED)
        last = visible(self.tg)[-1]["text"]
        self.assertIn("kerak:", last)
        self.assertIn("qabul qilindi", last)
        self.assertEqual(self.p.writes, [])


class ModuleSeatTests(Base):
    actions = {}

    def mod(self, text, tg=10, ocr=""):
        from . import modules
        return modules.handle(text, ocr, tg_id=tg, client=self.p, conn=Connection.get(), question=4)

    def test_default_only_reports(self):
        r = self.mod("PRBC da vazifalar ko'rinmayapti")
        self.assertEqual(r.kind, "escalate")
        self.assertIn("kerak: A'zo", r.text)
        self.assertIn("avtomatik o'zgartirish o'chiq", r.text)
        self.assertEqual(self.p.writes, [])

    def test_grants_member_and_reverts(self):
        Connection.objects.filter(pk=1).update(auto_actions={"task_seat": True, "chat_seat": True})
        r = self.mod("PRBC chat ochilmayapti")
        self.assertEqual(r.kind, "answer")
        self.assertIn("yo'q → A'zo (berildi)", r.text)
        self.assertEqual(self.p.mod_seats["chat"][10], "member")
        e = AccessLog.objects.get(action="chat_seat")
        self.assertEqual((e.before, e.after["level"], e.reversible), ({"level": "none"}, "member", True))
        ok, _text = access.revert(e, actor="admin", client=self.p)
        self.assertTrue(ok)
        self.assertEqual(self.p.mod_seats["chat"][10], "none")

    def test_has_access_or_not_prbc_is_left_alone(self):
        Connection.objects.filter(pk=1).update(auto_actions={"task_seat": True})
        self.assertIsNone(self.mod("PRBC da vazifalar ko'rinmayapti", tg=11))  # ruxsati bor
        self.assertIsNone(self.mod("Не получается перейти в задание"))  # ProTarget ilovasi — PRBC emas
        self.assertFalse([w for w in self.p.writes if "task-access" in w[1]])

    def test_simulate_module(self):
        Connection.objects.filter(pk=1).update(auto_actions={"task_seat": True})
        r = access.simulate(10, "", client=self.p, conn=Connection.get(), mod="task")
        self.assertEqual(r["planned"][0]["key"], "task_seat")
        self.assertTrue(r["planned"][0]["enabled"])
        self.assertEqual(self.p.writes, [])


class TelegramSyncTests(Base):
    def test_sync_when_username_changed(self):
        r = access.handle("yangi tochka qo'sha olmayapman 2.1 Навои SR3", "", tg_id=10, username="shohruh_new",
                          client=self.p, conn=Connection.get())
        self.assertIn(("POST", "/auth/admin/users/10/telegram-sync/", None), self.p.writes)
        self.assertIn("@shohruh → @shohruh_new (yangilandi)", r.text)

    def test_no_sync_when_same_or_off(self):
        access.handle("yangi tochka qo'sha olmayapman", "", tg_id=10, username="Shohruh", client=self.p, conn=Connection.get())
        self.assertFalse([w for w in self.p.writes if "telegram-sync" in w[1]])
        Connection.objects.filter(pk=1).update(auto_actions={})
        access.handle("yangi tochka qo'sha olmayapman", "", tg_id=10, username="other", client=self.p, conn=Connection.get())
        self.assertFalse([w for w in self.p.writes if "telegram-sync" in w[1]])


class RouteResendTests(Base):
    def test_requeue_transient_attachment_only(self):
        busy = {"id": 8, "status": "failed", "counterparty_name": "Do'kon", "actions": ["requeue", "cancel"],
                "last_error": "HTTP 503 from DMS"}
        data = {"id": 9, "status": "failed", "counterparty_name": "Boshqa", "actions": ["requeue"],
                "last_error": "REF_NOT_FOUND Элемент не найден"}
        lines = outlets.resend_failed({"301111111": {"attachments": [busy]}, "301111112": {"attachments": [data]}},
                                      client=self.p, conn=Connection.get())
        self.assertEqual(self.p.writes, [("POST", "/integrations/route-attachments/8/requeue/", None)])
        self.assertIn("qayta yuborildi", lines[0])
        self.assertTrue(AccessLog.objects.filter(action="route_resend", ok=True).exists())
