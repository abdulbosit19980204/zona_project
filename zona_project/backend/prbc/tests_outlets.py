"""Mijoz arizasining PRBC'dagi jonli holati (prbc.outlets) va botdagi javob — soxta PRBC bilan.
Javob shakllari prbc.uz'dagi haqiqiy /integrations/outlet-requests/ javobidan olingan (nomlar o'zgartirilgan)."""
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from support import engine
from support.models import Entry, Settings
from zona.crypto import encrypt

from . import outlets
from .client import PrbcError
from .models import Connection

SENT = {
    "id": 3601, "status": "sent", "connection_code": "nonfood", "outlet_name": '"TEST SAVDO" MCHJ', "inn": "309035202",
    "pinfl": "", "dms_status": "created", "dms_outlet_code": "UZ-00069292", "dms_client_code": "42601987391223",
    "sales_rep_name": "2.1 Navoi SR3", "territory_name": "Navoiy", "phones": ["+998901234567"], "contact_person": "Ali",
    "route_state": "in_route", "protarget_state": "incomplete", "subdivision_state": "ok",
    "outcome_notes": {"route": "№ FIL-NAVLR000012", "protarget": "Нет кода в СоответствиеТиповТРТ_Протаргет — ProTarget "
                      "не получит тип для команд: 3"},
    "outcome_at": "2026-11-25T18:35:57+05:00", "sent_at": "2026-11-25T18:35:57+05:00", "last_error": "",
    "updated_at": "2026-11-25T18:36:00+05:00",
}
FAILED = {
    "id": 3550, "status": "failed", "connection_code": "food", "outlet_name": "Do'kon", "inn": "301111111", "pinfl": "",
    "dms_outlet_code": "", "dms_client_code": "", "route_state": None, "protarget_state": None, "subdivision_state": "error",
    "last_error": "DMS refused: sales_rep.subdivision_guid: REF_MISMATCH Подразделение не относится к сотруднику",
    "outcome_notes": {"subdivision": "Подразделение не относится к сотруднику"}, "updated_at": "2026-11-24T10:00:00+05:00",
}
OTHER = {**SENT, "id": 1, "inn": "309035203", "outlet_name": "Boshqa"}  # q qidiruvi o'xshashini ham qaytaradi


class FakeOutlets:
    def __init__(self, rows=(), attachments=(), fail=False):
        self.rows, self.attachments, self.fail, self.calls = list(rows), list(attachments), fail, []
        self.timeout = 30

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        if self.fail:
            raise PrbcError("PRBC serveriga ulanib bo'lmadi: timed out")
        if path == "/integrations/outlet-requests/":
            return {"count": len(self.rows), "results": self.rows}
        if path == "/integrations/route-attachments/":
            return {"count": len(self.attachments), "results": self.attachments}
        raise AssertionError(path)


class IdsTests(TestCase):
    def test_find_ids(self):
        self.assertEqual(outlets.find_ids("309035202 klient protargetda chiqmayapti"), ["309035202"])
        self.assertEqual(outlets.find_ids("STIR: 309 035 202"), ["309035202"])
        self.assertEqual(outlets.find_ids("pinfl 42601987391223, kodi uz-69292"), ["UZ-00069292", "42601987391223"])
        self.assertEqual(outlets.find_ids("УЗ 00069292"), ["UZ-00069292"])
        self.assertEqual(outlets.find_ids("tel: 901234567, +998 901234567"), [])  # telefon
        self.assertEqual(outlets.find_ids("zakaz 150 000 000 so'm"), [])  # summa
        self.assertEqual(outlets.find_ids("salom, nuqta chiqmayapti"), [])


class CardTests(TestCase):
    def setUp(self):
        outlets._cache.clear()

    def test_created_partial_protarget_explained_both_languages(self):
        fake = FakeOutlets([OTHER, SENT])
        found = outlets.lookup(["309035202"], client=fake)
        self.assertEqual([r["id"] for r in found["309035202"]["requests"]], [3601])  # faqat aniq mos STIR
        uz, ru = outlets.card(found, "uz"), outlets.card(found, "ru")
        for s in ("1C da yaratildi", "Marshrutda", "FIL-NAVLR000012", "Qisman", "UZ-00069292", "5–10 daqiqa", "1 soatgacha"):
            self.assertIn(s, uz)
        for s in ("Создана в 1С", "В маршруте", "Частично", "до 1 часа"):
            self.assertIn(s, ru)
        for private in ("+998901234567", "Ali"):
            self.assertNotIn(private, uz)  # telefon va aloqa shaxsi guruhga chiqmaydi

    def test_failed_subdivision_reason_and_fix(self):
        found = outlets.lookup(["301111111"], client=FakeOutlets([FAILED]))
        text = outlets.card(found, "uz")
        self.assertIn("1C rad etdi", text)
        self.assertIn("bo'linma bu savdo vakiliga tegishli emas", text)
        self.assertIn("qayta yuboring", text)

    def test_cache_and_errors(self):
        fake = FakeOutlets([SENT])
        outlets.lookup(["309035202"], client=fake)
        outlets.lookup(["309035202"], client=fake)
        self.assertEqual(sum(1 for p, _ in fake.calls if p == "/integrations/outlet-requests/"), 1)  # keshdan
        self.assertEqual(outlets.lookup(["309035299"], client=FakeOutlets(fail=True)), {})  # PRBC javob bermadi
        self.assertNotIn("309035299", outlets._cache)  # xato keshlanmaydi

    def test_route_attachment_shown(self):
        att = {"id": 9, "status": "sent", "inn": "309035202", "route_document_number": "STARMDLZ0000349",
               "route_posting_pending": True, "outlets": [{"code": "UZ-1"}, {"code": "UZ-2"}], "updated_at": "2026-11-25T10:00:00+05:00"}
        text = outlets.card(outlets.lookup(["309035202"], client=FakeOutlets([], [att])), "uz")
        self.assertIn("1C dagi marshrutga qo'shildi", text)
        self.assertIn("STARMDLZ0000349", text)
        self.assertIn("Hujjat hali o'tkazilmagan", text)


class BotLiveTests(TestCase):
    def setUp(self):
        outlets._cache.clear()
        c = Connection.get()
        c.enabled, c.phone, c.password_enc = True, "998900000000", encrypt("x")
        c.save()
        s = Settings.load()
        s.ai_enabled = False
        s.save()
        self.fake = FakeOutlets([SENT])
        patcher = mock.patch("prbc.outlets.Client", lambda conn: self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_status_question_answered_from_prbc(self):
        q = "309035202 klient protargetda chiqmayapti"
        d = engine.decide(q, "uz", text=q, live=True)
        self.assertEqual(d.stage, "prbc")
        self.assertFalse(d.needs_human)
        self.assertIn("1C da yaratildi", d.text)
        self.assertTrue(engine.allowed(d, Settings.load()))
        Settings.objects.update(answer_policy="standard")
        self.assertTrue(engine.allowed(d, Settings.load()))  # aniq holat — "faqat standart" rejimida ham yoziladi

    def test_screenshot_text_with_inn(self):
        d = engine.decide("", "ru", text="", ocr="ИНН 309035202 Создана в 1С Частично", live=True)
        self.assertEqual(d.stage, "prbc")
        self.assertIn("Частично", d.text)

    def test_kb_answer_kept_and_card_on_top(self):
        Entry.objects.create(title="Klient protargetda chiqmayapti", kind=Entry.TEMPLATE, status=Entry.APPROVED,
                             triggers=["protargetda chiqmayapti"], answer="Moderatsiyani kuting.")
        q = "309035202 klient protargetda chiqmayapti"
        d = engine.decide(q, "uz", text=q, live=True)
        self.assertEqual(d.stage, "template")
        self.assertTrue(d.text.startswith("📋 PRBC"))
        self.assertIn("Moderatsiyani kuting.", d.text)
        self.assertIn("1C da yaratildi", engine.vary(d, "uz", Settings.load()))

    def test_off_switches(self):
        q = "309035202 klient holati qanday"
        d = engine.decide(q, "uz", text=q)  # live=False (tarix, tahlil, testlar) — PRBC so'ralmaydi
        self.assertNotEqual(getattr(d, "stage", ""), "prbc")
        self.assertEqual(self.fake.calls, [])
        Connection.objects.update(outlet_lookup=False)
        d = engine.decide(q, "uz", text=q, live=True)
        self.assertNotEqual(getattr(d, "stage", ""), "prbc")
        self.assertEqual(self.fake.calls, [])

    def test_prbc_down_or_not_found_keeps_normal_flow(self):
        self.fake.fail = True
        q = "309035202 klient holati qanday"
        d = engine.decide(q, "uz", text=q, live=True)
        self.assertNotEqual(getattr(d, "stage", ""), "prbc")
        outlets._cache.clear()
        self.fake.fail, self.fake.rows = False, []
        d = engine.decide(q, "uz", text=q, live=True)
        self.assertNotEqual(getattr(d, "stage", ""), "prbc")

    def test_panel_check(self):
        api = APIClient()
        api.force_authenticate(User.objects.create_superuser("adm", "a@x.uz", "x"))
        r = api.get("/api/prbc/outlet-status/", {"q": "309035202"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("1C da yaratildi", r.json()["text"])
        self.assertIn("Создана в 1С", r.json()["text_ru"])
        self.assertEqual(api.get("/api/prbc/outlet-status/", {"q": "salom"}).status_code, 400)
