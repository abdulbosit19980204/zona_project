"""Import / eksport: CSV, Excel (tekis jadval) va asl shablon formati (formulalar va ro'yxatlar bilan).

Shablon: data/template.xlsx ("StarGroup_IT_inventarizatsiya_shablon.xlsx"). Eksportda uning varaqlari bazadagi
katalog, filiallar, xodimlar va qurilmalar bilan to'ldiriladi — Filiallar va Xulosa formulalari o'zi hisoblaydi.
Importda o'sha shablon (to'ldirilgan holda) yoki eksport qilingan tekis jadval qabul qilinadi.
"""
import csv
import io
import re
from copy import copy

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from rest_framework.response import Response

from . import photos as photo_store
from .access import MANAGER, branch_scope, can_write_branch, level_of, scoped
from .models import Access, Branch, DeviceType, Employee, Item, Location, Log, Org
from .seed import CONDITION_BY_LABEL, TEMPLATE, norm
from .views import (COND_LABEL, STATUS_LABEL, CanWrite, HasInventory, IsManager, _int, _s, bad, compute_stats,
                    filter_items, inv_api, item_qs, log, next_inv_number, user_name)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HEAD_FILL = PatternFill("solid", fgColor="1F3A5F")
HEAD_FONT = Font(bold=True, color="FFFFFF")
THIN = Side(style="thin", color="D0D7E2")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

ITEM_COLUMNS = [
    ("Inventar raqam", 14), ("Tashkilot", 18), ("Filial", 14), ("Qayerda turibdi", 16), ("Qurilma turi", 28),
    ("Guruh", 12), ("Brend", 14), ("Model", 20), ("Seriya raqami (S/N)", 20), ("Soni", 6), ("Holati", 16),
    ("Kimda turibdi (xodim)", 26), ("Lavozimi", 18), ("Telefon", 16), ("Izoh", 30), ("Rasmlar soni", 8),
    ("Rasm havolalari", 40), ("Kiritgan", 16), ("Kiritilgan sana", 17), ("O'zgartirgan", 16),
    ("O'zgartirilgan sana", 17),
]
EMP_COLUMNS = [("F.I.Sh.", 30), ("Lavozimi", 20), ("Telefon", 18), ("Tashkilot", 20), ("Filial", 16),
               ("Loyiha (brend)", 18), ("Bo'lim", 18), ("Izoh", 24)]


def _now_tag():
    return timezone.localtime().strftime("%Y-%m-%d_%H%M")


def _file(content, name, mime):
    resp = HttpResponse(content, content_type=mime)
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    resp["Access-Control-Expose-Headers"] = "Content-Disposition"
    return resp


def _abs(request, path):
    try:
        return request.build_absolute_uri(path)
    except Exception:  # noqa: BLE001 — host noma'lum bo'lsa nisbiy manzil
        return path


def _local(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M") if dt else ""


def item_row(request, it):
    photos = list(it.photos.all())
    return [
        it.inv_number, it.org.name if it.org_id else "", it.branch.name, it.location, it.device_type.name,
        it.device_type.group, it.brand, it.model, it.serial, it.quantity, COND_LABEL.get(it.condition, it.condition),
        it.employee.full_name if it.employee_id else "", it.employee.position if it.employee_id else "",
        it.employee.phone if it.employee_id else "", it.note, len(photos),
        " ".join(_abs(request, photo_store.url(p)) for p in photos), user_name(it.created_by), _local(it.created_at),
        user_name(it.updated_by), _local(it.updated_at),
    ]


def style_table(ws, widths, header_row=1):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
        c = ws.cell(header_row, i)
        c.fill, c.font, c.border = HEAD_FILL, HEAD_FONT, BORDER
        c.alignment = Alignment(wrap_text=True, vertical="center")
    ws.freeze_panes = ws.cell(header_row + 1, 1)
    if ws.max_row > header_row:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(widths))}{ws.max_row}"


def add_sheet(wb, title, columns, rows, first=False):
    ws = wb.active if first else wb.create_sheet(title)
    ws.title = title
    ws.append([c[0] for c in columns])
    for r in rows:
        ws.append(r)
    style_table(ws, [c[1] for c in columns])
    return ws


def _save(wb):
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _csv(columns, rows):
    buf = io.StringIO()
    buf.write("﻿")  # Excel UTF-8 ni to'g'ri ochishi uchun
    w = csv.writer(buf, delimiter=";")
    w.writerow([c[0] for c in columns])
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


# ====================================================================== qurilmalar eksporti
def branch_status_rows(stats):
    flag = {"done": "Yakunlandi", "active": "Faol (24 soat)", "slowing": "Sekinlashgan", "slow": "Sust", "idle": "Boshlanmagan"}
    return [[b["code"], b["name"], b["region"], b["status_label"], b["conductor"], b["rows"], b["qty"],
             b["broken"], b["no_serial"], b["no_employee"], b["with_photo"], b["employees"],
             b["employees_with_devices"], b["today"], b["week"], _local(b["last_at"]), flag.get(b["flag"], b["flag"])]
            for b in stats["branches"]]


BRANCH_COLUMNS = [("Kod", 7), ("Filial", 14), ("Viloyat", 20), ("Holati", 12), ("O'tkazuvchi", 20),
                  ("Qatorlar", 9), ("Qurilmalar (dona)", 10), ("Ishlamaydi / ta'mir", 10), ("S/N yo'q", 9),
                  ("Xodimsiz", 9), ("Rasmli", 8), ("Xodimlar", 9), ("Qurilmasi bor xodimlar", 11), ("Bugun", 7),
                  ("7 kun", 7), ("Oxirgi faollik", 17), ("Faollik", 14)]


@inv_api(["GET"], [HasInventory])
def export_items(request):
    fmt = request.query_params.get("fmt", "xlsx")
    qs = filter_items(request, scoped(item_qs(), request.user)).order_by("branch__order", "branch__name", "inv_number")
    if fmt == "template":
        return _file(fill_template(request, qs if request.query_params.get("empty") != "1" else Item.objects.none()),
                     f"IT_inventarizatsiya_{_now_tag()}.xlsx", XLSX)
    rows = [item_row(request, it) for it in qs.iterator(chunk_size=500)] if fmt != "template" else []
    if fmt == "csv":
        return _file(_csv(ITEM_COLUMNS, rows), f"inventarizatsiya_{_now_tag()}.csv", "text/csv; charset=utf-8")
    wb = Workbook()
    add_sheet(wb, "Qurilmalar", ITEM_COLUMNS, rows, first=True)
    stats = compute_stats(request)
    add_sheet(wb, "Filiallar holati", BRANCH_COLUMNS, branch_status_rows(stats))
    emps = scoped(Employee.objects.select_related("org", "branch"), request.user).filter(is_active=True)
    add_sheet(wb, "Xodimlar", EMP_COLUMNS, [employee_row(e) for e in emps])
    return _file(_save(wb), f"inventarizatsiya_{_now_tag()}.xlsx", XLSX)


@inv_api(["GET"], [HasInventory])
def export_report(request):
    """Rahbarlar uchun hisobot: filiallar holati, qurilma turlari, xodimlar faolligi, kunlik dinamika."""
    stats = compute_stats(request)
    wb = Workbook()
    ws = wb.active
    ws.title = "Umumiy"
    t = stats["totals"]
    ws.append(["IT inventarizatsiyasi — hisobot", _local(stats["generated_at"])])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    for label, value in [
        ("Filiallar", t["branches"]), ("Yakunlangan", t["done"]), ("Jarayonda", t["active"]), ("Rejada", t["planned"]),
        ("Sust / boshlanmagan filiallar", t["slow"]), ("Kiritilgan qatorlar", t["rows"]), ("Qurilmalar (dona)", t["qty"]),
        ("Bugun kiritildi", t["today"]), ("Oxirgi 7 kunda", t["week"]), ("Ishlamaydi / ta'mirga muhtoj (dona)", t["broken"]),
        ("Topilmadi (dona)", t["missing"]), ("Seriya raqamsiz qatorlar", t["no_serial"]),
        ("Xodim biriktirilmagan qatorlar", t["no_employee"]), ("Rasmli qatorlar", t["with_photo"]),
        ("Xodimlar", t["employees_total"]), ("Qurilmasi bor xodimlar", t["employees_with_devices"]),
        ("Filial loginlari (faol)", t["collectors"]), ("Kamida bir marta kirgan", t["collectors_logged_in"]),
    ]:
        ws.append([label, value])
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 38, 18
    add_sheet(wb, "Filiallar holati", BRANCH_COLUMNS, branch_status_rows(stats))
    add_sheet(wb, "Qurilma turlari", [("Qurilma turi", 34), ("Guruh", 14), ("Qatorlar", 10), ("Dona", 10)],
              [[r["name"], r["group"], r["rows"], r["qty"]] for r in stats["by_type"]])
    add_sheet(wb, "Holat", [("Holati", 28), ("Dona", 10)], [[r["label"], r["qty"]] for r in stats["by_condition"]])
    add_sheet(wb, "Tashkilotlar", [("Tashkilot", 28), ("Qatorlar", 10), ("Dona", 10)],
              [[r["name"], r["rows"], r["qty"]] for r in stats["by_org"]])
    add_sheet(wb, "Xodimlar faolligi", [("Foydalanuvchi", 24), ("Login", 16), ("Filial(lar)", 24), ("Qo'shdi", 9),
                                        ("O'zgartirdi", 11), ("O'chirdi", 9), ("7 kunda qo'shdi", 12), ("Oxirgi faollik", 17)],
              [[r["name"], r["username"], ", ".join(r["branches"]), r["create"], r["update"], r["delete"], r["week"],
                _local(r["last_at"])] for r in stats["leaderboard"]])
    add_sheet(wb, "Kunlik dinamika", [("Sana", 12), ("Qo'shildi", 10), ("O'zgartirildi", 12), ("O'chirildi", 10)],
              [[d["date"], d["create"], d["update"], d["delete"]] for d in stats["daily"]])
    return _file(_save(wb), f"inventarizatsiya_hisobot_{_now_tag()}.xlsx", XLSX)


# ====================================================================== shablonni to'ldirish
ROW_REF = re.compile(r"(?<![$A-Z])([A-Z]{1,2})5(?!\d)")


def _formula_for_row(formula, r):
    return ROW_REF.sub(lambda m: f"{m.group(1)}{r}", formula) if isinstance(formula, str) else formula


def _clear(ws, row, cols):
    for c in cols:
        ws.cell(row, c).value = None


def _unitalic(ws, row, ref_row, cols):
    for c in cols:
        ws.cell(row, c).font = copy(ws.cell(ref_row, c).font)


def fill_template(request, items_qs):
    wb = load_workbook(TEMPLATE)
    ids = branch_scope(request.user)
    branches = list(Branch.objects.all() if ids is None else Branch.objects.filter(pk__in=ids))
    orgs, locations = list(Org.objects.all()), list(Location.objects.all())
    types = list(DeviceType.objects.filter(is_active=True))
    emps = list(scoped(Employee.objects.select_related("org", "branch"), request.user).filter(is_active=True)
                .order_by("branch__order", "full_name"))
    items = list(items_qs.select_related("org", "branch", "device_type", "employee"))

    # Tanlovlar
    t = wb["Tanlovlar"]
    for r in range(2, 60):
        _clear(t, r, range(1, 6))
    for i, o in enumerate(orgs, start=2):
        t.cell(i, 1, o.name)
        t.cell(i, 2, o.code)
    for i, (_, label) in enumerate(Item.CONDITIONS, start=2):
        t.cell(i, 3, label)
    for i, loc in enumerate(locations, start=2):
        t.cell(i, 4, loc.name)
    for i, (_, label) in enumerate(Branch.STATUSES, start=2):
        t.cell(i, 5, label)

    # Qurilmalar
    q = wb["Qurilmalar"]
    for r in range(5, max(q.max_row, 5 + len(types)) + 1):
        _clear(q, r, range(1, 15))
    for i, d in enumerate(types):
        r = 5 + i
        for c, v in enumerate([i + 1, d.name, d.group, d.description, d.serial_hint, d.extra_hint], start=1):
            q.cell(r, c, v or None)
        for j, b in enumerate((d.brands or [])[:8]):
            q.cell(r, 7 + j, b)
        if r > 34:
            for c in range(1, 15):
                q.cell(r, c)._style = copy(q.cell(34, c)._style)

    # Filiallar (H..J — formulalar)
    f = wb["Filiallar"]
    base_formulas = {c: f.cell(5, c).value for c in (8, 9, 10)}
    for r in range(5, max(35, 5 + len(branches))):
        _clear(f, r, range(1, 8))
    for i, b in enumerate(branches):
        r = 5 + i
        for c, v in enumerate([b.code, b.name, b.region, b.note, b.conductor,
                               b.started_at.strftime("%d.%m.%Y") if b.started_at else None,
                               STATUS_LABEL.get(b.status, b.status)], start=1):
            f.cell(r, c, v or None)
        if r > 34:
            for c in range(1, 11):
                f.cell(r, c)._style = copy(f.cell(34, c)._style)
            for c, formula in base_formulas.items():
                f.cell(r, c, _formula_for_row(formula, r))

    # Xodimlar
    x = wb["Xodimlar"]
    _clear(x, 5, range(1, 6))
    _unitalic(x, 5, 6, range(1, 6))
    for i, e in enumerate(emps):
        r = 5 + i
        for c, v in enumerate([e.full_name, e.position, e.phone, e.org.name if e.org_id else None,
                               e.branch.name if e.branch_id else None], start=1):
            x.cell(r, c, v or None)
    emp_last = max(1004, 4 + len(emps))

    # Inventarizatsiya (A, F, M, N — formulalar)
    inv = wb["Inventarizatsiya"]
    formulas = {c: inv.cell(5, c).value for c in (1, 6, 13, 14)}
    _clear(inv, 5, [2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 15])
    _unitalic(inv, 5, 6, range(1, 16))
    last = max(1000, 4 + len(items))
    for i, it in enumerate(items):
        r = 5 + i
        values = {2: it.org.name if it.org_id else None, 3: it.branch.name, 4: it.location or None,
                  5: it.device_type.name, 7: it.brand or None, 8: it.model or None, 9: it.serial or None,
                  10: it.quantity, 11: COND_LABEL.get(it.condition), 12: it.employee.full_name if it.employee_id else None,
                  15: (f"[{it.inv_number}] " + it.note).strip() if it.note else f"[{it.inv_number}]"}
        for c, v in values.items():
            inv.cell(r, c, v)
        if inv.cell(r, 1).value is None:
            for c, formula in formulas.items():
                inv.cell(r, c, _formula_for_row(formula, r))
            if r > 6:
                for c in range(1, 16):
                    inv.cell(r, c)._style = copy(inv.cell(6, c)._style)
    if emp_last > 1004:
        for row in inv.iter_rows(min_row=5, max_row=last):
            for c in (row[12], row[13]):
                if isinstance(c.value, str):
                    c.value = c.value.replace("$1004", f"${emp_last}")
    if last > 1000:  # Filiallar va Xulosa formulalari barcha qatorlarni qamrasin
        for sheet in (f, wb["Xulosa"]):
            for row in sheet.iter_rows():
                for c in row:
                    if isinstance(c.value, str) and "$1000" in c.value:
                        c.value = c.value.replace("$1000", f"${last}")

    _validations(wb, last, emp_last, 4 + max(len(branches), 30))
    wb.active = wb.sheetnames.index("Inventarizatsiya")
    return _save(wb)


def _dv(ws, formula, sqref, title, error, warning=False):
    dv = DataValidation(type="list", formula1=formula, allow_blank=True, showErrorMessage=True,
                        errorTitle=title, error=error, errorStyle="warning" if warning else "stop")
    dv.add(sqref)
    ws.add_data_validation(dv)


def _validations(wb, last, emp_last, branch_last):
    """Shablondagi ochiluvchi ro'yxatlar (openpyxl kengaytma ro'yxatlarini saqlamaydi — qayta qo'shamiz)."""
    inv, x, f = wb["Inventarizatsiya"], wb["Xodimlar"], wb["Filiallar"]
    org = "OFFSET(Tanlovlar!$A$2,0,0,MAX(1,COUNTA(Tanlovlar!$A$2:$A$50)),1)"
    br = f"OFFSET(Filiallar!$B$5,0,0,MAX(1,COUNTA(Filiallar!$B$5:$B${branch_last})),1)"
    _dv(inv, org, f"B5:B{last}", "Tashkilot", "Ro'yxatdan tanlang.")
    _dv(inv, br, f"C5:C{last}", "Filial", "Ro'yxatdan tanlang.")
    _dv(inv, "OFFSET(Tanlovlar!$D$2,0,0,MAX(1,COUNTA(Tanlovlar!$D$2:$D$50)),1)", f"D5:D{last}", "Qayerda turibdi",
        "Ro'yxatda yo'q joy. Shunday qoldirasizmi?", warning=True)
    _dv(inv, "OFFSET(Qurilmalar!$B$5,0,0,MAX(1,COUNTA(Qurilmalar!$B$5:$B$60)),1)", f"E5:E{last}", "Qurilma turi",
        "Ro'yxatdan tanlang.")
    _dv(inv, "OFFSET(Qurilmalar!$G$4,MATCH($E5,Qurilmalar!$B$5:$B$60,0),0,1,"
             "MAX(1,COUNTA(OFFSET(Qurilmalar!$G$4:$N$4,MATCH($E5,Qurilmalar!$B$5:$B$60,0),0))))",
        f"G5:G{last}", "Brend", "Bu brend ro'yxatda yo'q. Shunday qoldirasizmi?", warning=True)
    _dv(inv, "OFFSET(Tanlovlar!$C$2,0,0,MAX(1,COUNTA(Tanlovlar!$C$2:$C$50)),1)", f"K5:K{last}", "Holati",
        "Ro'yxatdan tanlang.")
    _dv(inv, f"OFFSET(Xodimlar!$A$5,0,0,MAX(1,COUNTA(Xodimlar!$A$5:$A${emp_last})),1)", f"L5:L{last}", "Xodim",
        "Bu xodim 'Xodimlar' ro'yxatida yo'q.", warning=True)
    whole = DataValidation(type="whole", operator="between", formula1="1", formula2="100000", allow_blank=True,
                           showErrorMessage=True, errorTitle="Soni", error="1 dan katta butun son kiriting.")
    whole.add(f"J5:J{last}")
    inv.add_data_validation(whole)
    _dv(x, org, f"D5:D{emp_last}", "Tashkilot", "Ro'yxatdan tanlang.")
    _dv(x, br, f"E5:E{emp_last}", "Filial", "Ro'yxatdan tanlang.")
    _dv(f, "OFFSET(Tanlovlar!$E$2,0,0,MAX(1,COUNTA(Tanlovlar!$E$2:$E$50)),1)", f"G5:G{branch_last}", "Holati",
        "Ro'yxatdan tanlang.")


# ====================================================================== import yordamchilari
def _read_table(upload):
    """Fayldan varaqlar: {nom: [qatorlar]}. CSV — bitta varaq."""
    name = (upload.name or "").lower()
    data = upload.read()
    if name.endswith(".csv") or name.endswith(".txt"):
        text = data.decode("utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:4000], delimiters=";,\t")
        except csv.Error:
            class dialect(csv.excel):  # noqa: N801
                delimiter = ";"
        return {"csv": [list(r) for r in csv.reader(io.StringIO(text), dialect)]}
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}


def _header(rows, must):
    """Sarlavha qatorini topadi: (indeks, {normallashgan nom: ustun})."""
    for i, row in enumerate(rows[:15]):
        # sarlavha katagi qisqa bo'ladi (yo'riqnoma matnlari sarlavha deb olinmasin)
        names = {norm(str(c).replace("▼", "")): j for j, c in enumerate(row)
                 if c not in (None, "") and len(str(c)) <= 40}
        if any(k.startswith(must) for k in names):
            return i, names
    return None, {}


def _col(names, *prefixes):
    for p in prefixes:
        for k, j in names.items():
            if k == p:
                return j
    for p in prefixes:
        for k, j in names.items():
            if k.startswith(p):
                return j
    return None


def _cell(row, j):
    if j is None or j >= len(row) or row[j] is None:
        return ""
    v = row[j]
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


class Lookup:
    def __init__(self):
        self.branches = {}
        for b in Branch.objects.all():
            self.branches[norm(b.name)] = b
            self.branches[norm(b.code)] = b
        self.orgs = {}
        for o in Org.objects.all():
            self.orgs[norm(o.name)] = o
            if o.code:
                self.orgs[norm(o.code)] = o
        self.types = {norm(d.name): d for d in DeviceType.objects.all()}
        self.emps = {}
        for e in Employee.objects.filter(is_active=True):
            self.emps[(norm(e.full_name), e.branch_id)] = e
            self.emps.setdefault((norm(e.full_name), None), e)


def _import_employees_rows(request, rows, lk, result, default_branch=None):
    idx, names = _header(rows, "f.i.sh")
    if idx is None:
        return
    c_name, c_pos, c_phone = _col(names, "f.i.sh."), _col(names, "lavozim"), _col(names, "telefon")
    c_org, c_branch = _col(names, "tashkilot"), _col(names, "filial")
    c_proj, c_dep, c_note = _col(names, "loyiha"), _col(names, "bo'lim"), _col(names, "izoh")
    manager = level_of(request.user) == MANAGER
    for n, row in enumerate(rows[idx + 1:], start=idx + 2):
        name = _cell(row, c_name)
        if len(name) < 3 or "(namuna)" in name.lower():
            continue
        bname = _cell(row, c_branch)
        branch = lk.branches.get(norm(bname)) if bname else default_branch
        if bname and not branch:
            result["errors"].append({"sheet": "Xodimlar", "row": n, "message": f"Filial topilmadi: {bname}"})
            continue
        if not manager and (not branch or not can_write_branch(request.user, branch.id)):
            result["errors"].append({"sheet": "Xodimlar", "row": n, "message": "Faqat o'z filialingiz xodimlari"})
            continue
        org = lk.orgs.get(norm(_cell(row, c_org)))
        fields = {"position": _cell(row, c_pos)[:120], "phone": _cell(row, c_phone)[:40],
                  "project": _cell(row, c_proj)[:120], "department": _cell(row, c_dep)[:120],
                  "note": _cell(row, c_note)[:255]}
        key = (norm(name), branch.id if branch else None)
        emp = lk.emps.get(key)
        if emp:
            changed = False
            for f, v in fields.items():
                if v and getattr(emp, f) != v:
                    setattr(emp, f, v)
                    changed = True
            if org and emp.org_id != org.id:
                emp.org, changed = org, True
            if changed:
                emp.save()
                result["employees_updated"] += 1
        else:
            emp = Employee.objects.create(full_name=name[:150], branch=branch, org=org, source=Employee.IMPORT,
                                          created_by=request.user, **fields)
            lk.emps[key] = emp
            lk.emps.setdefault((norm(name), None), emp)
            result["employees_created"] += 1


def _items_from_rows(request, rows, lk, result, default_branch, sheet):
    idx, names = _header(rows, "qurilma turi")
    if idx is None:
        return False
    cols = {
        "inv": _col(names, "inventar raqam"), "org": _col(names, "tashkilot"), "branch": _col(names, "filial"),
        "location": _col(names, "qayerda turibdi"), "type": _col(names, "qurilma turi"), "brand": _col(names, "brend"),
        "model": _col(names, "model"), "serial": _col(names, "seriya raqami (s/n)", "seriya"),
        "qty": _col(names, "soni"), "condition": _col(names, "holati"),
        "employee": _col(names, "kimda turibdi (xodim)", "kimda"), "position": _col(names, "lavozim"),
        "phone": _col(names, "telefon"), "note": _col(names, "izoh"),
    }
    numbers = {}
    for n, row in enumerate(rows[idx + 1:], start=idx + 2):
        tname = _cell(row, cols["type"])
        if not tname:
            continue
        emp_name = _cell(row, cols["employee"])
        if "(namuna)" in emp_name.lower():
            continue
        dt = lk.types.get(norm(tname))
        if not dt:
            result["errors"].append({"sheet": sheet, "row": n, "message": f"Qurilma turi topilmadi: {tname}"})
            continue
        bname = _cell(row, cols["branch"])
        branch = lk.branches.get(norm(bname)) if bname else default_branch
        if not branch:
            result["errors"].append({"sheet": sheet, "row": n, "message": f"Filial topilmadi: {bname or '(bo`sh)'}"})
            continue
        if not can_write_branch(request.user, branch.id):
            result["errors"].append({"sheet": sheet, "row": n, "message": f"{branch.name}: yozish huquqi yo'q"})
            continue
        cond_raw = _cell(row, cols["condition"])
        cond = CONDITION_BY_LABEL.get(norm(cond_raw), Item.OK) if cond_raw else Item.OK
        if cond_raw and norm(cond_raw) not in CONDITION_BY_LABEL and cond_raw not in COND_LABEL:
            result["warnings"].append({"sheet": sheet, "row": n, "message": f"Holat tanilmadi ({cond_raw}) — 'Ishlayapti'"})
        elif cond_raw in COND_LABEL:
            cond = cond_raw
        emp = None
        if emp_name:
            emp = lk.emps.get((norm(emp_name), branch.id)) or lk.emps.get((norm(emp_name), None))
            if not emp:
                emp = Employee.objects.create(full_name=emp_name[:150], branch=branch, source=Employee.IMPORT,
                                              position=_cell(row, cols["position"])[:120],
                                              phone=_cell(row, cols["phone"])[:40], created_by=request.user)
                lk.emps[(norm(emp_name), branch.id)] = emp
                result["employees_created"] += 1
        note = _cell(row, cols["note"])
        inv_number = _cell(row, cols["inv"])
        m = re.match(r"^\[([A-Z0-9]+-\d+)\]\s*", note)  # shablon eksportida raqam izohda: "[SAM-00012] ..."
        if m:
            inv_number = inv_number or m.group(1)
            note = note[m.end():]
        qty = _int(_cell(row, cols["qty"]), 1) or 1
        fields = {"org": lk.orgs.get(norm(_cell(row, cols["org"]))), "branch": branch,
                  "location": _cell(row, cols["location"])[:120], "device_type": dt,
                  "brand": _cell(row, cols["brand"])[:80], "model": _cell(row, cols["model"])[:150],
                  "serial": _cell(row, cols["serial"])[:120], "quantity": max(qty, 1), "condition": cond,
                  "employee": emp, "note": note[:2000]}
        item = None
        if inv_number:
            item = scoped(Item.objects.all(), request.user).filter(inv_number=inv_number).first()
        if not item and fields["serial"]:
            item = Item.objects.filter(branch=branch, device_type=dt, serial__iexact=fields["serial"],
                                       is_deleted=False).first()
        if item:
            changes = {}
            for f, v in fields.items():
                old = getattr(item, f)
                if (old.pk if hasattr(old, "pk") else old) != (v.pk if hasattr(v, "pk") else v):
                    changes[f] = [str(old or ""), str(v or "")]
                    setattr(item, f, v)
            if changes:
                item.updated_by = request.user
                item.save()
                log(request, Log.UPDATE, branch=branch, item=item, changes=changes,
                    summary=f"Import: {item.inv_number} · {', '.join(changes)}")
                result["updated"] += 1
            else:
                result["unchanged"] += 1
        else:
            item = Item(**fields, created_by=request.user, updated_by=request.user)
            item.inv_number = next_inv_number(branch.id)
            item.save()
            log(request, Log.IMPORT, branch=branch, item=item,
                summary=f"Import: {item.inv_number} · {dt.name} {fields['brand']} {fields['model']}".strip())
            result["created"] += 1
            numbers[branch.id] = numbers.get(branch.id, 0) + 1
    for bid in numbers:
        b = Branch.objects.get(pk=bid)
        if b.status == Branch.PLANNED:
            b.status, b.started_at = Branch.ACTIVE, b.started_at or timezone.localdate()
            b.save(update_fields=["status", "started_at"])
    return True


def _default_branch(request):
    ids = branch_scope(request.user)
    if ids is not None and len(ids) == 1:
        return Branch.objects.filter(pk__in=ids).first()
    bid = _int(request.data.get("branch"))
    return Branch.objects.filter(pk=bid).first() if bid else None


@inv_api(["POST"], [CanWrite], multipart=True)
def import_items(request):
    """Fayl: to'ldirilgan shablon (Inventarizatsiya + Xodimlar varaqlari) yoki eksport qilingan jadval (xlsx/csv).
    dry_run=1 — hech narsa saqlanmaydi, faqat nima bo'lishi ko'rsatiladi."""
    upload = request.FILES.get("file")
    if not upload:
        return bad("Fayl tanlanmagan.")
    try:
        sheets = _read_table(upload)
    except Exception as e:  # noqa: BLE001 — buzilgan fayl
        return bad(f"Faylni o'qib bo'lmadi: {e}")
    dry = str(request.data.get("dry_run", "")) in ("1", "true", "True")
    result = {"created": 0, "updated": 0, "unchanged": 0, "employees_created": 0, "employees_updated": 0,
              "errors": [], "warnings": [], "dry_run": dry}
    default_branch = _default_branch(request)
    with transaction.atomic():
        lk = Lookup()
        emp_sheet = next((s for s in sheets if norm(s) == "xodimlar"), None)
        if emp_sheet:
            _import_employees_rows(request, sheets[emp_sheet], lk, result, default_branch)
        skip = {"xodimlar", "kirish", "tanlovlar", "xulosa", "filiallar", "filiallar holati"}
        if "Inventarizatsiya" in sheets:
            candidates = ["Inventarizatsiya"]  # shablondagi "Qurilmalar" — katalog, qurilmalar ro'yxati emas
        else:
            candidates = [s for s in sheets if norm(s) not in skip]
        found = any(_items_from_rows(request, sheets[name], lk, result, default_branch, name) for name in candidates)
        if not found and not emp_sheet:
            transaction.set_rollback(True)
            return bad("Faylda 'Qurilma turi' ustuni topilmadi. Shablon yoki eksport qilingan jadvalni yuklang.")
        if dry:
            transaction.set_rollback(True)
        elif result["created"] or result["updated"] or result["employees_created"]:
            log(request, Log.IMPORT, branch=default_branch, entity="import",
                summary=f"Import ({upload.name}): {result['created']} yangi, {result['updated']} yangilandi, "
                        f"{result['employees_created']} xodim, {len(result['errors'])} xato")
    result["errors"] = result["errors"][:200]
    result["warnings"] = result["warnings"][:100]
    return Response(result)


# ====================================================================== xodimlar import / eksport
def employee_row(e):
    return [e.full_name, e.position, e.phone, e.org.name if e.org_id else "", e.branch.name if e.branch_id else "",
            e.project, e.department, e.note]


@inv_api(["GET"], [HasInventory])
def employees_export(request):
    fmt = request.query_params.get("fmt", "xlsx")
    qs = scoped(Employee.objects.select_related("org", "branch"), request.user).filter(is_active=True) \
        .order_by("branch__order", "full_name")
    bid = _int(request.query_params.get("branch"))
    if bid:
        qs = qs.filter(branch_id=bid)
    rows = [employee_row(e) + [e.items.filter(is_deleted=False).count()] for e in qs]
    columns = EMP_COLUMNS + [("Qurilmalar soni", 10)]
    if fmt == "csv":
        return _file(_csv(columns, rows), f"xodimlar_{_now_tag()}.csv", "text/csv; charset=utf-8")
    wb = Workbook()
    add_sheet(wb, "Xodimlar", columns, rows, first=True)
    return _file(_save(wb), f"xodimlar_{_now_tag()}.xlsx", XLSX)


@inv_api(["GET"], [HasInventory])
def employees_template(request):
    """Bo'sh xodimlar shabloni: ochiluvchi Tashkilot / Filial ro'yxatlari va yo'riqnoma bilan."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Xodimlar"
    ws.append(["Xodimlar ro'yxati — har bir xodim uchun bitta qator"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["F.I.Sh. majburiy. Tashkilot va Filial — ro'yxatdan tanlang (katakni bosing). Loyiha — brend jamoasi "
               "(Heinz, BIC...). Tayyor bo'lgach saytda: Xodimlar → Import."])
    ws.append([])
    ws.append([c[0] for c in EMP_COLUMNS])
    ws.append(["Karimov Aziz (namuna)", "Savdo menejeri", "+998 90 123 45 67", "Star Distribution", "Samarqand",
               "Heinz", "Savdo bo'limi", ""])
    for c in range(1, len(EMP_COLUMNS) + 1):
        ws.cell(5, c).font = Font(italic=True, color="7F7F7F")
    style_table(ws, [c[1] for c in EMP_COLUMNS], header_row=4)
    ws.auto_filter.ref = None
    ch = wb.create_sheet("Tanlovlar")
    ids = branch_scope(request.user)
    branches = Branch.objects.all() if ids is None else Branch.objects.filter(pk__in=ids)
    ch.append(["Tashkilot", "Filial"])
    orgs, brs = [o.name for o in Org.objects.all()], [b.name for b in branches]
    for i in range(max(len(orgs), len(brs))):
        ch.append([orgs[i] if i < len(orgs) else None, brs[i] if i < len(brs) else None])
    _dv(ws, f"Tanlovlar!$A$2:$A${max(2, len(orgs) + 1)}", "D5:D3000", "Tashkilot", "Ro'yxatdan tanlang.")
    _dv(ws, f"Tanlovlar!$B$2:$B${max(2, len(brs) + 1)}", "E5:E3000", "Filial", "Ro'yxatdan tanlang.")
    return _file(_save(wb), "xodimlar_shablon.xlsx", XLSX)


@inv_api(["POST"], [CanWrite], multipart=True)
def employees_import(request):
    upload = request.FILES.get("file")
    if not upload:
        return bad("Fayl tanlanmagan.")
    try:
        sheets = _read_table(upload)
    except Exception as e:  # noqa: BLE001
        return bad(f"Faylni o'qib bo'lmadi: {e}")
    dry = str(request.data.get("dry_run", "")) in ("1", "true", "True")
    result = {"employees_created": 0, "employees_updated": 0, "errors": [], "warnings": [], "dry_run": dry}
    with transaction.atomic():
        lk = Lookup()
        name = next((s for s in sheets if norm(s) == "xodimlar"), None) or next(iter(sheets))
        if _header(sheets[name], "f.i.sh")[0] is None:
            return bad("Faylda 'F.I.Sh.' ustuni topilmadi. Xodimlar shablonini yuklab, shu shaklda to'ldiring.")
        _import_employees_rows(request, sheets[name], lk, result, _default_branch(request))
        if dry:
            transaction.set_rollback(True)
        elif result["employees_created"] or result["employees_updated"]:
            log(request, Log.IMPORT, entity="employee",
                summary=f"Xodimlar importi ({upload.name}): {result['employees_created']} yangi, "
                        f"{result['employees_updated']} yangilandi")
    result["errors"] = result["errors"][:200]
    return Response(result)


# ====================================================================== loginlar fayli
@inv_api(["GET"], [IsManager])
def credentials(request):
    """Barcha modul foydalanuvchilari: login, boshlang'ich parol va filial — tarqatish uchun."""
    from zona import conf
    from zona.crypto import decrypt
    site = (conf.get("FRONTEND_URL") or "").rstrip("/")
    if not site.startswith("http"):
        site = _abs(request, "/").rstrip("/")
    link = f"{site}/inventory"
    wb = Workbook()
    ws = wb.active
    ws.title = "Loginlar"
    ws.append(["IT inventarizatsiya — kirish ma'lumotlari"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([f"Sayt: {link}   ·   Telefonda shu manzilni oching, login va parolni yozing. "
               "Parolni boshqalarga bermang."])
    ws.append([])
    columns = [("Filial", 16), ("Login", 16), ("Parol", 14), ("Ism", 22), ("Daraja", 20), ("Holat", 22),
               ("Oxirgi kirish", 17), ("Sayt", 36)]
    ws.append([c[0] for c in columns])
    rows = Access.objects.select_related("user").prefetch_related("branches").order_by("level", "user__username")
    level_label = dict(Access.LEVELS)
    for acc in rows:
        u = acc.user
        pw = decrypt(acc.password_enc) if acc.password_enc else ""
        state = "Bloklangan" if not u.is_active else ""
        if pw and not u.check_password(pw):
            state, pw = "Parolni o'zi o'zgartirgan", ""
        elif not pw:
            state = state or "Zona paroli (bu yerda yo'q)"
        ws.append([", ".join(b.name for b in acc.branches.all()) or "Hammasi", u.username, pw, user_name(u),
                   level_label.get(acc.level, acc.level), state, _local(u.last_login), link])
    style_table(ws, [c[1] for c in columns], header_row=4)
    for row in ws.iter_rows(min_row=5, min_col=3, max_col=3):
        for c in row:
            c.font = Font(name="Consolas", bold=True)
    log(request, Log.LOGIN, entity="user", summary="Loginlar fayli yuklab olindi")
    return _file(_save(wb), f"inventarizatsiya_loginlar_{_now_tag()}.xlsx", XLSX)
