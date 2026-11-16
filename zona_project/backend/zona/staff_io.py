"""Dala jamoalari tuzilmasi: import (link / HTML / JSON / Excel / CSV), solishtirish va eksport.

Umumiy almashinuv formati (JSON):
    {"format": "zona-staff", "version": 1,
     "project": {"name": "Heinz", "description": "", "source_url": ""},
     "units":   [{"key": "tashkent", "title": "Toshkent"}],
     "people":  [{"key": "1", "name": "...", "role": "SVR", "position": "СВР", "territory": "SVR Tash 1",
                  "region": "", "city": "", "phone": "+998 ...", "email": "", "note": "", "vacancy": false,
                  "unit": "tashkent", "manager": "<rahbarning key>"}]}

Har qanday manba avval shu formatga keltiriladi; keyin bazadagi holat bilan solishtiriladi (preview) va
tasdiqlansa qo'llanadi. Import qilingan fayl — loyihaning to'liq holati: unda yo'q xodimlar o'chiriladi.
Moslashtirish: avval hudud kodi (lavozim o'rni) bo'yicha — odam almashsa "almashdi" deb ko'rsatiladi,
keyin F.I.Sh. bo'yicha (hududi o'zgargan xodim).
"""
import csv
import html
import io
import json
import re
import urllib.error
import urllib.request
from collections import Counter

from django.db import transaction
from django.utils import timezone

from . import staff_text
from .models import StaffPerson, StaffProject, StaffUnit

FORMAT = "zona-staff"
ROLES = {r for r, _ in StaffPerson.ROLES}
FIELDS = ["name", "role", "position", "territory", "region", "city", "phone", "email", "telegram", "note", "vacancy", "unit", "manager"]
MAX_BYTES = 5 * 1024 * 1024


class StaffImportError(Exception):
    pass


# ------------------------------------------------------------------ yordamchi
def phone(value):
    """+998 XX XXX XX XX ko'rinishiga keltirish (tanilmasa — o'zgarishsiz)."""
    raw = str(value or "").strip()
    if raw.endswith(".0"):
        raw = raw[:-2]
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 9:
        digits = "998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        return f"+998 {digits[3:5]} {digits[5:8]} {digits[8:10]} {digits[10:12]}"
    return raw


def telegram(value):
    """Telegram: @username yoki t.me havolasidan username; telefon raqami bo'lsa — bo'sh (telefon orqali ochiladi)."""
    raw = str(value or "").strip()
    raw = re.sub(r"^(https?://)?(www\.)?(t|telegram)\.(me|dog)/", "", raw, flags=re.I).strip("/@ ")
    if not raw or re.fullmatch(r"[+\d\s()-]+", raw):
        return ""
    return raw if re.fullmatch(r"[A-Za-z0-9_]{3,64}", raw) else ""


def fold(value):
    """Solishtirish uchun: kichik harf, apostroflar va bo'shliqlar bir xil."""
    s = str(value or "").lower().strip()
    s = re.sub(r"[ʻʼ’‘`´']", "", s)
    s = s.replace("х", "x").replace("о", "o").replace("а", "a").replace("с", "c").replace("е", "e").replace("р", "p")
    return re.sub(r"\s+", " ", s)


def slug(value, fallback="u"):
    s = re.sub(r"[^a-z0-9а-яё]+", "-", str(value or "").lower()).strip("-")
    return s[:50] or fallback


VACANCY_WORDS = ("вакансия", "vacancy", "vakansiya", "вакант")


def _is_vacancy_name(name):
    n = fold(name)
    return not n or any(w in n for w in VACANCY_WORDS)


def _role(value, default="TP"):
    r = str(value or "").strip().upper()
    aliases = {"СВР": "SVR", "ТП": "TP", "РОП": "ROP", "МЕРЧ": "MER", "MR": "MER", "SPEC": "TP", "SR": "TP"}
    r = aliases.get(r, r)
    return r if r in ROLES else (default if r in ("", "VAC") else "OTHER")


def empty(name="", source_url=""):
    return {"format": FORMAT, "version": 1, "project": {"name": name, "description": "", "source_url": source_url},
            "units": [], "people": []}


def _person(**kw):
    p = {f: "" for f in FIELDS}
    p["vacancy"] = False
    p.update(kw)
    p["phone"] = phone(p["phone"])
    p["telegram"] = telegram(p["telegram"])
    for f in FIELDS:
        if f != "vacancy":
            p[f] = str(p[f] or "").strip()
    return p


# ------------------------------------------------------------------ artifact (HTML ichidagi const DATA)
def _grab_json(src, name):
    """`const NAME = {...}` dagi JSON ni qavs balansi bo'yicha ajratib oladi."""
    m = re.search(r"const\s+" + name + r"\s*=\s*([\[{])", src)
    if not m:
        return None
    i = m.start(1)
    depth, in_str, j = 0, False, i
    while j < len(src):
        c = src[j]
        if in_str:
            if c == "\\":
                j += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if not depth:
                raw = src[i:j + 1]
                try:
                    return json.loads(raw)
                except ValueError:
                    pass
                # JS obyekt yozuvi: {id:"kam"} — kalitlarni qo'shtirnoqqa olamiz
                try:
                    return json.loads(re.sub(r'([{,]\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', raw))
                except ValueError:
                    return None
        j += 1
    return None


def _title_name(src):
    m = re.search(r"<title>([^<]+)</title>", src, re.I)
    title = (m.group(1) if m else "").strip()
    title = re.sub(r"^(структура\s+(полевой\s+)?команды|team structure|tuzilma)\s*", "", title, flags=re.I)
    return title.strip(" :—-")


def from_artifact(data, rop=None, branches_meta=None, name="", source_url=""):
    """Jamoa tuzilmasi sahifalaridagi DATA (Heinz, BIC, L'Oréal...) -> umumiy format."""
    out = empty(name, source_url)
    keys = set()
    seq = [0]

    def key_of(p):
        k = str(p.get("n") or "").strip()
        if not k or k in keys:
            seq[0] += 1
            k = f"x{seq[0]}"
        keys.add(k)
        return k

    def add(p, unit, manager, default_role, head=False):
        if not p:
            return None
        raw_role = str(p.get("role") or "").upper()
        name_ = str(p.get("name") or "")
        vacancy = raw_role == "VAC" or _is_vacancy_name(name_)
        role = _role(raw_role, default_role)
        if raw_role == "VAC" or role == "OTHER" and vacancy:
            role = "SVR" if (head or p.get("svr") or "SVR" in str(p.get("terr") or "").upper()) else default_role
        k = key_of(p)
        out["people"].append(_person(
            key=k, name="" if vacancy else name_, role=role, position=p.get("pos") or "", territory=p.get("terr") or "",
            region=p.get("region") or "", city=p.get("city") or "", phone=p.get("phone") or "", vacancy=vacancy,
            unit=unit or "", manager=manager or ""))
        return k

    top = data.get("asm") or data.get("rop") or rop
    top_key = add(dict(top, role=(top.get("role") or ("ROP" if rop else "ASM"))), "", "", "ROP") if top else ""
    for i, b in enumerate(data.get("branches") or []):
        meta = (branches_meta or [])[i] if branches_meta and i < len(branches_meta) else {}
        key = str(b.get("id") or meta.get("id") or f"u{i + 1}")
        title = str(b.get("title") or meta.get("title") or key)
        base, n = key, 2
        while any(u["key"] == key for u in out["units"]):  # takroriy id: kam, kam-2
            key, n = f"{base}-{n}", n + 1
        out["units"].append({"key": key, "title": title})
        bhead = add(b.get("head"), key, top_key, "RSM", head=True) if b.get("head") else ""
        boss = bhead or top_key
        for t in b.get("teams") or []:
            h = add(t.get("head"), key, boss, "SVR", head=True)
            for m in t.get("members") or []:
                add(m, key, h or boss, "TP")
        for d in b.get("direct") or []:
            add(d, key, boss, "TP")
    return out


# ------------------------------------------------------------------ jadval (Excel / CSV)
COLUMNS = [  # (maydon, sarlavha) — eksport tartibi
    ("key", "№"), ("project", "Loyiha"), ("unit", "Yo'nalish"), ("role", "Rol"), ("position", "Lavozim"),
    ("name", "F.I.Sh."), ("territory", "Hudud kodi"), ("region", "Region"), ("city", "Shahar"),
    ("phone", "Telefon"), ("telegram", "Telegram"), ("email", "Email"), ("manager", "Rahbar №"), ("manager_name", "Rahbar"),
    ("vacancy", "Vakansiya"), ("note", "Izoh"),
]
HEADER_ALIASES = {
    "key": ["№", "n", "#", "id", "no"],
    "project": ["loyiha", "проект", "бренд", "project", "brand"],
    "unit": ["yo'nalish", "yonalish", "направление", "филиал", "unit", "branch", "direction"],
    "role": ["rol", "роль", "role"],
    "position": ["lavozim", "должность", "позиция", "position", "pos"],
    "name": ["f.i.sh.", "fish", "фио", "ф.и.о.", "ism", "name", "full name", "сотрудник"],
    "territory": ["hudud kodi", "hudud", "территория", "код территории", "territory", "terr"],
    "region": ["region", "регион", "viloyat"],
    "city": ["shahar", "город", "city"],
    "phone": ["telefon", "телефон", "phone", "тел"],
    "email": ["email", "e-mail", "почта"],
    "telegram": ["telegram", "телеграм", "tg"],
    "manager": ["rahbar №", "rahbar no", "руководитель №", "manager no", "manager #"],
    "manager_name": ["rahbar", "руководитель", "manager"],
    "vacancy": ["vakansiya", "вакансия", "vacancy"],
    "note": ["izoh", "примечание", "комментарий", "note"],
}


def _header_map(row):
    norm = {fold(h).replace("ʻ", "'"): i for i, h in enumerate(row) if str(h or "").strip()}
    out = {}
    for field, names in HEADER_ALIASES.items():
        for n in [fold(x) for x in names]:
            if n in norm and field not in out and norm[n] not in out.values():
                out[field] = norm[n]
                break
    return out


def from_rows(rows, name="", source_url=""):
    """Jadval qatorlari (birinchisi — sarlavha) -> {loyiha nomi: umumiy format}."""
    rows = [list(r) for r in rows if any(str(c or "").strip() for c in r)]
    if not rows:
        raise StaffImportError("Jadval bo'sh.")
    hmap = _header_map(rows[0])
    if "name" not in hmap or not ({"territory", "role"} & set(hmap)):
        raise StaffImportError("Sarlavhalar tanilmadi: kamida \"F.I.Sh.\" va \"Hudud kodi\" yoki \"Rol\" ustunlari kerak.")
    val = lambda r, f: str(r[hmap[f]] if f in hmap and hmap[f] < len(r) and r[hmap[f]] is not None else "").strip()  # noqa: E731
    projects = {}
    for n, r in enumerate(rows[1:], start=1):
        pname = val(r, "project") or name
        if not pname:
            raise StaffImportError("\"Loyiha\" ustuni bo'sh: import qilinadigan loyihani tanlang.")
        doc = projects.setdefault(pname, empty(pname, source_url))
        unit_title = val(r, "unit")
        ukey = ""
        if unit_title:
            ukey = next((u["key"] for u in doc["units"] if u["title"] == unit_title), None) or slug(unit_title, f"u{len(doc['units']) + 1}")
            if all(u["key"] != ukey for u in doc["units"]):
                doc["units"].append({"key": ukey, "title": unit_title})
        key = val(r, "key").removesuffix(".0") or f"r{n}"
        person_name = val(r, "name")
        vac_flag = fold(val(r, "vacancy")) in ("1", "ha", "да", "yes", "true", "+", "x")
        vacancy = vac_flag or _is_vacancy_name(person_name)
        doc["people"].append(_person(
            key=key, name="" if vacancy else person_name, role=_role(val(r, "role")), position=val(r, "position"),
            territory=val(r, "territory"), region=val(r, "region"), city=val(r, "city"), phone=val(r, "phone"),
            email=val(r, "email"), telegram=val(r, "telegram"), note=val(r, "note"), vacancy=vacancy, unit=ukey,
            manager=val(r, "manager").removesuffix(".0"), _manager_name=val(r, "manager_name")))
    for doc in projects.values():
        _resolve_manager_names(doc)
    return projects


def _resolve_manager_names(doc):
    """"Rahbar" ustunida F.I.Sh. yoki hudud kodi yozilgan bo'lsa — key ga aylantiramiz."""
    keys = {p["key"] for p in doc["people"]}
    by_name = {fold(p["name"]): p["key"] for p in doc["people"] if p["name"]}
    by_terr = {fold(p["territory"]): p["key"] for p in doc["people"] if p["territory"]}
    for p in doc["people"]:
        ref = p.pop("_manager_name", "")
        if p["manager"] and p["manager"] not in keys:
            ref, p["manager"] = ref or p["manager"], ""
        if not p["manager"] and ref:
            p["manager"] = by_name.get(fold(ref)) or by_terr.get(fold(ref)) or ""
        if p["manager"] == p["key"]:
            p["manager"] = ""


def _xlsx_rows(content):
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb["Xodimlar"] if "Xodimlar" in wb.sheetnames else wb.worksheets[0]
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _csv_rows(text):
    sample = text[:4000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect))


# ------------------------------------------------------------------ manbani tanish
def parse(content, filename="", name="", source_url=""):
    """Bayt yoki matn -> {loyiha nomi: umumiy format}. Format o'zi aniqlanadi."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    if not content:
        raise StaffImportError("Ma'lumot bo'sh.")
    if content[:2] == b"PK":
        return from_rows(_xlsx_rows(content), name, source_url)
    text = content.decode("utf-8-sig", errors="replace").strip()
    if text[:1] in "{[":
        try:
            data = json.loads(text)
        except ValueError as e:
            raise StaffImportError(f"JSON xato: {e}") from None
        return _from_json(data, name, source_url)
    if "const DATA" in text or "<html" in text[:2000].lower() or "<!doctype" in text[:200].lower():
        data = _grab_json(text, "DATA")
        if not data:
            plain = _html_text(text)
            if staff_text.looks_like(plain):
                return staff_text.from_text(plain, name or _title_name(text), source_url)
            raise StaffImportError("Sahifada jamoa ma'lumoti topilmadi.")
        doc = from_artifact(data, _grab_json(text, "ROP"), _grab_json(text, "BR"),
                            name or _title_name(text), source_url)
        if not doc["project"]["name"]:
            raise StaffImportError("Loyiha nomini kiriting.")
        return {doc["project"]["name"]: doc}
    if filename.lower().endswith((".csv", ".tsv", ".txt")) or "\n" in text:
        try:
            return from_rows(_csv_rows(text), name, source_url)
        except StaffImportError:
            if not staff_text.looks_like(text):
                raise
        # sahifadan nusxa olingan oddiy matn (Ctrl+A, Ctrl+C)
        return staff_text.from_text(text, name, source_url)
    raise StaffImportError("Format tanilmadi: link, HTML sahifa, JSON, Excel (.xlsx) yoki CSV bo'lishi kerak.")


def _html_text(page):
    """HTML -> ko'rinadigan matn (qatorlar bo'yicha)."""
    page = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|</(div|p|li|tr|h\d|section|article|td|th)>", "\n", page)
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    return "\n".join(ln.strip() for ln in text.split("\n") if ln.strip())


def _from_json(data, name, source_url):
    docs = data if isinstance(data, list) else [data]
    out = {}
    for d in docs:
        if not isinstance(d, dict):
            raise StaffImportError("JSON tuzilmasi tanilmadi.")
        if d.get("format") == FORMAT:
            doc = empty(name or (d.get("project") or {}).get("name") or "", source_url or (d.get("project") or {}).get("source_url") or "")
            doc["project"]["description"] = (d.get("project") or {}).get("description") or ""
            doc["units"] = [{"key": str(u.get("key") or slug(u.get("title"))), "title": str(u.get("title") or u.get("key") or "")}
                            for u in d.get("units") or []]
            doc["people"] = [_person(**{f: p.get(f, "" if f != "vacancy" else False) for f in FIELDS}, key=str(p.get("key") or i))
                             for i, p in enumerate(d.get("people") or [], start=1)]
            for p in doc["people"]:
                p["vacancy"] = bool(p["vacancy"]) or (not p["name"])
                p["role"] = _role(p["role"])
        elif "branches" in d:
            doc = from_artifact(d, d.get("rop"), None, name, source_url)
        else:
            raise StaffImportError("JSON tuzilmasi tanilmadi: \"zona-staff\" formati yoki jamoa DATA kerak.")
        if not doc["project"]["name"]:
            raise StaffImportError("Loyiha nomini kiriting.")
        out[doc["project"]["name"]] = doc
    return out


def fetch(url):
    """Linkdan yuklab olish. Google Sheets havolasi CSV eksportiga aylantiriladi."""
    url = (url or "").strip()
    if not re.match(r"^https?://", url, re.I):
        raise StaffImportError("Link http:// yoki https:// bilan boshlansin.")
    if re.match(r"^https?://(www\.)?claude\.ai/(artifact|public/artifacts)/", url, re.I):
        raise StaffImportError(
            "Claude artifact sahifasini server ocha olmaydi (u faqat brauzerda, Claude hisobi orqali ochiladi). "
            "Linkni oching, sahifa ichiga bir marta bosing, Ctrl+A va Ctrl+C bosing, so'ng matnni shu yerga joylang.")
    m = re.match(r"^https?://docs\.google\.com/spreadsheets/d/([\w-]+)", url)
    if m and "output=csv" not in url and "format=csv" not in url:
        gid = re.search(r"[#&?]gid=(\d+)", url)
        url = f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv" + (f"&gid={gid.group(1)}" if gid else "")
    req = urllib.request.Request(url, headers={"User-Agent": "zona-staff-import/1.0", "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 — faqat http(s), muharrir kiritadi
            content = resp.read(MAX_BYTES + 1)
            ctype = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raise StaffImportError(f"Link ochilmadi: HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise StaffImportError(f"Link ochilmadi: {getattr(e, 'reason', e)}") from None
    if len(content) > MAX_BYTES:
        raise StaffImportError("Fayl juda katta (5 MB dan oshiq).")
    return content, ("data.csv" if "csv" in ctype else "")


# ------------------------------------------------------------------ bazadagi holat
def snapshot(project):
    """Bazadagi loyiha -> umumiy format (key = xodim id)."""
    units = {u.id: u.key for u in project.units.all()}
    doc = empty(project.name, project.source_url)
    doc["project"]["description"] = project.description
    doc["units"] = [{"key": u.key, "title": u.title} for u in project.units.all()]
    for p in project.people.all():
        doc["people"].append(_person(
            key=str(p.id), name=p.name, role=p.role, position=p.position, territory=p.territory, region=p.region,
            city=p.city, phone=p.phone, email=p.email, telegram=p.telegram, note=p.note, vacancy=p.is_vacancy,
            unit=units.get(p.unit_id, ""), manager=str(p.manager_id or "")))
    return doc


def _match(old_people, new_people):
    """[(eski, yangi)] juftliklari + qo'shilgan / o'chirilganlar. Avval hudud kodi, keyin F.I.Sh. bo'yicha."""
    pairs, used_old, used_new = [], set(), set()
    oc = Counter(fold(p["territory"]) for p in old_people if p["territory"])
    nc = Counter(fold(p["territory"]) for p in new_people if p["territory"])
    old_by_terr = {fold(p["territory"]): i for i, p in enumerate(old_people) if p["territory"] and oc[fold(p["territory"])] == 1}
    for j, p in enumerate(new_people):
        t = fold(p["territory"])
        if t and nc[t] == 1 and t in old_by_terr:
            pairs.append((old_by_terr[t], j))
            used_old.add(old_by_terr[t])
            used_new.add(j)
    old_by_name = {}
    for i, p in enumerate(old_people):
        if i not in used_old and p["name"]:
            old_by_name.setdefault(fold(p["name"]), i)
    for j, p in enumerate(new_people):
        i = old_by_name.get(fold(p["name"])) if j not in used_new and p["name"] else None
        if i is not None and i not in used_old:
            pairs.append((i, j))
            used_old.add(i)
            used_new.add(j)
    # bir xil hudud kodi bir necha marta (masalan "Merch КА-Tsh"): tartib bo'yicha juftlash
    rest_old = [i for i in range(len(old_people)) if i not in used_old]
    for j, p in enumerate(new_people):
        if j in used_new or not p["territory"]:
            continue
        i = next((i for i in rest_old if fold(old_people[i]["territory"]) == fold(p["territory"])), None)
        if i is not None:
            rest_old.remove(i)
            pairs.append((i, j))
            used_old.add(i)
            used_new.add(j)
    added = [j for j in range(len(new_people)) if j not in used_new]
    removed = [i for i in range(len(old_people)) if i not in used_old]
    return pairs, added, removed


def _label(p):
    return {"name": p["name"], "territory": p["territory"], "role": p["role"], "vacancy": p["vacancy"]}


def diff(project, doc):
    """Import qilinsa nima o'zgaradi: preview uchun."""
    old = snapshot(project) if project else empty()
    o, n = old["people"], doc["people"]
    pairs, added, removed = _match(o, n)
    old_key_to_i = {p["key"]: i for i, p in enumerate(o)}
    new_key_to_j = {p["key"]: j for j, p in enumerate(n)}
    pair_of_old = {i: j for i, j in pairs}
    units_new = {u["key"]: u["title"] for u in doc["units"]}
    units_old = {u["key"]: u["title"] for u in old["units"]}
    replaced, changed, same = [], [], 0
    keep = set(doc.get("keep_empty") or [])
    for i, j in pairs:
        a, b = o[i], n[j]
        diffs = []
        for f in ("role", "position", "territory", "region", "city", "phone", "email", "telegram", "note"):
            if (a[f] or "") != (b[f] or "") and not ((f in ("note", "telegram") or f in keep) and not b[f]):
                diffs.append({"field": f, "from": a[f], "to": b[f]})
        if units_old.get(a["unit"], a["unit"]) != units_new.get(b["unit"], b["unit"]):
            diffs.append({"field": "unit", "from": units_old.get(a["unit"], ""), "to": units_new.get(b["unit"], "")})
        old_mgr = pair_of_old.get(old_key_to_i.get(a["manager"])) if a["manager"] else None
        new_mgr = new_key_to_j.get(b["manager"]) if b["manager"] else None
        if old_mgr != new_mgr:
            diffs.append({"field": "manager", "from": o[old_key_to_i[a["manager"]]]["name"] if a["manager"] in old_key_to_i else "",
                          "to": n[new_mgr]["name"] or n[new_mgr]["territory"] if new_mgr is not None else ""})
        if fold(a["name"]) != fold(b["name"]) or a["vacancy"] != b["vacancy"]:
            replaced.append({"territory": b["territory"] or a["territory"], "role": b["role"],
                             "from": a["name"], "to": b["name"], "changes": diffs})
        elif diffs:
            changed.append({**_label(b), "changes": diffs})
        else:
            same += 1
    return {
        "project": {"id": project.id if project else None, "name": doc["project"]["name"], "exists": bool(project),
                    "source_url": doc["project"]["source_url"]},
        "summary": {"total": len(n), "added": len(added), "removed": len(removed), "replaced": len(replaced),
                    "changed": len(changed), "same": same, "vacancies": sum(1 for p in n if p["vacancy"]),
                    "units": len(doc["units"])},
        "added": [_label(n[j]) for j in added],
        "removed": [_label(o[i]) for i in removed],
        "replaced": replaced,
        "changed": changed,
    }


@transaction.atomic
def apply(doc, project=None):
    """Umumiy formatni bazaga yozish: loyiha to'liq shu holatga keltiriladi. (loyiha, diff) qaytaradi."""
    info = doc["project"]
    if project is None:
        project = StaffProject.objects.filter(name__iexact=info["name"]).first()
    result = diff(project, doc)
    if project is None:
        last = StaffProject.objects.order_by("-order").values_list("order", flat=True).first() or 0
        project = StaffProject.objects.create(name=info["name"], description=info.get("description") or "", order=last + 1)
    if info.get("source_url"):
        project.source_url = info["source_url"]
    if info.get("description"):
        project.description = info["description"]
    project.synced_at = timezone.now()
    project.save()

    units = {}
    for n_, u in enumerate(doc["units"]):
        obj, _ = StaffUnit.objects.update_or_create(project=project, key=u["key"], defaults={"title": u["title"], "order": n_})
        units[u["key"]] = obj
    old = snapshot(project)
    existing = {p.id: p for p in project.people.all()}
    pairs, added, removed = _match(old["people"], doc["people"])
    objs = {}  # yangi key -> StaffPerson
    for i, j in pairs:
        objs[doc["people"][j]["key"]] = existing[int(old["people"][i]["key"])]
    for j in added:
        objs[doc["people"][j]["key"]] = StaffPerson(project=project)
    today = timezone.localdate()
    keep = set(doc.get("keep_empty") or [])
    for order, p in enumerate(doc["people"]):
        obj = objs[p["key"]]
        holder_changed = obj.pk is not None and (fold(obj.name) != fold(p["name"]) or obj.is_vacancy != p["vacancy"])
        if holder_changed:
            obj.remember_holder("import", today)
            obj.telegram, obj.since = "", (None if p["vacancy"] else today)
        if p["telegram"]:
            obj.telegram = p["telegram"]
        obj.name, obj.role, obj.territory = p["name"], p["role"], p["territory"]
        obj.city, obj.phone, obj.email = p["city"], p["phone"], p["email"]
        for f in ("position", "region"):
            if p[f] or f not in keep or obj.pk is None:
                setattr(obj, f, p[f])
        if p["note"] or obj.pk is None:
            obj.note = p["note"]
        obj.is_vacancy, obj.unit, obj.order = p["vacancy"], units.get(p["unit"]), order
        obj.manager = None
        obj.save()
    for p in doc["people"]:
        mgr = objs.get(p["manager"]) if p["manager"] else None
        if mgr is not None and mgr.pk != objs[p["key"]].pk:
            StaffPerson.objects.filter(pk=objs[p["key"]].pk).update(manager=mgr)
    StaffPerson.objects.filter(pk__in=[int(old["people"][i]["key"]) for i in removed]).delete()
    project.units.exclude(key__in=list(units)).delete()
    result["project"]["id"] = project.id
    return project, result


# ------------------------------------------------------------------ eksport
def export_json(projects):
    docs = [snapshot(p) for p in projects]
    return docs[0] if len(docs) == 1 else docs


def export_xlsx(projects):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Xodimlar"
    ws.append([h for _, h in COLUMNS])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3A5F")
    for project in projects:
        units = {u.id: u.title for u in project.units.all()}
        people = list(project.people.all())
        num = {p.id: n for n, p in enumerate(people, start=1)}
        names = {p.id: p.name or f"Vakansiya ({p.territory})" for p in people}
        for p in people:
            ws.append([num[p.id], project.name, units.get(p.unit_id, ""), p.role, p.position, p.name, p.territory,
                       p.region, p.city, p.phone, p.telegram, p.email, num.get(p.manager_id, ""), names.get(p.manager_id, ""),
                       "ha" if p.is_vacancy else "", p.note])
    widths = [6, 14, 24, 7, 12, 38, 22, 16, 18, 19, 18, 22, 10, 34, 10, 30]
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
