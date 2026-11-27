"""PRBC modul ruxsatlari: «PRBC'da vazifalar ko'rinmayapti», «PRBC chat ochilmayapti» — bot xodimning modul darajasini
tekshiradi. Ruxsat yo'q bo'lsa: amal yoqilgan bo'lsa — «A'zo» (member) beradi va javobda yozadi, o'chiq bo'lsa —
faqat aniqlaydi va mutaxassisga uzatadi. Ruxsati bor bo'lsa — aralashmaydi (oddiy javob).

Faqat PRBC tilga olingan savol (matn yoki skrinshotda «PRBC»): ProTarget ilovasida ham «Задачи» bor — u bilan
adashtirilmasin. Hech narsa pasaytirilmaydi (manager/admin darajasiga tegilmaydi). Har amal AccessLog'da, ortga qaytariladi."""
import logging
import re
from dataclasses import dataclass, field

from .access import _log, _t, find_target, fold, make_client, connection
from .actions import allowed
from .client import PrbcError, items_of

log = logging.getLogger("prbc")

MODULES = {
    "task": {"path": "task-access", "action": "task_seat", "name": ("«Vazifalar» moduli", "модуль «Задачи»")},
    "chat": {"path": "chat-access", "action": "chat_seat", "name": ("«Chat» moduli", "модуль «Чат»")},
}
HAS = ("member", "manager", "admin")
LEVEL = {"member": ("A'zo", "Участник"), "manager": ("Menejer", "Менеджер"), "admin": ("Administrator", "Администратор"),
         "none": ("yo'q", "нет")}

_PRBC = re.compile(r"прбк|прбц|\bпрб\b")
_TASK = re.compile(r"вазиф|задач|задани")
_CHAT = re.compile(r"\bчат|чатга|чатда")
_NEG = re.compile(r"коринм|курим|кур[иу]нм|очилм|очолм|кира олм|киролм|чикм|\bйук\b|\bйок\b|ишлам|не\s+вижу|не\s+вид|"
                  r"не\s+откр|не\s+показ|нет\s+доступ|не\s+доступ|недоступ|не\s+работ|пуст|пропал|нету")


def which(text, ocr=""):
    """Savol qaysi modul haqida: "task" / "chat" / "" (PRBC tilga olinmagan yoki muammo yozilmagan)."""
    f, o = fold(text), fold(ocr)
    if not (_PRBC.search(f) or _PRBC.search(o)) or not _NEG.search(f):
        return ""
    if _CHAT.search(f):
        return "chat"
    if _TASK.search(f):
        return "task"
    return ""


def roster(client, org, mod):
    r = client.get(f"/admin/organization-modules/{org}/{MODULES[mod]['path']}/")
    return {p["id"]: p.get("level") or "none" for p in (r or {}).get("members") or []}


def set_level(client, org, mod, uid, level):
    r = client.post(f"/admin/organization-modules/{org}/{MODULES[mod]['path']}/",
                    {"level": level, "user_ids": [uid], "include_subtree": False})
    return {p["id"]: p.get("level") or "none" for p in (r or {}).get("members") or []}.get(uid, "none")


@dataclass
class Result:
    kind: str
    text: str
    note: str = ""
    fixed: list = field(default_factory=list)
    planned: list = field(default_factory=list)


def _org(client):
    conns = items_of(client.get("/integrations/connections/"))
    return int(conns[0].get("organization") or 0) if conns else 0


def handle(text, ocr="", tg_id=None, username="", lang="uz", question=None, client=None, conn=None, dry=False,
           target=None, mod=None):
    """Modul ruxsati savoli -> Result yoki None (bu savol emas / ruxsati bor / PRBC javob bermadi)."""
    conn = conn or connection()
    if conn is None or not getattr(conn, "access_bot", True):
        return None
    mod = mod or which(text, ocr)
    if not mod:
        return None
    try:
        client = client or make_client(conn)
        users = items_of(client.get("/auth/admin/users/"))
        org = int(conn.organization or 0) or _org(client)
        levels = roster(client, org, mod)
    except PrbcError as e:
        log.warning("PRBC modul ruxsati: %s", e)
        return None

    class _St:
        pass
    st = _St()
    st.users = users
    u = next((x for x in users if x.get("id") == target), None) if target else find_target(st, tg_id, username, text)
    if u is None:
        return None
    cur = levels.get(u["id"], "none")
    if cur in HAS:
        return None  # ruxsati bor — muammo boshqa joyda, oddiy javob
    m = MODULES[mod]
    name = _t(lang, *m["name"])
    head = _t(lang, f"🔎 PRBC {name} ruxsatini tekshirdim — {u.get('full_name')}:",
              f"🔎 Проверил доступ к {name} в PRBC — {u.get('full_name')}:")
    lv = lambda v: _t(lang, *LEVEL.get(v, (v, v)))  # noqa: E731
    test = ["", _t(lang, "🧪 Sinov: PRBC'da hech narsa o'zgarmadi.", "🧪 Тест: в PRBC ничего не изменено.")] if dry else []
    if not dry and allowed(conn, m["action"]):
        try:
            got = set_level(client, org, mod, u["id"], "member")
            if got not in HAS:
                raise PrbcError("PRBC darajani o'zgartirmadi")
        except PrbcError as e:
            _log("bot", u, m["action"], False, f"{name}: {e}", question=question)
            body = "\n".join([head, f"❌ {lv(cur)} → {lv('member')} — " + _t(lang, "PRBC xato berdi", "ошибка PRBC"), "",
                              _t(lang, "IT mutaxassisi ko'rib chiqadi.", "Посмотрит IT-специалист.")])
            return Result("escalate", body, note=f"PRBC {mod} ruxsati: {e}"[:300])
        _log("bot", u, m["action"], True, f"{name}: {cur} → {got}", before={"level": cur}, after={"level": got, "module": mod},
             question=question, reversible=True)
        body = "\n".join([head, f"🔧 {lv(cur)} → {lv(got)} " + _t(lang, "(berildi)", "(выдан)"), "",
                          _t(lang, "👉 PRBC ilovasini yopib qayta oching.", "👉 Закройте и заново откройте приложение PRBC.")])
        return Result("answer", body, note=f"PRBC {mod} ruxsati berildi", fixed=[m["action"]])
    off = "" if dry and allowed(conn, m["action"]) else _t(lang, " (avtomatik o'zgartirish o'chiq — mutaxassis bajaradi)",
                                                           " (автоматическое изменение выключено — сделает специалист)")
    body = "\n".join([head, f"{'🧪' if dry and allowed(conn, m['action']) else '❌'} "
                      + _t(lang, f"ruxsat: {lv(cur)} — kerak: {lv('member')}", f"доступ: {lv(cur)} — нужно: {lv('member')}") + off,
                      "", _t(lang, "IT mutaxassisi ko'rib chiqadi.", "Посмотрит IT-специалист."), *test])
    if not dry:
        _log("bot", u, "escalate", False, f"{name}: ruxsat yo'q — kerak: member", question=question)
    return Result("escalate", body, note=f"PRBC {mod} ruxsati yo'q — kerak: member", planned=[(m["action"], f"{lv(cur)} → {lv('member')}")])


def revert(entry, client, org):
    """task_seat / chat_seat: avvalgi darajaga qaytarish."""
    mod = (entry.after or {}).get("module") or ("task" if entry.action == "task_seat" else "chat")
    before = (entry.before or {}).get("level") or "none"
    set_level(client, org, mod, entry.prbc_user, before)
    return f"{MODULES[mod]['name'][0]}: {(entry.after or {}).get('level')} → {before}"
