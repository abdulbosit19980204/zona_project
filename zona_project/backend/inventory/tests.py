import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from openpyxl import load_workbook
from PIL import Image
from rest_framework.test import APIClient

from zona.auth import issue_tokens
from zona.models import Profile

from .models import Access, Branch, DeviceType, Employee, Item, Log, Org
from .views import create_access_user

User = get_user_model()
TMP = tempfile.mkdtemp(prefix="inv-test-")


def client_for(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(user)['access']}")
    return c


def jpeg(color=(200, 30, 30), size=(2400, 1800)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    buf.seek(0)
    buf.name = "foto.jpg"
    return buf


@override_settings()
class InvBase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import os
        os.environ["ZONA_INVENTORY_MEDIA"] = TMP

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        # katalog 0002 migratsiyasi bilan to'lgan
        self.sam = Branch.objects.get(code="SAM")
        self.bux = Branch.objects.get(code="BUX")
        self.laptop = DeviceType.objects.get(name="Noutbuk")
        self.org = Org.objects.get(name="Star Distribution")
        self.admin = User.objects.create_superuser("boss", password="x")
        self.acc, self.pw = create_access_user("inv.sam", "Samarqand", "filiali", Access.COLLECTOR, [self.sam.id])
        self.collector = self.acc.user
        self.api = client_for(self.admin)
        self.col = client_for(self.collector)

    def add_item(self, client=None, **extra):
        data = {"branch": self.sam.id, "device_type": self.laptop.id, "org": self.org.id, "brand": "Lenovo",
                "model": "ThinkPad E14", "serial": "PF4ABC12", "condition": "ok", **extra}
        r = (client or self.col).post("/api/inventory/items/", data, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()



class InventoryTests(InvBase):
    # ------------------------------------------------------------ huquqlar
    def test_catalog_seeded_from_template(self):
        self.assertEqual(Branch.objects.count(), 12)
        self.assertEqual(DeviceType.objects.count(), 30)
        self.assertIn("Lenovo", self.laptop.brands)

    def test_collector_is_isolated_from_rest_of_platform(self):
        self.assertEqual(self.collector.zona_profile.role, Profile.INVENTORY)
        for url in ("/api/state/", "/api/support/stats/", "/api/admin/users/"):
            self.assertIn(self.col.get(url).status_code, (401, 403), url)
        me = self.col.get("/api/auth/me/").json()
        self.assertEqual(me["role"], "inventory")
        self.assertEqual(me["inventory"], "collector")

    def test_user_without_access_cannot_open_module(self):
        viewer = User.objects.create_user("viewer", password="x")
        self.assertEqual(client_for(viewer).get("/api/inventory/bootstrap/").status_code, 403)

    def test_collector_sees_only_own_branch(self):
        self.add_item()
        self.add_item(client=self.api, branch=self.bux.id, serial="BUX-1")
        boot = self.col.get("/api/inventory/bootstrap/").json()
        self.assertEqual([b["code"] for b in boot["branches"]], ["SAM"])
        self.assertEqual(self.col.get("/api/inventory/items/").json()["count"], 1)
        self.assertEqual(self.api.get("/api/inventory/items/").json()["count"], 2)
        r = self.col.post("/api/inventory/items/", {"branch": self.bux.id, "device_type": self.laptop.id}, format="json")
        self.assertEqual(r.status_code, 400)
        bux_item = Item.objects.get(branch=self.bux)
        self.assertEqual(self.col.get(f"/api/inventory/items/{bux_item.id}/").status_code, 404)

    def test_director_reads_all_but_cannot_write(self):
        acc, _ = create_access_user("rahbar", level=Access.DIRECTOR)
        d = client_for(acc.user)
        self.add_item()
        self.assertEqual(d.get("/api/inventory/items/").json()["count"], 1)
        self.assertEqual(d.get("/api/inventory/stats/").status_code, 200)
        r = d.post("/api/inventory/items/", {"branch": self.sam.id, "device_type": self.laptop.id}, format="json")
        self.assertEqual(r.status_code, 403)

    # ------------------------------------------------------------ qurilmalar
    def test_create_assigns_inventory_number_and_logs(self):
        a = self.add_item()
        b = self.add_item(serial="PF4ABC12")
        self.assertEqual(a["inv_number"], "SAM-00001")
        self.assertEqual(b["inv_number"], "SAM-00002")
        self.assertEqual(b["duplicate"]["inv_number"], "SAM-00001")  # bir xil seriya ogohlantiriladi
        self.sam.refresh_from_db()
        self.assertEqual(self.sam.status, Branch.ACTIVE)
        self.assertTrue(Log.objects.filter(action=Log.CREATE, item_id=a["id"]).exists())

    def test_update_delete_restore_history(self):
        a = self.add_item()
        r = self.col.patch(f"/api/inventory/items/{a['id']}/", {"condition": "repair", "quantity": 2}, format="json")
        self.assertEqual(r.json()["condition_label"], "Ta'mirga muhtoj")
        upd = Log.objects.get(action=Log.UPDATE, item_id=a["id"])
        self.assertEqual(upd.changes["condition"], ["Ishlayapti", "Ta'mirga muhtoj"])
        self.assertEqual(self.col.delete(f"/api/inventory/items/{a['id']}/").status_code, 204)
        self.assertEqual(self.col.get("/api/inventory/items/").json()["count"], 0)
        self.assertEqual(self.col.post(f"/api/inventory/items/{a['id']}/restore/").status_code, 200)
        self.assertEqual(self.col.get("/api/inventory/items/").json()["count"], 1)

    def test_photo_upload_compress_and_signed_url(self):
        r = self.col.post("/api/inventory/photos/", {"files": [jpeg(), jpeg((0, 0, 255))]}, format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        photos = r.json()
        self.assertEqual(len(photos), 2)
        self.assertLessEqual(max(photos[0]["width"], photos[0]["height"]), 1600)
        item = self.add_item(photos=[p["id"] for p in photos])
        self.assertEqual(len(item["photos"]), 2)
        anon = APIClient()
        self.assertEqual(anon.get(photos[0]["thumb"]).status_code, 200)
        self.assertEqual(anon.get(f"/api/inventory/photos/{photos[0]['id']}/file/?k=bad").status_code, 404)
        # bittasini olib tashlash
        r = self.col.patch(f"/api/inventory/items/{item['id']}/", {"photos": [photos[1]["id"]]}, format="json")
        self.assertEqual(len(r.json()["photos"]), 1)

    def test_not_an_image_rejected(self):
        bad = io.BytesIO(b"hello")
        bad.name = "x.jpg"
        self.assertEqual(self.col.post("/api/inventory/photos/", {"files": [bad]}, format="multipart").status_code, 400)

    # ------------------------------------------------------------ xodimlar
    def test_employee_crud_scope(self):
        r = self.col.post("/api/inventory/employees/", {"full_name": "Karimov Aziz", "branch": self.sam.id,
                                                         "org": self.org.id, "project": "Heinz"}, format="json")
        self.assertEqual(r.status_code, 201)
        emp = r.json()
        r = self.col.post("/api/inventory/employees/", {"full_name": "Boshqa", "branch": self.bux.id}, format="json")
        self.assertEqual(r.status_code, 400)
        self.add_item(employee=emp["id"])
        lst = self.col.get("/api/inventory/employees/?project=Heinz").json()
        self.assertEqual(lst["results"][0]["devices"], 1)
        self.assertEqual(lst["projects"], ["Heinz"])
        r = self.col.delete(f"/api/inventory/employees/{emp['id']}/")
        self.assertTrue(r.json()["deactivated"])  # qurilmasi bor — o'chmaydi, nofaol bo'ladi

    def test_employees_template_roundtrip(self):
        r = self.api.get("/api/inventory/employees/template/")
        wb = load_workbook(io.BytesIO(r.content))
        ws = wb["Xodimlar"]
        ws.append(["Toshmatov Ali", "Kassir", "+998901112233", "@toshmatov_ali", "STAR FMCG", "Buxoro", "BIC", "Savdo", ""])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "x.xlsx"
        r = self.api.post("/api/inventory/employees/import/", {"file": buf}, format="multipart")
        self.assertEqual(r.json()["employees_created"], 1, r.json())
        e = Employee.objects.get(full_name="Toshmatov Ali")
        self.assertEqual((e.branch.code, e.org.name, e.project), ("BUX", "STAR FMCG", "BIC"))
        self.assertEqual((e.phone, e.telegram), ("+998 90 111 22 33", "toshmatov_ali"))

    # ------------------------------------------------------------ eksport / import
    def test_exports(self):
        self.add_item(note="Zaryadlovchisi bor")
        csv_r = self.api.get("/api/inventory/items/export/?fmt=csv")
        self.assertIn("SAM-00001", csv_r.content.decode("utf-8-sig"))
        x = load_workbook(io.BytesIO(self.api.get("/api/inventory/items/export/?fmt=xlsx").content))
        self.assertEqual(x.sheetnames, ["Qurilmalar", "Filiallar holati", "Xodimlar"])
        t = load_workbook(io.BytesIO(self.api.get("/api/inventory/items/export/?fmt=template").content))
        inv = t["Inventarizatsiya"]
        self.assertEqual(inv["E5"].value, "Noutbuk")
        self.assertEqual(inv["C5"].value, "Samarqand")
        self.assertTrue(str(inv["F5"].value).startswith("=IF("))  # formulalar saqlangan
        self.assertTrue(len(inv.data_validations.dataValidation) >= 7)  # ochiluvchi ro'yxatlar qayta qo'shilgan
        self.assertEqual(t["Filiallar"]["G13"].value, "Jarayonda")  # SAM — 9-filial, 13-qator
        rep = load_workbook(io.BytesIO(self.api.get("/api/inventory/stats/export/").content))
        self.assertIn("Filiallar holati", rep.sheetnames)

    def test_template_import_roundtrip_updates_not_duplicates(self):
        self.add_item()
        content = self.api.get("/api/inventory/items/export/?fmt=template").content
        wb = load_workbook(io.BytesIO(content))
        inv = wb["Inventarizatsiya"]
        inv["K5"] = "Ishlamaydi"
        for c, v in zip("BCDEGHIJKLO", ["STAR FMCG", "Buxoro", "Ombor", "Printer", "HP", "LaserJet 1020", "CN123",
                                         2, "Ishlayapti", "Yangi Xodim", "kartrij 12A"]):
            inv[f"{c}6"] = v
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "t.xlsx"
        dry = self.api.post("/api/inventory/items/import/", {"file": buf, "dry_run": "1"}, format="multipart").json()
        self.assertEqual((dry["created"], dry["updated"]), (1, 1), dry)
        self.assertEqual(Item.objects.count(), 1)  # dry run hech narsa saqlamaydi
        buf.seek(0)
        res = self.api.post("/api/inventory/items/import/", {"file": buf}, format="multipart").json()
        self.assertEqual((res["created"], res["updated"], res["errors"]), (1, 1, []), res)
        self.assertEqual(Item.objects.get(inv_number="SAM-00001").condition, "broken")
        printer = Item.objects.get(branch=self.bux)
        self.assertEqual((printer.quantity, printer.employee.full_name, printer.inv_number), (2, "Yangi Xodim", "BUX-00001"))

    def test_collector_import_cannot_touch_other_branch(self):
        buf = io.BytesIO("Qurilma turi;Filial;Brend\nNoutbuk;Buxoro;HP\nNoutbuk;;Dell\n".encode("utf-8"))
        buf.name = "x.csv"
        res = self.col.post("/api/inventory/items/import/", {"file": buf}, format="multipart").json()
        self.assertEqual(res["created"], 1)  # bo'sh filial — o'z filiali (Samarqand)
        self.assertEqual(len(res["errors"]), 1)
        self.assertEqual(Item.objects.get().branch, self.sam)

    # ------------------------------------------------------------ foydalanuvchilar, statistika
    def test_generate_branch_logins_and_credentials_file(self):
        r = self.api.post("/api/inventory/users/generate/", {}, format="json").json()
        self.assertEqual(len(r["created"]), 11)  # SAM uchun allaqachon bor
        u = User.objects.get(username="inv.bux")
        self.assertTrue(u.check_password(next(x["password"] for x in r["created"] if x["username"] == "inv.bux")))
        self.assertEqual(self.col.post("/api/inventory/users/generate/", {}, format="json").status_code, 403)
        wb = load_workbook(io.BytesIO(self.api.get("/api/inventory/users/credentials/").content))
        rows = list(wb["Loginlar"].iter_rows(min_row=5, values_only=True))
        self.assertEqual(len(rows), 12)
        sam = next(r for r in rows if r[1] == "inv.sam")
        self.assertEqual(sam[2], self.pw)

    def test_stats(self):
        self.add_item()
        self.add_item(condition="broken", serial="")
        s = self.api.get("/api/inventory/stats/").json()
        self.assertEqual(s["totals"]["rows"], 2)
        self.assertEqual(s["totals"]["broken"], 1)
        sam = next(b for b in s["branches"] if b["code"] == "SAM")
        self.assertEqual((sam["rows"], sam["flag"], sam["no_serial"]), (2, "active", 1))
        bux = next(b for b in s["branches"] if b["code"] == "BUX")
        self.assertEqual(bux["flag"], "idle")
        self.assertEqual(s["leaderboard"][0]["create"], 2)
        self.assertEqual(s["daily"][-1]["create"], 2)
        col = self.col.get("/api/inventory/stats/").json()
        self.assertEqual(len(col["branches"]), 1)

    def test_branch_status_by_collector(self):
        r = self.col.patch(f"/api/inventory/branches/{self.sam.id}/", {"status": "done", "name": "X"}, format="json")
        self.assertEqual(r.json()["status"], "done")
        self.sam.refresh_from_db()
        self.assertEqual(self.sam.name, "Samarqand")  # filial xodimi faqat holatni o'zgartira oladi
        self.assertIsNotNone(self.sam.finished_at)

    def test_staff_import_maps_cities(self):
        from zona.models import StaffPerson, StaffProject
        p = StaffProject.objects.create(name="Heinz")
        StaffPerson.objects.create(project=p, name="Ivanov Ivan", city="Самарканд", phone="+998")
        StaffPerson.objects.create(project=p, name="Petrov", city="Джизак")
        r = self.api.post("/api/inventory/employees/from-staff/", {}, format="json").json()
        self.assertEqual((r["created"], r["unmapped"]), (2, 1))
        self.assertEqual(Employee.objects.get(full_name="Ivanov Ivan").branch, self.sam)
        r = self.api.post("/api/inventory/employees/from-staff/", {}, format="json").json()
        self.assertEqual((r["created"], r["updated"]), (0, 2))  # qayta import — dublikat yo'q


PNG_DOT = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


class AckAndLanguageTests(InvBase):
    def emp(self, **extra):
        r = self.col.post("/api/inventory/employees/", {"full_name": "Karimov Aziz", "branch": self.sam.id, **extra},
                          format="json")
        self.assertIn(r.status_code, (200, 201), r.content)
        return r.json()

    def test_phone_and_telegram_normalized_and_validated(self):
        e = self.emp(phone="90 123 45 67", telegram="https://t.me/Karimov_Aziz")
        self.assertEqual((e["phone"], e["telegram"]), ("+998 90 123 45 67", "Karimov_Aziz"))
        r = self.col.patch(f"/api/inventory/employees/{e['id']}/", {"telegram": "@ab"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.col.patch(f"/api/inventory/employees/{e['id']}/", {"phone": "12"}, format="json", HTTP_X_LANG="ru")
        self.assertIn("номер телефона", r.json()["detail"])

    def test_russian_messages_and_catalog(self):
        r = self.col.post("/api/inventory/items/", {"branch": self.bux.id, "device_type": self.laptop.id}, format="json",
                          HTTP_X_LANG="ru")
        self.assertEqual(r.json()["detail"], "Нет прав на запись в этот филиал.")
        boot = self.col.get("/api/inventory/bootstrap/").json()
        laptop = next(d for d in boot["device_types"] if d["name"] == "Noutbuk")
        self.assertEqual(laptop["name_ru"], "Ноутбук")
        self.assertTrue(all(x["name_ru"] for x in boot["locations"]))

    def test_ack_flow_link_open_sign(self):
        e = self.emp(telegram="karimov_aziz")
        r = self.col.post(f"/api/inventory/employees/{e['id']}/ack/")
        self.assertEqual(r.status_code, 400)  # qurilmasi yo'q
        item = self.add_item(employee=e["id"])
        ack = self.col.post(f"/api/inventory/employees/{e['id']}/ack/").json()
        self.assertEqual((ack["status"], ack["items_count"], ack["outdated"]), ("pending", 1, False))
        anon = APIClient()
        page = anon.get(f"/api/inventory/public/ack/{ack['token']}/").json()
        self.assertEqual(page["employee_name"], "Karimov Aziz")
        self.assertEqual(page["items"][0]["inv_number"], item["inv_number"])
        self.assertNotIn("ip", page)
        bad = anon.post(f"/api/inventory/public/ack/{ack['token']}/sign/", {"name": "Karimov Aziz", "signature": ""},
                        format="json", HTTP_X_LANG="ru")
        self.assertEqual(bad.json()["detail"], "Поставьте подпись (нарисуйте пальцем).")
        ok = anon.post(f"/api/inventory/public/ack/{ack['token']}/sign/", {
            "name": "Karimov Aziz", "signature": PNG_DOT, "lang": "uz",
            "items": [{"id": item["id"], "ok": False, "comment": "menda emas"}]}, format="json")
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual((ok.json()["status"], ok.json()["issues"]), ("signed", 1))
        again = anon.post(f"/api/inventory/public/ack/{ack['token']}/sign/", {"name": "Karimov Aziz", "signature": PNG_DOT},
                          format="json")
        self.assertEqual(again.status_code, 400)
        detail = self.api.get(f"/api/inventory/acks/{ack['id']}/").json()
        self.assertEqual(anon.get(detail["signature_url"]).status_code, 200)
        s = self.api.get("/api/inventory/stats/").json()
        self.assertEqual(s["totals"]["acks_signed"], 1)
        lst = self.col.get("/api/inventory/employees/?ack=signed").json()
        self.assertEqual(lst["results"][0]["ack"]["status"], "signed")
        # qurilmalar o'zgarsa — tasdiqnoma eskiradi, bulk yangisini yaratadi
        self.add_item(employee=e["id"], serial="NEW-1")
        rows = self.api.get("/api/inventory/acks/").json()["results"]
        self.assertTrue(rows[0]["outdated"])
        self.assertEqual(self.api.post("/api/inventory/acks/bulk/", {}, format="json").json()["created"], 1)
        x = load_workbook(io.BytesIO(self.api.get("/api/inventory/acks/export/").content))
        self.assertIn("/ack/", x.active["J2"].value)

    def test_collector_cannot_ack_other_branch_and_revoke(self):
        other = Employee.objects.create(full_name="Boshqa Odam", branch=self.bux)
        self.assertEqual(self.col.post(f"/api/inventory/employees/{other.id}/ack/").status_code, 404)
        e = self.emp()
        self.add_item(employee=e["id"])
        ack = self.col.post(f"/api/inventory/employees/{e['id']}/ack/").json()
        self.col.post(f"/api/inventory/acks/{ack['id']}/revoke/")
        self.assertEqual(APIClient().get(f"/api/inventory/public/ack/{ack['token']}/").status_code, 404)


class ImportDedupeTests(InvBase):
    def upload(self, client, url, content, name="x.csv"):
        buf = io.BytesIO(content.encode("utf-8"))
        buf.name = name
        return client.post(url, {"file": buf}, format="multipart").json()

    def test_employees_reimport_does_not_duplicate(self):
        csv_text = "F.I.Sh.;Lavozimi;Telefon;Filial\nKarimov Aziz;Kassir;901234567;Samarqand\nToshev Ali;;;Buxoro\n"
        r1 = self.upload(self.api, "/api/inventory/employees/import/", csv_text)
        self.assertEqual(r1["employees_created"], 2, r1)
        # ikkinchi marta, katta-kichik harf va bo'shliqlar boshqacha
        r2 = self.upload(self.api, "/api/inventory/employees/import/",
                         "F.I.Sh.;Lavozimi;Telefon;Filial\nKARIMOV  aziz.;Kassir;+998 90 123 45 67;Samarqand\nToshev Ali;;;Buxoro\n")
        self.assertEqual(r2["employees_created"], 0, r2)
        self.assertEqual(Employee.objects.count(), 2)

    def test_employee_without_branch_and_inactive_are_reused(self):
        Employee.objects.create(full_name="Filialsiz Odam")
        Employee.objects.create(full_name="Ketgan Xodim", branch=self.sam, is_active=False)
        r = self.upload(self.api, "/api/inventory/employees/import/",
                        "F.I.Sh.;Filial\nFilialsiz Odam;Samarqand\nKetgan Xodim;Samarqand\n")
        self.assertEqual((r["employees_created"], r["employees_updated"]), (0, 2), r)
        self.assertEqual(Employee.objects.get(full_name="Filialsiz Odam").branch, self.sam)
        self.assertTrue(Employee.objects.get(full_name="Ketgan Xodim").is_active)

    def test_same_name_other_branch_matched_by_phone_only(self):
        Employee.objects.create(full_name="Aliyev Vali", branch=self.bux, phone="+998 90 111 22 33")
        r = self.upload(self.api, "/api/inventory/employees/import/",
                        "F.I.Sh.;Telefon;Filial\nAliyev Vali;90 111 22 33;Samarqand\nAliyev Vali;;Andijon\n")
        self.assertEqual(r["employees_created"], 1, r)  # telefon mos — o'sha odam; telefonsiz boshqa filialda — boshqa odam

    def test_items_without_serial_reimport_and_duplicate_rows(self):
        text = ("Qurilma turi;Filial;Brend;Model;Soni;Kimda turibdi (xodim);Qayerda turibdi\n"
                "Klaviatura va sichqoncha;Samarqand;Logitech;MK270;2;Karimov Aziz;Ofis\n"
                "Klaviatura va sichqoncha;Samarqand;Logitech;MK270;3;Karimov Aziz;Ofis\n"
                "Monitor;Samarqand;Samsung;S24;1;;Ofis\n")
        r1 = self.upload(self.api, "/api/inventory/items/import/", text)
        self.assertEqual((r1["created"], r1["employees_created"]), (2, 1), r1)
        kb = Item.objects.get(device_type__name="Klaviatura va sichqoncha")
        self.assertEqual(kb.quantity, 5)  # fayldagi takror qator — soni qo'shildi
        r2 = self.upload(self.api, "/api/inventory/items/import/", text)
        self.assertEqual((r2["created"], r2["employees_created"]), (0, 0), r2)
        self.assertEqual(Item.objects.count(), 2)
        kb.refresh_from_db()
        self.assertEqual(kb.quantity, 5)
        self.assertEqual(Employee.objects.count(), 1)

    def test_manual_add_and_staff_import_reuse_existing(self):
        r = self.col.post("/api/inventory/employees/", {"full_name": "karimov aziz", "branch": self.sam.id}, format="json")
        r2 = self.col.post("/api/inventory/employees/", {"full_name": "Karimov Aziz", "branch": self.sam.id}, format="json")
        self.assertEqual(r.json()["id"], r2.json()["id"])
        from zona.models import StaffPerson, StaffProject
        p = StaffProject.objects.create(name="Heinz")
        StaffPerson.objects.create(project=p, name="KARIMOV AZIZ", city="Самарканд")
        res = self.api.post("/api/inventory/employees/from-staff/", {}, format="json").json()
        self.assertEqual((res["created"], res["updated"]), (0, 1))
        self.assertEqual(Employee.objects.count(), 1)
        self.assertEqual(Employee.objects.get().project, "Heinz")
