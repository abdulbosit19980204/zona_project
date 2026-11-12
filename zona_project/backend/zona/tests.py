from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase, override_settings
from openpyxl import load_workbook

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

    def call(self, method, url, data=None):
        headers = {"Authorization": f"Bearer {self.token}"} if getattr(self, "token", None) else {}
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
        self.assertEqual({t["task"] for t in tasks}, {"route", "person", "audit"})
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
        self.assertEqual(set(data["meta"]["ai"]), {"route", "person", "audit"})

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
        self.assertEqual(r.json()["fallbacks"], [{"member": s.id, "condition": "qila olmasa"},
                                                 {"member": x.id, "condition": ""}])
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
