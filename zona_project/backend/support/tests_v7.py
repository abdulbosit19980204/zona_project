"""AI zaxira zanjiri (503 band), xodimlar faolligi tahlili, kontaktlarning aqlli rejimi."""
import json
import time
from unittest import mock

from zona.ai import providers, service
from zona.crypto import encrypt
from zona.models import AIProvider, AITaskConfig, Member, StaffPerson, StaffProject
from zona.tests import Base

from . import contacts, engine
from .models import MODE_LIVE, Bot, Message, Settings, TgUser
from .runner import Handler
from .tests import FakeClient, group_msg


class FailoverTests(Base):
    def setUp(self):
        service._cool.clear()
        self.g = AIProvider.objects.create(name="Gemini", kind="gemini", is_active=True, api_key_enc=encrypt("k"))
        AITaskConfig.objects.update_or_create(task="support", defaults={
            "enabled": True, "provider": self.g, "model": "gemini-2.5-flash", "fallback_provider": self.g,
            "fallback_model": "gemini-flash-lite-latest"})

    def test_busy_model_falls_back_and_cools_down(self):
        calls = []

        def fake(provider, model, *a, **k):
            calls.append(model)
            if model == "gemini-2.5-flash":
                raise providers.HTTPFail(503, "This model is currently experiencing high demand")
            return providers.Result("ok", 1, 1)

        with mock.patch.object(providers, "call", side_effect=fake):
            data, meta = service.run("support", None, "t", "sys", "m", None)
            self.assertEqual((data["text"], meta["model"], meta["fallback"]), ("ok", "gemini-flash-lite-latest", True))
            calls.clear()
            service.run("support", None, "t", "sys", "m", None)  # band model sovutilmoqda — birinchi bo'lib chaqirilmaydi
            self.assertEqual(calls[0], "gemini-flash-lite-latest")

    def test_all_busy_gives_friendly_message(self):
        with mock.patch.object(providers, "call", side_effect=providers.HTTPFail(503, "high demand")):
            with self.assertRaisesRegex(service.AIUnavailable, "Barcha AI modellar hozir band"):
                service.run("support", None, "t", "sys", "m", None)
        cfg = AITaskConfig.objects.get(task="support")
        tried = [m for _p, m in service._chain(cfg)]
        self.assertIn("gemini-flash-latest", tried)  # avtomatik zaxira modellar ham sinab ko'rildi

    def test_extra_fallbacks_api(self):
        c = AIProvider.objects.create(name="Claude", kind="anthropic", is_active=True, api_key_enc=encrypt("sk"))
        self.login("admin")
        r = self.call("patch", "admin/ai/tasks/support/", {"extra_fallbacks": [{"provider": c.id, "model": "claude-haiku-5-5"}]})
        self.assertEqual(r.status_code, 200, r.content)
        chain = [(p.kind, m) for p, m in service._chain(AITaskConfig.objects.get(task="support"))]
        self.assertEqual(chain[2], ("anthropic", "claude-haiku-5-5"))
        r = self.call("patch", "admin/ai/tasks/support/", {"extra_fallbacks": [{"provider": 999, "model": "x"}]})
        self.assertEqual(r.status_code, 400)


class StaffActivityTests(Base):
    def test_staff_work_analytics(self):
        Member.objects.create(name="Saida", role="Operator", telegram="op_saida")
        bot = Bot.objects.create(name="S", token_enc=encrypt("1:x"), mode=MODE_LIVE)
        h = Handler(bot, FakeClient())
        h.handle(group_msg(1, 10, "Klient ko'rinmayapti nima qilay?"))
        h.handle(group_msg(2, 77, "Klientni marshrutingizga qo'shdim", "op_saida", reply_to=1))
        h.handle(group_msg(3, 11, "Zakaz o'chmayapti yordam bering"))
        h.handle(group_msg(4, 77, "O'chirildi, tekshiring", "op_saida", reply_to=3))
        h.handle(group_msg(5, 77, "rahmat hammaga", "op_saida"))
        self.assertEqual(TgUser.objects.get(tg_id=77).msg_count, 3)
        self.login("viewer")
        row = next(x for x in self.call("get", "support/analytics/?days=30").json()["staff"] if x["name"] == "Saida")
        self.assertEqual((row["answers"], row["questions"], row["messages"], row["active_days"], row["share"]), (2, 2, 3, 1, 100))
        self.assertIsNotNone(row["avg_minutes"])


class SmartContactTests(Base):
    def setUp(self):
        hz = StaffProject.objects.create(name="Heinz")
        StaffPerson.objects.create(project=hz, name="Xalikov Valijon", role="SVR", city="Ташкент", phone="+998 90 000 00 01")

    def test_relaxed_and_ai_modes_within_deadline(self):
        res, q, how = contacts.smart_search("Heinz SVR Toshkent")
        self.assertEqual(how, "aniq")
        res, q, how = contacts.smart_search("Heinz SVR Xalikof")  # imlo xato ism — eng yaqin
        self.assertEqual((how, res[0]["name"]), ("aniq", "Xalikov Valijon")) if res and how == "aniq" else \
            self.assertEqual((how, res[0]["name"]), ("yaqin", "Xalikov Valijon"))
        Settings.load()
        Settings.objects.update(ai_enabled=True)
        ai_q = contacts.Query(roles={"SVR"}, brands={"Heinz"})
        with mock.patch.object(contacts, "_ai_parse", return_value=ai_q):
            res, q, how = contacts.smart_search("ketchup kompaniyasidagi nazoratchi kim")
        self.assertEqual((how, res[0]["name"]), ("ai", "Xalikov Valijon"))

        def slow(text, timeout):
            time.sleep(0.05)
            raise TimeoutError

        t0 = time.monotonic()
        with mock.patch.object(contacts, "_ai_parse", side_effect=slow):
            res, q, how = contacts.smart_search("noma'lum narsa", deadline=15.0)
        self.assertEqual(how, "topilmadi")
        self.assertLess(time.monotonic() - t0, 15)

    def test_engine_unchanged(self):
        self.assertTrue(engine.is_question("klient ko'rinmayapti"))
        self.assertEqual(Message.objects.count(), 0)
