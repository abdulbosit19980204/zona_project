import json
import re
from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase, override_settings
from openpyxl import load_workbook

from . import translation
from .ai import providers
from .crypto import decrypt
from .models import (AIProvider, AITaskConfig, AIUsage, Authority, Department, Event, Member, Process, ProcessRole,
                     Profile, Task)
from .search import search
from .search.normalize import fold, tokens

API = "/api/"
User = get_user_model()


def make_user(username, role, password="Parol-123456"):
    user = User.objects.create_user(username, password=password)
    Profile.objects.create(user=user, role=role)
    return user


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("zona_seed", verbosity=0)
        cls.admin = make_user("admin", Profile.ADMIN)
        cls.editor = make_user("editor", Profile.EDITOR)
        cls.viewer = make_user("viewer", Profile.VIEWER)

    def login(self, username):
        r = self.client.post(API + "auth/login/", {"username": username, "password": "Parol-123456"},
                             content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.token = r.json()["access"]
        self.refresh_token = r.json()["refresh"]
        return r.json()

    def call(self, method, url, data=None, lang=None):
        headers = {"Authorization": f"Bearer {self.token}"} if getattr(self, "token", None) else {}
        if lang:
            headers["X-Lang"] = lang
        return getattr(self.client, method)(API + url, data, content_type="application/json", headers=headers)


class AuthTests(Base):
    def test_anonymous_is_rejected(self):
        self.assertEqual(self.client.get(API + "state/").status_code, 401)

    @override_settings(ZONA={"PUBLIC_READ": True})
    def test_public_read(self):
        self.assertEqual(self.client.get(API + "state/").status_code, 200)
        self.assertEqual(self.client.post(API + "tasks/", {"title": "x"}, content_type="application/json").status_code, 401)

    def test_login_logout_and_bad_password(self):
        r = self.client.post(API + "auth/login/", {"username": "viewer", "password": "xato"}, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        me = self.login("viewer")
        self.assertEqual(me["user"]["role"], "viewer")
        self.assertEqual(self.call("get", "state/").status_code, 200)
        # refresh: yangi juftlik, eskisi bekor (rotatsiya)
        r = self.call("post", "auth/refresh/", {"refresh": self.refresh_token})
        self.assertEqual(r.status_code, 200)
        new_refresh = r.json()["refresh"]
        self.assertEqual(self.call("post", "auth/refresh/", {"refresh": self.refresh_token}).status_code, 401)
        # chiqish: shu refresh endi ishlamaydi
        self.call("post", "auth/logout/", {"refresh": new_refresh})
        self.assertEqual(self.call("post", "auth/refresh/", {"refresh": new_refresh}).status_code, 401)
        self.token = "buzilgan.token"
        self.assertEqual(self.call("get", "state/").status_code, 401)

    def test_viewer_cannot_edit(self):
        self.login("viewer")
        task = Task.objects.first()
        self.assertEqual(self.call("post", f"tasks/{task.id}/move/", {"owner": None}).status_code, 403)
        self.assertEqual(self.call("get", "admin/users/").status_code, 403)

    def test_editor_edits_but_no_admin(self):
        self.login("editor")
        task = Task.objects.first()
        self.assertEqual(self.call("post", f"tasks/{task.id}/move/", {"owner": None}).status_code, 200)
        self.assertEqual(Event.objects.first().actor, "editor")
        self.assertEqual(self.call("get", "admin/ai/providers/").status_code, 403)

    def test_own_profile_contacts(self):
        self.login("viewer")
        r = self.call("patch", "auth/me/", {"phone": "+998901234567", "telegram": "viewer_uz", "role": "admin"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["phone"], "+998901234567")
        self.assertEqual(r.json()["role"], "viewer")  # o'ziga rol bera olmaydi

    def test_change_password(self):
        self.login("viewer")
        r = self.call("post", "auth/password/", {"old_password": "Parol-123456", "new_password": "Yangi-Parol-987"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(User.objects.get(username="viewer").check_password("Yangi-Parol-987"))


class AdminTests(Base):
    def test_user_crud_with_contacts(self):
        self.login("admin")
        m = Member.objects.get(name="Jahongir")
        r = self.call("post", "admin/users/", {"username": "jahongir", "password": "Kuchli-Parol-77", "role": "editor",
                                              "member": m.id, "phone": "+998901112233", "telegram": "jahongir"})
        self.assertEqual(r.status_code, 201, r.content)
        uid = r.json()["id"]
        self.assertEqual(r.json()["member"], m.id)
        r = self.call("patch", f"admin/users/{uid}/", {"role": "viewer"})
        self.assertEqual(r.json()["role"], "viewer")
        self.assertEqual(self.call("delete", f"admin/users/{uid}/").status_code, 204)

    def test_cannot_remove_last_admin(self):
        self.login("admin")
        self.assertEqual(self.call("delete", f"admin/users/{self.admin.id}/").status_code, 400)
        r = self.call("patch", f"admin/users/{self.admin.id}/", {"role": "viewer"})
        self.assertEqual(r.status_code, 400)

    def test_provider_key_is_encrypted_and_masked(self):
        self.login("admin")
        r = self.call("post", "admin/ai/providers/", {"name": "Claude", "kind": "anthropic", "api_key": "sk-ant-test-123456789"})
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertNotIn("api_key", body)
        self.assertEqual(body["api_key_masked"], "••••6789")
        p = AIProvider.objects.get(pk=body["id"])
        self.assertNotIn("sk-ant", p.api_key_enc)
        self.assertEqual(decrypt(p.api_key_enc), "sk-ant-test-123456789")
        # bo'sh kalit eskisini o'chirmaydi
        self.call("patch", f"admin/ai/providers/{p.id}/", {"api_key": "", "name": "Claude asosiy"})
        p.refresh_from_db()
        self.assertEqual(decrypt(p.api_key_enc), "sk-ant-test-123456789")

    def test_task_config_requires_model(self):
        self.login("admin")
        tasks = self.call("get", "admin/ai/tasks/").json()
        self.assertEqual({t["task"] for t in tasks}, {"route", "person", "audit", "translate"})
        r = self.call("patch", "admin/ai/tasks/route/", {"enabled": True})
        self.assertEqual(r.status_code, 400)


class StructureTests(Base):
    def test_seed_counts(self):
        self.assertEqual(Department.objects.count(), 4)
        self.assertEqual(Member.objects.count(), 5)
        self.assertEqual(Process.objects.count(), 35)
        self.assertEqual(Task.objects.count(), 198)
        self.assertEqual(ProcessRole.objects.filter(role="owner").count(), 35)
        self.assertTrue(Authority.objects.exists())

    def test_state_has_everything(self):
        self.login("viewer")
        data = self.call("get", "state/").json()
        for key in ("departments", "members", "authorities", "processes", "roles", "tasks", "edge_cases"):
            self.assertTrue(data[key], key)
        self.assertEqual(data["me"]["username"], "viewer")
        self.assertEqual(set(data["meta"]["ai"]), {"route", "person", "audit", "translate"})

    def test_member_contacts_and_authority(self):
        self.login("editor")
        m = Member.objects.get(name="Xusniddin")
        r = self.call("patch", f"members/{m.id}/", {"phone": "+998 90 000 00 00", "telegram": "@xusniddin"})
        self.assertEqual(r.json()["telegram"], "xusniddin")
        r = self.call("post", "authorities/", {"member": m.id, "title": "VPN berish", "scope": "faqat xodimlarga"})
        self.assertEqual(r.status_code, 201)

    def test_bulk_move_and_roles(self):
        self.login("editor")
        ids = list(Task.objects.filter(owner__name="Saidabror").values_list("id", flat=True)[:3])
        target = Member.objects.get(name="Xusniddin")
        self.assertEqual(self.call("post", "tasks/bulk-move/", {"ids": ids, "owner": target.id}).json()["moved"], 3)
        p = Process.objects.first()
        self.assertEqual(self.call("post", "roles/", {"process": p.id, "member": target.id, "role": "backup"}).status_code, 201)
        self.assertEqual(self.call("post", "roles/", {"process": p.id, "member": target.id, "role": "backup"}).status_code, 400)

    def test_export_xlsx(self):
        self.login("viewer")
        r = self.call("get", "export.xlsx")
        self.assertEqual(r.status_code, 200)
        wb = load_workbook(BytesIO(r.content))
        self.assertEqual(wb.sheetnames, ["Xodimlar", "To'liq ro'yxat", "Matritsa", "Aralash holatlar"])

    def test_fallback_chain(self):
        # seed: avval Supervayzer, qila olmasa Saidabror
        t = Task.objects.get(title="Marshrutga nuqta qo'shish yoki olib tashlash")
        self.assertEqual(t.owner.name, "Supervayzerlar")
        self.assertEqual([f.member.name for f in t.fallbacks.all()], ["Saidabror"])
        self.login("editor")
        row = next(x for x in self.call("get", "state/").json()["tasks"] if x["id"] == t.id)
        self.assertEqual(row["fallbacks"][0]["member"], Member.objects.get(name="Saidabror").id)

        x, j = Member.objects.get(name="Xusniddin"), Member.objects.get(name="Jahongir")
        s = Member.objects.get(name="Saidabror")
        chain = [{"member": s.id, "condition": "  qila olmasa "}, {"member": x.id}]
        r = self.call("patch", f"tasks/{t.id}/", {"fallbacks": chain})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["fallbacks"], [{"member": s.id, "condition": "qila olmasa", "i18n": {}},
                                                 {"member": x.id, "condition": "", "i18n": {}}])
        # takror yoki asosiy mas'ul navbatda bo'lmaydi
        self.assertEqual(self.call("patch", f"tasks/{t.id}/", {"fallbacks": [{"member": x.id}, {"member": x.id}]}).status_code, 400)
        self.assertEqual(self.call("patch", f"tasks/{t.id}/", {"fallbacks": [{"member": t.owner_id}]}).status_code, 400)
        # navbatdagi xodim asosiy bo'lsa, navbatdan chiqadi
        self.call("post", f"tasks/{t.id}/move/", {"owner": s.id})
        self.assertEqual(list(t.fallbacks.values_list("member_id", flat=True)), [x.id])
        # qidiruv navbatdagini ham ko'rsatadi
        self.call("patch", f"tasks/{t.id}/", {"fallbacks": [{"member": j.id}]})
        people = {p["member"]: p for p in search("marshrutga nuqta qoshish")["people"]}
        self.assertIn("fallback", people[j.id]["via"])

    def test_process_executor_add_remove(self):
        self.login("editor")
        p = Process.objects.get(name="ProTarget: klient")
        n = p.tasks.count()
        s, sup = Member.objects.get(name="Saidabror"), Member.objects.get(name="Supervayzerlar")
        r = self.call("post", "tasks/process-executor/", {"process": p.id, "member": sup.id})
        self.assertEqual(r.json()["changed"], n)
        for task in p.tasks.all():
            self.assertEqual(task.owner, s)
            self.assertEqual(list(task.fallbacks.values_list("member_id", flat=True)), [sup.id])
        # takror qo'shish hech narsani o'zgartirmaydi
        self.assertEqual(self.call("post", "tasks/process-executor/", {"process": p.id, "member": sup.id}).json()["changed"], 0)
        # asosiyni olib tashlasa, navbatdagi asosiy bo'ladi
        self.call("post", "tasks/process-executor/", {"process": p.id, "member": s.id, "remove": True})
        for task in p.tasks.all():
            self.assertEqual(task.owner, sup)
            self.assertFalse(task.fallbacks.exists())
        self.login("viewer")
        self.assertEqual(self.call("post", "tasks/process-executor/", {"process": p.id, "member": s.id}).status_code, 403)

    def test_index_describes_api(self):
        data = self.client.get("/").json()
        self.assertEqual(data["api"], "/api/")
        self.assertEqual(data["websocket"], "/ws/events/")

    def test_teams(self):
        self.login("editor")
        data = self.call("get", "state/").json()
        self.assertEqual(len(data["teams"]), 5)
        it = Department.objects.get(name="IT xizmati")
        r = self.call("post", "teams/", {"department": it.id, "name": "Kiberxavfsizlik"})
        self.assertEqual(r.status_code, 201)
        m = Member.objects.get(name="Saidabror")
        # boshqa bo'lim jamoasiga qo'shib bo'lmaydi; bo'limni ham almashtirsa bo'ladi
        self.assertEqual(self.call("patch", f"members/{m.id}/", {"team": r.json()["id"]}).status_code, 400)
        r2 = self.call("patch", f"members/{m.id}/", {"team": r.json()["id"], "department": it.id})
        self.assertEqual(r2.json()["department"], it.id)


class ApprovalTests(Base):
    def test_viewer_proposes_editor_approves(self):
        task = Task.objects.filter(owner__name="Saidabror").first()
        target = Member.objects.get(name="Jahongir")
        self.login("viewer")
        r = self.call("post", "approvals/", {"kind": "task_owner", "payload": {"task": task.id, "owner": target.id},
                                             "reason": "Bu qurilma masalasi"})
        self.assertEqual(r.status_code, 201, r.content)
        rid = r.json()["id"]
        self.assertIn("Jahongir", r.json()["title"])
        self.assertEqual(self.call("post", f"approvals/{rid}/approve/", {}).status_code, 403)  # o'zi tasdiqlay olmaydi
        task.refresh_from_db()
        self.assertNotEqual(task.owner, target)
        self.login("editor")
        self.assertEqual(self.call("get", "state/").json()["meta"]["pending_approvals"], 1)
        r = self.call("post", f"approvals/{rid}/approve/", {"note": "To'g'ri"})
        self.assertEqual(r.json()["status"], "approved")
        task.refresh_from_db()
        self.assertEqual(task.owner, target)  # o'zgarish qo'llandi
        self.assertEqual(self.call("post", f"approvals/{rid}/reject/", {}).status_code, 400)  # qayta hal qilib bo'lmaydi

    def test_role_add_reject_and_cancel(self):
        p = Process.objects.first()
        m = Member.objects.get(name="Jahongir")
        self.login("viewer")
        rid = self.call("post", "approvals/", {"kind": "role_add", "payload": {"process": p.id, "member": m.id, "role": "backup"}}).json()["id"]
        self.assertEqual(self.call("post", "approvals/", {"kind": "role_add", "payload": {"process": p.id, "member": m.id, "role": "boss"}}).status_code, 400)
        rid2 = self.call("post", "approvals/", {"kind": "role_add", "payload": {"process": p.id, "member": m.id, "role": "supervisor"}}).json()["id"]
        self.assertEqual(self.call("post", f"approvals/{rid2}/cancel/", {}).json()["status"], "cancelled")
        self.login("editor")
        self.assertEqual(self.call("post", f"approvals/{rid}/reject/", {"note": "Kerak emas"}).json()["status"], "rejected")
        self.assertFalse(ProcessRole.objects.filter(process=p, member=m).exists())


class RealtimeTests(TransactionTestCase):
    """WebSocket boshqa oqimdan bazaga murojaat qiladi — shuning uchun tranzaksiyasiz test."""

    def test_websocket_requires_token_and_receives_events(self):
        from asgiref.sync import async_to_sync
        from channels.testing import WebsocketCommunicator
        from rest_framework_simplejwt.tokens import RefreshToken

        from config.asgi import application

        token = str(RefreshToken.for_user(make_user("viewer", Profile.VIEWER)).access_token)

        async def scenario():
            anon = WebsocketCommunicator(application, "/ws/events/", headers=[(b"origin", b"http://localhost")])
            connected, code = await anon.connect()
            assert not connected and code == 4401, (connected, code)
            ws = WebsocketCommunicator(application, f"/ws/events/?token={token}", headers=[(b"origin", b"http://localhost")])
            connected, _ = await ws.connect()
            assert connected
            hello = await ws.receive_json_from()
            assert hello["type"] == "hello" and hello["data"]["user"] == "viewer"
            await ws.send_json_to({"type": "ping"})
            assert (await ws.receive_json_from())["type"] == "pong"
            from channels.layers import get_channel_layer
            await get_channel_layer().group_send("zona", {"type": "zona.message", "payload": {"type": "event", "data": {"id": 1}}})
            assert (await ws.receive_json_from())["type"] == "event"
            await ws.disconnect()

        async_to_sync(scenario)()


class SearchTests(Base):
    CASES = [
        ("parolimni unutdim", "Xusniddin"),
        ("Пароль забыл не могу войти", "Xusniddin"),
        ("Паролимни унутдим", "Xusniddin"),
        ("telfon yoqoldi akkaunt", "Xusniddin"),
        ("принтер не печатает", "Jahongir"),
        ("интернет нет вайфай", "Jahongir"),
        ("klientga aksiya qoshib bering", "Saidabror"),
        ("клиенту добавить скидку", "Saidabror"),
        ("yangi aksiya yaratish kerak", "Dasturchilar jamoasi"),
    ]

    def test_normalize(self):
        self.assertEqual(fold("Ўзгартириш"), fold("o'zgartirish"))
        self.assertEqual(tokens("Пароль"), tokens("parol"))
        self.assertEqual(tokens("parolni"), tokens("parol"))

    def test_multilingual_routing(self):
        names = dict(Member.objects.values_list("id", "name"))
        for q, want in self.CASES:
            with self.subTest(q=q):
                people = search(q)["people"]
                self.assertTrue(people)
                self.assertEqual(names[people[0]["member"]], want)

    def test_search_endpoint(self):
        self.login("viewer")
        r = self.call("get", "search/?q=" + "принтер").json()
        self.assertTrue(r["tasks"][0]["hl"])


class AITests(Base):
    def setUp(self):
        self.provider = AIProvider.objects.create(name="Test", kind="openai", api_key_enc="")
        AITaskConfig.objects.update_or_create(task="route", defaults={"enabled": True, "provider": self.provider, "model": "m1"})

    def test_route_falls_back_to_search_when_ai_disabled(self):
        AITaskConfig.objects.filter(task="route").update(enabled=False)
        self.login("viewer")
        r = self.call("post", "ai/route/", {"question": "parolni tiklash kerak"}).json()
        self.assertEqual(r["source"], "search")
        self.assertTrue(r["ai_unavailable"])
        self.assertTrue(r["search"]["people"])

    def test_route_with_mocked_model(self):
        mid = Member.objects.get(name="Xusniddin").id
        tid = Task.objects.filter(owner_id=mid).first().id
        fake = providers.Result('{"language":"uz","summary":"Parol","candidates":[{"member_id":%d,"confidence":0.9,"role":"owner","reason":"Dostup"},{"member_id":99999,"confidence":0.5,"role":"x","reason":"yo\'q"}],"process_ids":[],"task_ids":[%d,99999],"answer":"Xusniddinga yozing","needs_clarification":false,"clarifying_question":""}' % (mid, tid), 1200, 80)
        with mock.patch.object(providers, "call", return_value=fake) as call:
            self.login("viewer")
            r = self.call("post", "ai/route/", {"question": "parolimni unutdim"}).json()
        self.assertEqual(r["source"], "ai")
        self.assertEqual([c["member"] for c in r["candidates"]], [mid])  # mavjud bo'lmagan id tashlanadi
        self.assertEqual(r["task_ids"], [tid])
        self.assertEqual(r["candidates"][0]["confidence"], 90)
        system = call.call_args.args[2]
        self.assertIn("TUZILMA", system)
        log = AIUsage.objects.first()
        self.assertEqual((log.ok, log.input_tokens, log.user), (True, 1200, "viewer"))

    def test_fallback_model_used_on_error(self):
        backup = AIProvider.objects.create(name="Zaxira", kind="openai")
        AITaskConfig.objects.filter(task="route").update(fallback_provider=backup, fallback_model="m2")
        ok = providers.Result('{"language":"uz","summary":"","candidates":[],"process_ids":[],"task_ids":[],"answer":"ok","needs_clarification":false,"clarifying_question":""}', 10, 5)
        with mock.patch.object(providers, "call", side_effect=[providers.AIError("limit"), ok]):
            self.login("viewer")
            r = self.call("post", "ai/route/", {"question": "parolimni unutdim"}).json()
        self.assertEqual(r["source"], "ai")
        self.assertTrue(r["meta"]["fallback"])
        self.assertEqual(AIUsage.objects.filter(ok=False).count(), 1)

    def test_parse_json(self):
        self.assertEqual(providers.parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(providers.parse_json('Javob: {"a": 2} tamom'), {"a": 2})
        with self.assertRaises(providers.AIError):
            providers.parse_json("json yo'q")


def fake_translator(provider, model, system, user, **kwargs):
    """Soxta AI: rus matnini "ru" deb aniqlaydi, boshqa tillarga prefiks qo'shib "tarjima qiladi"."""
    out = []
    for item in json.loads(user)["items"]:
        text = item["text"]
        ru = bool(re.search(r"[Ѐ-ӿ]", text))
        out.append({"id": item["id"], "source": "ru" if ru else "uz", "uz": f"UZ {text}" if ru else text,
                    "ru": text if ru else f"RU {text}", "en": f"EN {text}"})
    return providers.Result(json.dumps({"items": out}, ensure_ascii=False), 10, 10)


@override_settings(ZONA_TRANSLATE_ASYNC=False)
class TranslationTests(Base):
    def setUp(self):
        provider = AIProvider.objects.create(name="T", kind="openai")
        AITaskConfig.objects.update_or_create(task="translate", defaults={"enabled": True, "provider": provider, "model": "m"})

    def translate(self):
        with mock.patch.object(providers, "call", side_effect=fake_translator):
            return translation.translate_pending()

    def state_task(self, tid, lang=None):
        return next(t for t in self.call("get", "state/", lang=lang).json()["tasks"] if t["id"] == tid)

    def test_written_in_any_language_translated_to_all(self):
        self.login("editor")
        tid = self.call("post", "tasks/", {"title": "Новый клиент: добавить в маршрут"}, lang="uz").json()["id"]
        self.assertGreater(self.translate(), 0)
        i18n = self.state_task(tid)["i18n"]
        self.assertEqual(i18n["ru"]["title"], "Новый клиент: добавить в маршрут")  # asl matn o'z tilida o'zgarmaydi
        self.assertEqual(i18n["uz"]["title"], "UZ Новый клиент: добавить в маршрут")
        self.assertEqual(i18n["en"]["title"], "EN Новый клиент: добавить в маршрут")
        self.assertEqual(translation.status()["pending"], 0)
        # qidiruv tarjima bo'yicha ham topadi
        self.assertIn(tid, [t["id"] for t in search("Новый клиент маршрут")["tasks"]])

    def test_unchanged_localized_text_keeps_source(self):
        self.login("editor")
        task = Task.objects.filter(title__startswith="Klientni boshqa agentga").first()
        self.translate()
        # ingliz tilidagi interfeysda faqat izoh o'zgardi: sarlavha inglizcha qaytadi, lekin asl matn saqlanadi
        original = task.title
        r = self.call("patch", f"tasks/{task.id}/", {"title": f"EN {original}", "note": "Muhim"}, lang="en")
        self.assertEqual(r.status_code, 200, r.content)
        task.refresh_from_db()
        self.assertEqual(task.title, original)
        self.assertEqual(translation.pending_fields(task), ["note"])
        self.assertEqual(r.json()["i18n"]["en"]["title"], f"EN {original}")
        # sarlavha haqiqatan o'zgarsa: yangi asl matn, eski tarjimalar ko'rsatilmaydi
        self.call("patch", f"tasks/{task.id}/", {"title": "Перевести клиента"}, lang="ru")
        task.refresh_from_db()
        self.assertEqual(task.title, "Перевести клиента")
        self.assertNotIn("title", self.state_task(task.id)["i18n"].get("en", {}))
        self.translate()
        self.assertEqual(self.state_task(task.id)["i18n"]["uz"]["title"], "UZ Перевести клиента")

    def test_fallback_condition_translation_survives_resave(self):
        self.login("editor")
        task = Task.objects.filter(fallbacks__condition__gt="").first()
        fb = task.fallbacks.first()
        self.translate()
        ru = self.state_task(task.id)["fallbacks"][0]["i18n"]["ru"]["condition"]
        r = self.call("patch", f"tasks/{task.id}/", {"fallbacks": [{"member": fb.member_id, "condition": ru}]}, lang="ru")
        self.assertEqual(r.status_code, 200, r.content)
        new = task.fallbacks.get()
        self.assertEqual(new.condition, fb.condition)
        self.assertEqual(translation.pending_fields(new), [])

    def test_ai_error_keeps_text_and_reports(self):
        self.login("editor")
        tid = self.call("post", "tasks/", {"title": "Yangi vazifa"}).json()["id"]
        with mock.patch.object(providers, "call", side_effect=providers.AIError("limit")):
            self.assertEqual(translation.translate_pending(), 0)
        self.assertEqual(self.state_task(tid)["title"], "Yangi vazifa")
        self.login("admin")
        st = self.call("get", "admin/ai/translate/").json()
        self.assertTrue(st["enabled"])
        self.assertGreater(st["pending"], 0)
        self.assertIn("limit", st["last_error"])
        self.login("editor")
        self.assertEqual(self.call("get", "admin/ai/translate/").status_code, 403)


ARTIFACT_HTML = """<title>Структура команды Testbrand</title><script>
const ROP={"name": "Bilalov Zamir", "phone": ""};
const DATA={"branches": [{"id": "tashkent", "title": "Ташкент", "teams": [{"head": {"n": 1, "name": "Xalikov Valijon", "terr": "SVR Tash 1", "role": "SVR", "city": "Ташкент", "phone": "998777299944", "svr": true},
 "members": [{"n": 2, "name": "Rashidova Shahnoza", "terr": "SR1 Tashkent", "role": "TP", "city": "Ташкент", "phone": "+998 90 641 27 97"},
             {"n": 3, "name": "Вакансия", "terr": "SR4 Tashkent", "role": "VAC", "city": "Ташкент", "phone": ""}]}], "direct": []},
 {"id": "spec", "title": "Спецканалы", "teams": [], "direct": [{"n": 4, "name": "Galimov Timur", "terr": "MR Tashkent H1", "role": "MER", "city": "", "phone": "+998 99 051 71 39"}]}]};
</script>"""


class StaffTests(Base):
    def imp(self, apply=False, **body):
        return self.call("post", "staff/import/", {**body, "apply": apply})

    def test_import_preview_apply_and_reimport(self):
        from .models import StaffPerson, StaffProject
        self.login("editor")
        prev = self.imp(text=ARTIFACT_HTML).json()["projects"][0]
        self.assertEqual(prev["project"]["name"], "Testbrand")
        self.assertFalse(prev["project"]["exists"])
        self.assertEqual(prev["summary"]["added"], 5)
        self.assertFalse(StaffProject.objects.exists())  # preview bazaga yozmaydi
        r = self.imp(apply=True, text=ARTIFACT_HTML)
        self.assertEqual(r.status_code, 200, r.content)
        project = StaffProject.objects.get(name="Testbrand")
        svr = StaffPerson.objects.get(territory="SVR Tash 1")
        self.assertEqual(svr.phone, "+998 77 729 99 44")
        self.assertEqual(svr.manager.role, "ROP")
        self.assertEqual(StaffPerson.objects.get(territory="SR1 Tashkent").manager, svr)
        self.assertTrue(StaffPerson.objects.get(territory="SR4 Tashkent").is_vacancy)
        # qayta import: vakansiyaga odam keldi, bir xodim almashdi, merchendayzer ketdi
        html = (ARTIFACT_HTML.replace('"Вакансия", "terr": "SR4', '"Yangi Odam", "terr": "SR4').replace('"role": "VAC"', '"role": "TP"')
                .replace("Rashidova Shahnoza", "Boshqa Xodim")
                .replace(', "direct": [{"n": 4, "name": "Galimov Timur", "terr": "MR Tashkent H1", "role": "MER", "city": "", "phone": "+998 99 051 71 39"}]', ', "direct": []'))
        d = self.imp(text=html).json()["projects"][0]
        self.assertTrue(d["project"]["exists"])
        self.assertEqual((d["summary"]["replaced"], d["summary"]["removed"], d["summary"]["added"]), (2, 1, 0))
        self.assertEqual({(x["from"], x["to"]) for x in d["replaced"]}, {("Rashidova Shahnoza", "Boshqa Xodim"), ("", "Yangi Odam")})
        sr1_id = StaffPerson.objects.get(territory="SR1 Tashkent").id
        self.imp(apply=True, text=html)
        sr1 = StaffPerson.objects.get(territory="SR1 Tashkent")
        self.assertEqual((sr1.id, sr1.name), (sr1_id, "Boshqa Xodim"))  # o'rin saqlanadi, odam almashadi
        self.assertFalse(StaffPerson.objects.filter(territory="MR Tashkent H1").exists())
        self.assertEqual(project.people.count(), 4)
        self.login("viewer")
        self.assertEqual(self.imp(apply=True, text=html).status_code, 403)
        self.assertEqual(len(self.call("get", "staff/").json()["people"]), 4)

    def test_copied_page_text_import(self):
        """Claude artifact sahifasidan Ctrl+A/Ctrl+C qilingan matn — link manba sifatida saqlanadi."""
        from .models import StaffPerson, StaffProject
        self.login("editor")
        text = chr(10).join([
            "Структура полевой команды Textbrand", "12 позиций", "РОП", "1",
            "РУКОВОДИТЕЛЬ ОТДЕЛА ПРОДАЖ", "Bosh Rahbar Aliyevich", "Textbrand · Узбекистан",
            "Ташкент", "3 чел.",
            "Guruh Boshliq Karimovich", "СВР", "SVR Tash 1 · Ташкент · +998 77 729 99 44",
            "ТП", "Birinchi Xodim Valiyevna", "SR1 Tashkent", "Ташкент", "+998 90 641 27 97",
            "Вакансия", "Вакансия", "SR4 Tashkent", "Ташкент", "нет телефона",
            "Юг", "RSM Mintaqa Rahbari · Самарканд · +998 90 983 51 03",
            "СВР — вакансия", "Вакансия", "SVR SW 1 · Самарканд",
            "ТП", "Ikkinchi (Eski) Xodim ●", "SR Samarkand 1", "Самарканд", "998901112233",
        ])
        url = "https://claude.ai/artifact/AbCdEf123"
        r = self.imp(url=url)
        self.assertEqual(r.status_code, 400)
        self.assertIn("Ctrl+A", r.json()["detail"])
        r = self.imp(apply=True, url=url, text=text)
        self.assertEqual(r.status_code, 200, r.content)
        project = StaffProject.objects.get(name="Textbrand")
        self.assertEqual(project.source_url, url)
        self.assertEqual(project.people.count(), 7)
        head = StaffPerson.objects.get(territory="SVR Tash 1")
        self.assertEqual((head.role, head.manager.name, head.unit.title), ("SVR", "Bosh Rahbar Aliyevich", "Ташкент"))
        sr1 = StaffPerson.objects.get(territory="SR1 Tashkent")
        self.assertEqual((sr1.manager, sr1.phone), (head, "+998 90 641 27 97"))
        self.assertTrue(StaffPerson.objects.get(territory="SR4 Tashkent").is_vacancy)
        rsm = StaffPerson.objects.get(name="Mintaqa Rahbari")
        self.assertEqual((rsm.role, rsm.unit.title), ("RSM", "Юг"))
        sw1 = StaffPerson.objects.get(territory="SVR SW 1")
        self.assertTrue(sw1.is_vacancy)
        self.assertEqual(sw1.manager, rsm)
        last = StaffPerson.objects.get(territory="SR Samarkand 1")
        self.assertEqual((last.name, last.manager, last.phone), ("Ikkinchi (Eski) Xodim", sw1, "+998 90 111 22 33"))
        # manbadan yangilash ham nusxa olingan matn bilan ishlaydi
        r = self.call("post", f"staff/projects/{project.id}/sync/", {"text": text.replace("Birinchi Xodim Valiyevna", "Yangi Odam Testov")})
        self.assertEqual(r.json()["projects"][0]["summary"]["replaced"], 1)

    def test_vacate_assign_and_seat_history(self):
        from .models import StaffPerson
        self.login("editor")
        self.imp(apply=True, text=ARTIFACT_HTML)
        sr1 = StaffPerson.objects.get(territory="SR1 Tashkent")
        boss, reports = sr1.manager_id, list(sr1.reports.values_list("id", flat=True))
        r = self.call("post", f"staff/people/{sr1.id}/vacate/", {"reason": "O'z xohishi bilan", "date": "2026-11-01"})
        self.assertEqual(r.status_code, 200, r.content)
        sr1.refresh_from_db()
        self.assertTrue(sr1.is_vacancy)
        self.assertEqual((sr1.name, sr1.phone, sr1.manager_id), ("", "", boss))  # o'rin va rahbar saqlanadi
        self.assertEqual(list(sr1.reports.values_list("id", flat=True)), reports)
        self.assertEqual(sr1.history[0]["name"], "Rashidova Shahnoza")
        self.assertEqual((sr1.history[0]["until"], sr1.history[0]["reason"]), ("2026-11-01", "O'z xohishi bilan"))
        self.assertEqual(self.call("post", f"staff/people/{sr1.id}/vacate/", {}).status_code, 400)
        # tayinlash: telefon va telegram normallashadi
        r = self.call("post", f"staff/people/{sr1.id}/assign/", {"name": "Yangi Xodim", "phone": "901234567", "telegram": "https://t.me/yangi_xodim"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["phone"], r.json()["telegram"], r.json()["is_vacancy"]), ("+998 90 123 45 67", "yangi_xodim", False))
        self.assertTrue(r.json()["since"])
        # almashtirish: avvalgisi tarixga
        r = self.call("post", f"staff/people/{sr1.id}/assign/", {"name": "Uchinchi Xodim", "telegram": "@uchinchi"})
        self.assertEqual([h["name"] for h in r.json()["history"]], ["Yangi Xodim", "Rashidova Shahnoza"])
        self.assertEqual(r.json()["telegram"], "uchinchi")
        self.assertEqual(self.call("post", f"staff/people/{sr1.id}/assign/", {"name": " "}).status_code, 400)
        # oddiy tahrirda ism almashsa ham tarixga yoziladi
        self.call("patch", f"staff/people/{sr1.id}/", {"name": "Tahrir Odam"})
        sr1.refresh_from_db()
        self.assertEqual(sr1.history[0]["name"], "Uchinchi Xodim")
        self.login("viewer")
        self.assertEqual(self.call("post", f"staff/people/{sr1.id}/vacate/", {}).status_code, 403)

    def test_excel_roundtrip_and_json_export(self):
        import base64
        from .models import StaffPerson
        self.login("editor")
        self.imp(apply=True, text=ARTIFACT_HTML)
        xlsx = self.call("get", "staff/export.xlsx").content
        wb = load_workbook(BytesIO(xlsx))
        ws = wb["Xodimlar"]
        header = [c.value for c in ws[1]]
        # Excel'da odamni almashtiramiz va yangi qator qo'shamiz
        for row in ws.iter_rows(min_row=2):
            if row[header.index("Hudud kodi")].value == "SR1 Tashkent":
                row[header.index("F.I.Sh.")].value = "Excel Odam"
                row[header.index("Telefon")].value = 901112233
        svr_no = next(r[0].value for r in ws.iter_rows(min_row=2) if r[header.index("Hudud kodi")].value == "SVR Tash 1")
        ws.append([99, "Testbrand", "Ташкент", "TP", "", "Qo'shilgan Odam", "SR9 Tashkent", "", "", "", "t.me/qoshilgan_odam", "", svr_no, "", "", ""])
        buf = BytesIO()
        wb.save(buf)
        body = {"file_b64": base64.b64encode(buf.getvalue()).decode(), "filename": "t.xlsx"}
        d = self.imp(**body).json()["projects"][0]
        self.assertEqual((d["summary"]["added"], d["summary"]["replaced"], d["summary"]["removed"]), (1, 1, 0))
        self.imp(apply=True, **body)
        new = StaffPerson.objects.get(territory="SR9 Tashkent")
        self.assertEqual(new.telegram, "qoshilgan_odam")
        self.assertEqual(StaffPerson.objects.get(territory="SR1 Tashkent").history[0]["reason"], "import")
        self.assertEqual(new.manager.territory, "SVR Tash 1")
        self.assertEqual(StaffPerson.objects.get(territory="SR1 Tashkent").phone, "+998 90 111 22 33")
        doc = self.call("get", "staff/export.json").json()
        self.assertEqual(doc["format"], "zona-staff")
        self.assertEqual(len(doc["people"]), 6)

    def test_bad_sources(self):
        self.login("editor")
        r = self.imp(url="https://claude.ai/artifact/abc")
        self.assertEqual(r.status_code, 400)
        self.assertIn("brauzerda", r.json()["detail"])
        self.assertEqual(self.imp(text="<html>bo'sh</html>").status_code, 400)
        self.assertEqual(self.imp(url="ftp://x").status_code, 400)


class KnowledgeTests(Base):
    """Savollar bazasi: zonalar, qoidalar, bot API va AI uchun eksport."""

    def setUp(self):
        from . import knowledge_seed
        self.stats = knowledge_seed.apply(log=lambda *_: None)

    def test_restructure_sets_zones_rules_and_chain(self):
        from .models import Process, Task, Zone
        self.assertEqual(Zone.objects.count(), 7)
        self.assertFalse(Process.objects.filter(zone__isnull=True).exists())
        t = Task.objects.get(title="Klient bazada bor, lekin agentda ko'rinmayapti")
        self.assertTrue(t.frequent)
        self.assertIn("marshrut", t.rule)
        self.assertIn("klient agentda ko'rinmayapti", t.examples)
        chain = list(t.fallbacks.order_by("order").values_list("member__name", "condition"))
        self.assertEqual(chain[0][0], "Saidabror")
        self.assertIn("topilmasa", chain[0][1])
        self.assertFalse(Task.objects.filter(asker="").exclude(process__isnull=True).exists())
        # qayta ishga tushirish xavfsiz
        from . import knowledge_seed
        again = knowledge_seed.apply(log=lambda *_: None)
        self.assertEqual(again["questions"], self.stats["questions"])
        self.assertFalse(Process.objects.filter(zone__isnull=True).exists())
        self.assertEqual(Zone.objects.count(), 7)

    def test_state_and_task_fields(self):
        self.login("editor")
        state = self.call("get", "state/").json()
        self.assertEqual(len(state["zones"]), 7)
        self.assertTrue(all(p["zone"] for p in state["processes"]))
        task = next(t for t in state["tasks"] if t["frequent"])
        self.assertIn("rule", task)
        r = self.call("patch", f"tasks/{task['id']}/", {"examples": ["  birinchi  ", "birinchi", "", "ikkinchi"]})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["examples"], ["birinchi", "ikkinchi"])
        self.assertEqual(self.call("patch", f"tasks/{task['id']}/", {"examples": "matn"}).status_code, 400)

    def test_bot_ask_with_key_and_without(self):
        from django.test import override_settings
        r = self.client.post(API + "bot/ask/", {"question": "klient bazada bor lekin agentda ko'rinmayapti"},
                             content_type="application/json")
        self.assertIn(r.status_code, (401, 403))
        with override_settings(ZONA={"COMPANY_NAME": "StarGroup", "BOT_API_KEY": "bot-secret"}):
            r = self.client.post(API + "bot/ask/", {"question": "klientim agentda ko'rinmayapti, bazada bor"},
                                 content_type="application/json", headers={"X-Bot-Key": "bot-secret"})
            self.assertEqual(r.status_code, 200, r.content)
            d = r.json()
            self.assertTrue(d["found"], d)
            self.assertEqual(d["best"]["question"], "Klient bazada bor, lekin agentda ko'rinmayapti")
            self.assertEqual(d["best"]["responsible"]["name"], "Supervayzerlar")
            self.assertIn("Qoida:", d["answer_text"])
            self.assertEqual(self.client.post(API + "bot/ask/", {"question": "x"}, content_type="application/json",
                                              headers={"X-Bot-Key": "bot-secret"}).status_code, 400)
            wrong = self.client.post(API + "bot/ask/", {"question": "parol"}, content_type="application/json",
                                     headers={"X-Bot-Key": "notogri"})
            self.assertIn(wrong.status_code, (401, 403))
        self.login("viewer")
        self.assertEqual(self.call("post", "bot/ask/", {"question": "parolni unutdim"}).status_code, 200)

    def test_knowledge_export_formats(self):
        import json as _json
        self.login("viewer")
        full = _json.loads(self.call("get", "knowledge/export.json").content)
        self.assertEqual(len(full["zones"]), 7)
        self.assertTrue(any(i["rule"] for i in full["items"]))
        lines = self.call("get", "knowledge/export.jsonl?frequent=1").content.decode().strip().split("\n")
        self.assertTrue(all(_json.loads(ln)["frequent"] for ln in lines))
        chat = [_json.loads(ln) for ln in self.call("get", "knowledge/export.chat?frequent=1").content.decode().strip().split("\n")]
        self.assertEqual([m["role"] for m in chat[0]["messages"]], ["system", "user", "assistant"])
        self.assertGreater(len(chat), len(lines))  # har bir misol alohida juftlik
        md = self.call("get", "knowledge/export.md").content.decode()
        self.assertIn("## Distributsiya", md)
        self.assertEqual(self.call("get", "knowledge/export.pdf").status_code, 400)
