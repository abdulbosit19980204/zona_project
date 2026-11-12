"""Excel eksport: xodimlar, to'liq ro'yxat, mas'uliyat matritsasi, aralash holatlar."""
from collections import defaultdict
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

FONT = "Arial"
HEAD_FILL = PatternFill("solid", start_color="111A2E")
SOFT_FILL = PatternFill("solid", start_color="EEF1F6")
HEAD_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
BODY_FONT = Font(name=FONT, size=10)
BOLD_FONT = Font(name=FONT, size=10, bold=True)
THIN = Side(style="thin", color="D1D5DB")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP_TOP = Alignment(wrap_text=True, vertical="top")
CENTER = Alignment(horizontal="center", vertical="center")

UNASSIGNED = "Biriktirilmagan"
# Matritsadagi qisqa belgilar
GLYPH = {"owner": "E", "approver": "T", "supervisor": "N", "contributor": "Y", "backup": "Z"}


def _header(ws, row, titles):
    for col, title in enumerate(titles, 1):
        c = ws.cell(row=row, column=col, value=title)
        c.font, c.fill, c.border = HEAD_FONT, HEAD_FILL, BORDER
        c.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[row].height = 26


def _widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _row(ws, r, values, bold_cols=()):
    for col, v in enumerate(values, 1):
        c = ws.cell(row=r, column=col, value=v)
        c.font = BOLD_FONT if col in bold_cols else BODY_FONT
        c.alignment, c.border = WRAP_TOP, BORDER


def build_workbook(company, members, processes, tasks, roles, edge_cases, authorities=()):
    wb = Workbook()
    by_member = defaultdict(int)
    for t in tasks:
        by_member[t.owner_id] += 1
    auth = defaultdict(list)
    for a in authorities:
        auth[a.member_id].append(a.title + (f" ({a.scope})" if a.scope else ""))

    ws = wb.active
    ws.title = "Xodimlar"
    ws["A1"] = f"{company}: kim nimaga javob beradi"
    ws["A1"].font = Font(name=FONT, size=14, bold=True)
    _header(ws, 3, ["Bo'lim", "Xodim", "Lavozim", "Nima bilan shug'ullanadi",
                    "Nima bilan shug'ullanmaydi (kimga)", "Vakolatlar", "Telefon", "Telegram", "Email", "Vazifalar"])
    for r, m in enumerate(members, 4):
        _row(ws, r, [m.department.name if m.department else "", m.name, m.role, m.does, m.excludes,
                     "\n".join(auth[m.id]), m.phone, f"@{m.telegram}" if m.telegram else "", m.email,
                     by_member[m.id]], bold_cols=(2,))
        ws.cell(row=r, column=10).alignment = CENTER
    _widths(ws, [22, 24, 22, 56, 56, 36, 16, 16, 24, 11])
    ws.freeze_panes = "A4"

    ws2 = wb.create_sheet("To'liq ro'yxat")
    _header(ws2, 1, ["№", "Mas'ul", "Lavozim", "Jarayon", "Tizim", "Savol turi / vazifa",
                     "Qila olmasa, navbatdagi mas'ullar"])
    names = {m.id: m.name for m in members}
    for i, t in enumerate(tasks, 1):
        p = t.process
        chain = "\n".join(f"{n}. {names.get(f.member_id, '?')}" + (f" — {f.condition}" if f.condition else "")
                          for n, f in enumerate(t.fallbacks.all(), 2))
        _row(ws2, i + 1, [i, t.owner.name if t.owner else UNASSIGNED, t.owner.role if t.owner else "",
                          p.name if p else "", p.system.name if p and p.system else "", t.title, chain], bold_cols=(2,))
        ws2.cell(row=i + 1, column=1).alignment = CENTER
    ws2.auto_filter.ref = f"A1:G{max(len(tasks) + 1, 2)}"
    ws2.freeze_panes = "A2"
    _widths(ws2, [6, 22, 20, 40, 16, 80, 40])

    ws3 = wb.create_sheet("Matritsa")
    ws3["A1"] = "E: egasi · I: ijrochi (vazifalar soni) · T: tasdiqlovchi · N: nazoratchi · Y: yordamchi · Z: zaxira"
    ws3["A1"].font = Font(name=FONT, size=9, italic=True, color="4B5563")
    _header(ws3, 2, ["Jarayon", "Tizim"] + [m.name for m in members])
    cell_roles = defaultdict(list)
    for role in roles:
        cell_roles[(role.process_id, role.member_id)].append(GLYPH.get(role.role, "?"))
    executes = defaultdict(int)
    for t in tasks:
        if t.process_id and t.owner_id:
            executes[(t.process_id, t.owner_id)] += 1
    for r, p in enumerate(processes, 3):
        _row(ws3, r, [p.name, p.system.name if p.system else ""], bold_cols=(1,))
        for c, m in enumerate(members, 3):
            parts = sorted(cell_roles[(p.id, m.id)])
            if executes[(p.id, m.id)]:
                parts.append(f"I{executes[(p.id, m.id)]}")
            cell = ws3.cell(row=r, column=c, value=" ".join(parts))
            cell.font, cell.border, cell.alignment = BODY_FONT, BORDER, CENTER
            if parts:
                cell.fill = SOFT_FILL
    _widths(ws3, [40, 14] + [16] * len(members))
    ws3.freeze_panes = "C3"

    ws4 = wb.create_sheet("Aralash holatlar")
    _header(ws4, 1, ["Vaziyat", "Avval kimga", "Qachon boshqa zonaga o'tadi"])
    for i, values in enumerate(edge_cases, 2):
        _row(ws4, i, list(values), bold_cols=(2,))
    _widths(ws4, [44, 24, 70])
    ws4.freeze_panes = "A2"
    return wb


def workbook_bytes(*args, **kwargs) -> bytes:
    buf = BytesIO()
    build_workbook(*args, **kwargs).save(buf)
    return buf.getvalue()
