"""Jamoa sahifasi (qatorlar jadvali / tablar) importi va Telegram ID bo'yicha xodimni aniq tanish."""
import json

from zona import staff_io
from zona.models import StaffPerson, StaffProject

from . import engine
from .models import TgUser
from .staffsync import link_staff
from .tests_v6 import FlowBase

ROW = lambda name, role, region, tg="", tgid="", co=None: [name, role, region, "+998 90 111 22 33", name, tg, "", tgid,  # noqa: E731
                                                       "Faol", f"{role} · Филиал", "", "Aniq", "", "", co]


def page(tabs, proj=None):
    head = "<html><head><title>Структура команды TESTPROJ</title></head><body><script>"
    body = (f"const ALL = {json.dumps(tabs, ensure_ascii=False)};" if len(tabs) > 1 else
            f"const DATA = {json.dumps(next(iter(tabs.values())), ensure_ascii=False)};")
    if proj:
        body += "const PROJ = [" + ",".join(f"['{k}','{v}','x']" for k, v in proj) + "];"
    return head + body + "</script></body></html>"


class TableImportTests(FlowBase):
    def test_single_table_hierarchy(self):
        rows = [ROW("BOSS ONE", "BDM", "Узбекистан"), ROW("Вакансия", "ТС", "Ташкент"), ROW("AGENT A", "ТА", "Ташкент", "agent_a", "111"),
                ROW("SUPER B", "ТС", "Ташкент", "sup_b", "222"), ROW("AGENT C", "ТА", "Ташкент"), ROW("MERCH D", "Мерчендайзер", "Ташкент"),
                ROW("TM E", "ТМ", "Ф-Д"), ROW("SUPER F", "ТС", "Ф-Д"), ROW("AGENT G", "ТА", "Ф-Д", "", "333")]
        doc = staff_io.parse(page({"": rows}))["TESTPROJ"]
        by = {p["name"] or p["key"]: p for p in doc["people"]}
        key = {p["key"]: p for p in doc["people"]}
        mgr = lambda n: (key.get(by[n]["manager"]) or {}).get("name")  # noqa: E731
        self.assertEqual((by["AGENT A"]["telegram_id"], by["AGENT A"]["telegram"]), ("111", "agent_a"))
        self.assertEqual(mgr("AGENT C"), "SUPER B")
        self.assertEqual(mgr("MERCH D"), "SUPER B")
        self.assertEqual(mgr("SUPER F"), "TM E")
        self.assertEqual(mgr("AGENT G"), "SUPER F")
        self.assertEqual(mgr("TM E"), "BOSS ONE")
        self.assertEqual(by["AGENT A"]["manager"], next(p["key"] for p in doc["people"] if p["vacancy"]))
        project, _res = staff_io.apply(doc)
        self.assertEqual(StaffPerson.objects.get(name="AGENT G").telegram_id, 333)
        self.assertEqual(StaffPerson.objects.get(name="AGENT G").manager.name, "SUPER F")

    def test_tabs_dedupe_and_co_supervisor(self):
        tabs = {"ev": [ROW("LEAD X", "РП", "Руководство"), ROW("SUP E", "ТС", "Ташкент"), ROW("AG 1", "ТА", "Ташкент"),
                       ROW("BOTH", "ТА", "Регионы")],
                "vs": [ROW("LEAD Y", "РП", "Руководство"), ROW("SUP M", "ТС", "Ташкент"), ROW("SUP CO", "ТС", "Ташкент", co=1),
                       ROW("AG 2", "ТА", "Ташкент"), ROW("BOTH", "ТА", "Регионы")]}
        doc = staff_io.parse(page(tabs, [("ev", "Eveline"), ("vs", "Vivienne Sabo")]))["TESTPROJ"]
        names = [p["name"] for p in doc["people"]]
        self.assertEqual(names.count("BOTH"), 1)
        key = {p["key"]: p for p in doc["people"]}
        by = {p["name"]: p for p in doc["people"]}
        self.assertEqual(key[by["AG 2"]["manager"]]["name"], "SUP M")  # qo'shimcha ТС agentlarni olib ketmaydi
        self.assertEqual(by["LEAD Y"]["manager"], "")  # har brend rahbari mustaqil
        self.assertIn("Vivienne Sabo · Ташкент", [u["title"] for u in doc["units"]])


class TelegramIdLinkTests(FlowBase):
    def test_identify_by_telegram_id_and_link_staff(self):
        proj = StaffProject.objects.create(name="TEST_P")
        sp = StaffPerson.objects.create(project=proj, name="Testova Aziza Karimovna", role="TP", telegram_id=900111)
        self.assertEqual(link_staff()["created"], 1)
        u = TgUser.objects.get(tg_id=900111)
        self.assertEqual((u.staff_person_id, u.staff_link), (sp.pk, "prbc"))
        u2 = engine.identify(900111, username="whatever", name="🌸")
        self.assertEqual(u2.staff_person_id, sp.pk)
        TgUser.objects.filter(pk=u.pk).update(staff_person=None, staff_link="none")  # qo'lda uzilgan — qayta bog'lanmaydi
        self.assertIsNone(engine.identify(900111, username="whatever", name="🌸").staff_person_id)
