"""Mijoz (savdo nuqtasi) arizasining PRBC'dagi jonli holati — bot savolga shu bo'yicha javob beradi.

Agent savolida yoki skrinshotida STIR (9 raqam), JShShIR (14 raqam) yoki 1C kodi (UZ-00069292) bo'lsa, PRBC
Integratsiyalar → Savdo nuqtalari ro'yxatidan shu mijozning arizasi o'qiladi (faqat GET) va holati PRBC qo'llanmasi
(12.5 «So'rov holatlari», 12.12 «mavjud mijoz», 12.18 «1C natijasi») bo'yicha tushuntiriladi: ariza qayerda turibdi,
nuqta marshrutga tushdimi, ProTarget'ga yetdimi, bo'linma to'g'rimi va kim nima qilishi kerak.

Shaxsiy ma'lumot (telefonlar, aloqa shaxsi, koordinata) javobga qo'shilmaydi. PRBC'ga hech narsa yozilmaydi."""
import logging
import re
import threading
import time
from datetime import datetime

from .client import Client, PrbcError, items_of

log = logging.getLogger("prbc")

TTL = 120          # bir xil STIR qisqa vaqtda qayta so'ralsa — kesh (guruhda bir necha kishi so'raydi)
TIMEOUT = 8        # guruhdagi odam kutyapti: PRBC javob bermasa — jonli holatsiz davom etiladi
MAX_IDS = 3
MAX_ROWS = 3

_cache: dict = {}
_lock = threading.Lock()

# ------------------------------------------------------------------ identifikatorlar
_INN = re.compile(r"(?<![\d+])(\d{3})[ \-]?(\d{3})[ \-]?(\d{3})(?![\d])")
_PINFL = re.compile(r"(?<![\d+])(\d{14})(?![\d])")
_CODE = re.compile(r"(?<![\w])(?:UZ|УЗ)[ \-]?(\d{4,8})(?![\d])", re.I)
_PHONE_BEFORE = re.compile(r"(\+?998|tel|тел|phone|nomer|номер)[\s:.\-]*$", re.I)
_MONEY_AFTER = re.compile(r"^\s*(so.?m|сум|sum|uzs)", re.I)


def find_ids(text):
    """Matndan STIR / JShShIR / 1C kodlari (tartib bilan, takrorsiz). Telefon va summa raqamlari olinmaydi."""
    text = text or ""
    out = []

    def add(v):
        if v not in out:
            out.append(v)

    for m in _CODE.finditer(text):
        add("UZ-" + m.group(1).zfill(8))
    for m in _PINFL.finditer(text):
        add(m.group(1))
    for m in _INN.finditer(text):
        before, after = text[max(0, m.start() - 12):m.start()], text[m.end():m.end() + 6]
        if _PHONE_BEFORE.search(before) or _MONEY_AFTER.match(after):
            continue
        add("".join(m.groups()))
    return out[:MAX_IDS]


def _match(row, ident):
    vals = {str(row.get(k) or "").strip().upper() for k in ("inn", "pinfl", "dms_outlet_code", "dms_client_code",
                                                              "dms_counterparty_code")}
    return ident.upper() in vals


# ------------------------------------------------------------------ PRBC'dan o'qish
def connection():
    from .models import Connection
    c = Connection.objects.filter(pk=1).first()
    if not c or not c.enabled or not c.phone or not c.password_enc or not getattr(c, "outlet_lookup", True):
        return None
    return c


def lookup(ids, client=None):
    """{id: {"requests": [...], "attachments": [...]}} — faqat aniq mos kelgan arizalar (yangisi birinchi)."""
    out, todo = {}, []
    now = time.time()
    with _lock:
        for i in ids:
            hit = _cache.get(i)
            if hit and now - hit[0] < TTL:
                out[i] = hit[1]
            else:
                todo.append(i)
    if not todo:
        return out
    if client is None:
        conn = connection()
        if conn is None:
            return out
        client = Client(conn)
        client.timeout = TIMEOUT
    for i in todo:
        res = {"requests": [], "attachments": []}
        try:
            data = client.get("/integrations/outlet-requests/", {"q": i, "page_size": 10, "ordering": "-updated_at"})
            res["requests"] = [r for r in items_of(data) if _match(r, i)]
            if i.isdigit():
                key = "pinfl" if len(i) == 14 else "inn"
                data = client.get("/integrations/route-attachments/", {key: i, "page_size": 5})
                res["attachments"] = sorted(items_of(data), key=lambda r: r.get("updated_at") or "", reverse=True)
        except PrbcError as e:
            log.warning("PRBC mijoz holati (%s): %s", i, e)
            continue  # keshlanmaydi — keyingi savolda qayta urinadi
        with _lock:
            _cache[i] = (time.time(), res)
        out[i] = res
    return out


# ------------------------------------------------------------------ matnlar
def _t(lang, uz, ru):
    return ru if lang == "ru" else uz


STATUS = {
    "draft": ("⚪", "Qoralama", "Черновик"),
    "pending_review": ("🟡", "Tekshiruv kutilmoqda", "Ожидает проверки"),
    "queued": ("🟡", "1C navbatida", "В очереди 1С"),
    "sending": ("🟡", "1C ga yuborilmoqda", "Отправляется в 1С"),
    "retry": ("🟡", "Qayta urinish", "Повторная попытка"),
    "sent": ("🟢", "1C da yaratildi", "Создана в 1С"),
    "duplicate": ("🟢", "1C da allaqachon bor", "Уже есть в 1С"),
    "failed": ("🔴", "1C rad etdi", "1С отклонила"),
    "rejected": ("🔴", "Tekshiruvchi rad etdi", "Отклонена проверяющим"),
    "cancelled": ("⚪", "Bekor qilindi", "Отменена"),
}
STATUS_NOTE = {
    "draft": ("Ariza hali yuborilmagan. PRBC → Savdo nuqtalari → arizani ochib «Tekshiruvga yuborish»ni bosing.",
              "Заявка ещё не отправлена. PRBC → Торговые точки → откройте заявку и нажмите «Отправить на проверку»."),
    "pending_review": ("Ariza moderator (tekshiruvchi) tasdig'ini kutyapti — tasdiqlangach 1C ga o'zi ketadi. Kutib turing.",
                       "Заявка ждёт подтверждения модератора (проверяющего) — после подтверждения сама уйдёт в 1С. Подождите."),
    "queued": ("Ariza tasdiqlangan, 1C ga yuborish navbatida — odatda bir daqiqada ketadi. Kutib turing.",
               "Заявка подтверждена и стоит в очереди в 1С — обычно уходит в течение минуты. Подождите."),
    "sending": ("Tizim 1C bilan bog'lanyapti — sizdan hech narsa talab qilinmaydi.",
                "Система связывается с 1С — от вас ничего не требуется."),
    "retry": ("1C javob bermadi — tizim o'zi qayta urinadi (pauza 30 soniyadan 1 soatgacha). Sizdan hech narsa talab qilinmaydi.",
              "1С не ответила — система сама повторит попытку (пауза от 30 секунд до 1 часа). От вас ничего не требуется."),
    "rejected": ("Tekshiruvchi arizani rad etdi. Kerak bo'lsa, nuqtada turib yangi ariza yarating.",
                 "Проверяющий отклонил заявку. Если нужно — создайте новую заявку, находясь в точке."),
    "cancelled": ("Ariza bekor qilingan. Kerak bo'lsa, yangi ariza yarating.",
                  "Заявка отменена. Если нужно — создайте новую заявку."),
    "duplicate": ("1C bu nuqtani avvaldan biladi — yangi nuqta yaratilmadi, mavjud nuqta ishlatiladi. Marshrutingizda "
                  "bo'lmasa: formada STIR kiriting → «1C dagi mavjud nuqtalar» ro'yxatidan belgilang → «Marshrutimga qo'shish».",
                  "1С уже знает эту точку — новая не создана, используется существующая. Если её нет в вашем маршруте: "
                  "введите ИНН в форме → отметьте точку в списке «существующих точек в 1С» → «Добавить в мой маршрут»."),
}
ROUTE = {
    "in_route": ("🟢", "Marshrutda", "В маршруте",
                 "nuqta savdo vakilining amaldagi marshrutida, tashrif kunlari bilan.",
                 "точка в действующем маршруте торгового представителя, с днями визита."),
    "no_days": ("🟡", "Kunlarsiz", "Без дней визита",
                "marshrutda bor, lekin tashrif kunlari belgilanmagan — kunlik rejaga tushmaydi. Moderator «Marshrut nazorati»da kunlarni qo'yadi.",
                "точка в маршруте, но дни визита не указаны — в план на день не попадёт. Модератор ставит дни в «Контроле маршрутов»."),
    "not_active": ("🔴", "Hujjat faol emas", "Документ не активен",
                   "nuqta marshrut hujjatida, lekin hujjat o'tkazilmagan yoki muddati tugagan — 1C operatori hujjatni o'tkazadi, "
                   "muddati tugagan bo'lsa moderator «Marshrut muddatlari»da uzaytiradi.",
                   "точка в документе маршрута, но документ не проведён или истёк — оператор 1С проводит документ, "
                   "если истёк — модератор продлевает его в «Сроках маршрутов»."),
    "not_in_route": ("🔴", "Marshrutda yo'q", "Нет в маршруте",
                     "nuqta yaratildi, lekin vakil marshrutida yo'q — moderator «Marshrut nazorati» orqali qaytaradi.",
                     "точка создана, но её нет в маршруте представителя — модератор возвращает её через «Контроль маршрутов»."),
    "other_route": ("🟡", "Boshqa agentda", "У другого агента",
                    "nuqta faqat boshqa savdo vakili marshrutida (supervayzer ko'chirgan bo'lishi mumkin) — supervayzeringizga yozing.",
                    "точка только в маршруте другого представителя (мог перенести супервайзер) — напишите своему супервайзеру."),
    "inactive": ("⚪", "1C'da yopilgan", "Закрыта в 1С",
                 "nuqta 1C'da yopilgan yoki o'chirishga belgilangan.",
                 "точка закрыта или помечена на удаление в 1С."),
}
PROTARGET = {
    "sent": ("🟢", "Yuborildi", "Отправлена",
             "ProTarget nuqtani xatosiz qabul qildi.", "ProTarget принял точку без ошибок."),
    "incomplete": ("🟡", "Qisman", "Частично",
                   "nuqta ProTarget'ga ketdi, lekin turi, shartnomasi yoki «Протаргет» jadvalida kamchilik bor (1C tomoni). "
                   "Odatda nuqta ilovada chiqadi; hali ko'rinmasa — moderatsiya va sinxronlashni kuting: avtomatik 5–10 daqiqa, "
                   "qo'lda tasdiqlansa 1 soatgacha.",
                   "точка ушла в ProTarget, но есть замечания по типу, договору или таблице «Протаргет» (сторона 1С). "
                   "Обычно точка появляется в приложении; если ещё не видно — дождитесь модерации и синхронизации: "
                   "автоматически 5–10 минут, при ручном подтверждении до 1 часа."),
    "failed": ("🔴", "Xato", "Ошибка",
               "ProTarget nuqtani qabul qilmadi — 1C operatori nuqta kartasini qayta saqlashi kerak (shunda qayta yuboriladi).",
               "ProTarget не принял точку — оператору 1С нужно пересохранить карточку точки (тогда она уйдёт повторно)."),
}
SUBDIV = {
    "ok": ("🟢", "To'g'ri", "Верно", "", ""),
    "differs": ("🟡", "Boshqa bo'linma", "Другое подразделение",
                "nuqta boshqa bo'linma marshrutiga tushgan yoki kartada boshqa bo'linma — agent nuqtani ko'rmasligi mumkin; "
                "supervayzer yoki 1C operatori tekshiradi.",
                "точка попала в маршрут другого подразделения или в карточке другое подразделение — агент может её не видеть; "
                "проверяет супервайзер или оператор 1С."),
    "error": ("🔴", "Xato", "Ошибка",
              "1C bo'linmani bu savdo vakiliga tegishli emas deb rad etdi — arizada bo'linmani to'g'rilab qayta yuboring.",
              "1С отклонила подразделение как не относящееся к представителю — исправьте подразделение в заявке и отправьте заново."),
}
ATTACH = {
    "queued": ("🟡", "Navbatda", "В очереди"),
    "sending": ("🟡", "1C ga yuborilmoqda", "Отправляется в 1С"),
    "retry": ("🟡", "1C javob bermadi — tizim qayta urinyapti", "1С не ответила — система повторяет"),
    "sent": ("🟢", "1C dagi marshrutga qo'shildi", "Добавлено в маршрут в 1С"),
    "failed": ("🔴", "1C marshrutga qo'shmadi", "1С не добавила в маршрут"),
    "cancelled": ("⚪", "Bekor qilindi", "Отменено"),
}
# 1C rad etish sabablari (PRBC'dagi haqiqiy xatolar) — tushuntirish va kim nima qiladi
REASONS = [
    (re.compile(r"не относится к сотруднику", re.I),
     "tanlangan bo'linma bu savdo vakiliga tegishli emas",
     "выбранное подразделение не относится к этому торговому представителю",
     "Arizani ochib bo'linmani (savdo vakilining o'z bo'linmasini) to'g'rilab qayta yuboring; bo'linma to'g'ri bo'lsa — "
     "1C operatori vakil kartasini tekshiradi.",
     "Откройте заявку, исправьте подразделение (подразделение самого представителя) и отправьте заново; если "
     "подразделение верное — оператор 1С проверяет карточку представителя."),
    (re.compile(r"не принадлежит указанной организации", re.I),
     "bo'linma tanlangan tashkilotga tegishli emas",
     "подразделение не принадлежит указанной организации",
     "Arizada tashkilot va bo'linmani to'g'rilab qayta yuboring yoki moderatorga yozing.",
     "Исправьте организацию и подразделение в заявке и отправьте заново или напишите модератору."),
    (re.compile(r"REF_NOT_FOUND|Элемент не найден|нет в справочник", re.I),
     "1C ma'lumotnomasida element topilmadi (vakil, bo'linma yoki tashkilot 1C da o'zgargan)",
     "элемент не найден в справочнике 1С (представитель, подразделение или организация изменились в 1С)",
     "PRBC administratori ma'lumotnomalarni yangilaydi va vakil bog'lanishini tekshiradi, so'ng ariza qayta yuboriladi.",
     "Администратор PRBC обновляет справочники и проверяет привязку представителя, затем заявка отправляется заново."),
    (re.compile(r"База занята|HTTP 50[234]|не отвечает|timeout", re.I),
     "1C bazasi o'sha payt band yoki javob bermadi",
     "база 1С была занята или не ответила",
     "Tekshiruvchi «1C ga yuborish» (yoki «Qayta yuborish») bilan qayta jo'natadi.",
     "Проверяющий отправляет заново кнопкой «Отправить в 1С» (или «Отправить повторно»)."),
    (re.compile(r"Запрещено|Создание торговых точек", re.I),
     "1C da savdo vakiliga nuqta yaratish taqiqlangan («Создание торговых точек» = «Запрещено»)",
     "в 1С представителю запрещено создавать точки («Создание торговых точек» = «Запрещено»)",
     "1C operatori ruxsat beradi, so'ng PRBC ma'lumotnomalari yangilanadi va ariza qayta yuboriladi.",
     "Оператор 1С даёт разрешение, затем справочники PRBC обновляются и заявка отправляется заново."),
]


def _reason(row, lang):
    raw = (row.get("last_error") or "").replace("DMS refused:", "").strip()
    notes = row.get("outcome_notes") or {}
    if not raw and isinstance(notes, dict):
        raw = "; ".join(str(v) for v in notes.values() if v)
    for rx, uz, ru, fix_uz, fix_ru in REASONS:
        if rx.search(raw):
            return _t(lang, uz, ru), _t(lang, fix_uz, fix_ru), raw
    return "", _t(lang, "Arizani tahrirlab qayta yuboring; sabab tushunarsiz bo'lsa — moderatorga yozing.",
                  "Исправьте заявку и отправьте заново; если причина непонятна — напишите модератору."), raw


def _date(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).strftime("%d.%m %H:%M")
    except (TypeError, ValueError):
        return ""


def _notes(row):
    n = row.get("outcome_notes")
    return n if isinstance(n, dict) else {}


def describe_request(row, lang="uz"):
    st = row.get("status") or ""
    icon, uz, ru = STATUS.get(st, ("⚪", st, st))
    name = row.get("outlet_name") or row.get("counterparty_name") or row.get("dms_counterparty_name") or "—"
    ids = [x for x in (
        f"{_t(lang, 'STIR', 'ИНН')} {row['inn']}" if row.get("inn") else "",
        f"{_t(lang, 'JShShIR', 'ПИНФЛ')} {row['pinfl']}" if row.get("pinfl") else "",
        f"{_t(lang, '1C kodi', 'код 1С')} {row['dms_outlet_code']}" if row.get("dms_outlet_code") else "",
        (row.get("connection_code") or "").upper(),
    ) if x]
    lines = [f"🏪 «{name}»", " · ".join(ids)]
    who = " · ".join(x for x in (row.get("sales_rep_name"), row.get("territory_name")) if x)
    if who:
        lines.append(_t(lang, "Savdo vakili: ", "Представитель: ") + who)
    when = _date(row.get("sent_at") or row.get("updated_at") or row.get("created_at"))
    lines.append(f"{icon} {_t(lang, 'Ariza', 'Заявка')}: **{_t(lang, uz, ru)}**" + (f" ({when})" if when else ""))
    todo = []
    if st == "failed":
        why, fix, raw = _reason(row, lang)
        lines.append(_t(lang, "Sabab: ", "Причина: ") + (why or raw[:200] or "—") + (f"\n1C: {raw[:200]}" if why and raw else ""))
        todo.append(fix)
    elif st == "rejected" and row.get("review_comment"):
        lines.append(_t(lang, "Izoh: ", "Комментарий: ") + row["review_comment"][:200])
        todo.append(_t(lang, *STATUS_NOTE["rejected"]))
    elif st in STATUS_NOTE:
        todo.append(_t(lang, *STATUS_NOTE[st]))
    if st in ("sent", "duplicate"):
        notes = _notes(row)
        for key, table, label in (("route_state", ROUTE, _t(lang, "Marshrut", "Маршрут")),
                                  ("protarget_state", PROTARGET, "ProTarget"),
                                  ("subdivision_state", SUBDIV, _t(lang, "Bo'linma", "Подразделение"))):
            v = row.get(key)
            if v not in table:
                continue
            ic, l_uz, l_ru, n_uz, n_ru = table[v]
            extra = ""
            if key == "route_state" and notes.get("route"):
                extra = f" ({notes['route']})"
            lines.append(f"{ic} {label}: **{_t(lang, l_uz, l_ru)}**{extra}")
            note = _t(lang, n_uz, n_ru)
            if ic != "🟢" and note:
                todo.append(f"{label}: {note}")
            if key == "protarget_state" and v in ("incomplete", "failed") and notes.get("protarget"):
                lines.append(f"   1C: {str(notes['protarget'])[:180]}")
            if key == "subdivision_state" and v in ("differs", "error") and notes.get("subdivision"):
                lines.append(f"   1C: {str(notes['subdivision'])[:180]}")
        if st == "sent" and not todo:
            todo.append(_t(lang, "Hammasi joyida — nuqta 1C da yaratilgan, marshrutda va ProTarget'ga yuborilgan.",
                           "Всё в порядке — точка создана в 1С, в маршруте и отправлена в ProTarget."))
        if row.get("outcome_at"):
            lines.append(_t(lang, "1C natijasi olingan: ", "Результат 1С получен: ") + _date(row["outcome_at"]))
    return lines, todo


def describe_attachment(row, lang="uz"):
    st = row.get("status") or ""
    icon, uz, ru = ATTACH.get(st, ("⚪", st, st))
    doc = row.get("route_document_number") or ""
    n = len(row.get("outlets") or [])
    line = (f"{icon} {_t(lang, 'Mavjud nuqtalarni marshrutga qo‘shish', 'Добавление существующих точек в маршрут')}"
            f"{f' ({n})' if n else ''}: **{_t(lang, uz, ru)}**" + (f" — № {doc}" if doc else "")
            + (f" ({_date(row.get('updated_at'))})" if row.get("updated_at") else ""))
    out = [line]
    if st == "failed" and row.get("last_error"):
        out.append("   1C: " + str(row["last_error"])[:200])
    if st == "sent" and row.get("route_posting_pending"):
        out.append(_t(lang, "   Hujjat hali o'tkazilmagan — 1C operatori o'tkazgach nuqtalar ilovada ko'rinadi.",
                      "   Документ ещё не проведён — после проведения оператором 1С точки появятся в приложении."))
    return out


def card(found, lang="uz"):
    """lookup() natijasi -> bitta javob matni (yoki "" — hech narsa topilmadi)."""
    blocks, todos, more = [], [], 0
    for ident, res in found.items():
        reqs = res.get("requests") or []
        for row in reqs[:MAX_ROWS]:
            lines, todo = describe_request(row, lang)
            blocks.append("\n".join(lines))
            todos += [x for x in todo if x not in todos]
        more += max(0, len(reqs) - MAX_ROWS)
        att = (res.get("attachments") or [])[:1]
        if att:
            blocks.append("\n".join(describe_attachment(att[0], lang)))
    if not blocks:
        return ""
    head = _t(lang, "📋 PRBC'dagi holat (jonli tekshiruv):", "📋 Статус в PRBC (проверено сейчас):")
    text = head + "\n\n" + "\n\n".join(blocks)
    if more:
        text += "\n\n" + _t(lang, f"…yana {more} ta ariza bor (PRBC → Savdo nuqtalari).",
                            f"…есть ещё {more} заявк(и) (PRBC → Торговые точки).")
    if todos:
        text += "\n\n👉 " + _t(lang, "Nima qilish kerak:", "Что делать:") + "\n" + "\n".join(f"• {x}" for x in todos)
    return text


TRANSIENT = REASONS[3][0]  # 1C bazasi band / javob bermadi — qayta yuborish yordam beradi


def resend_failed(found, client=None, conn=None, lang="uz", dry=False):
    """«1C rad etdi» + vaqtinchalik sabab (baza band, javob yo'q) -> arizani qayta yuborish (amal «outlet_resend»).
    Ruxsat o'chiq bo'lsa — faqat «kerak» qatori (mutaxassis bajaradi). Qaytaradi: javobga qo'shiladigan qatorlar."""
    from .access import _log
    from .actions import allowed
    lines = []
    for ident, res in found.items():
        for row in res.get("requests") or []:
            if row.get("status") != "failed" or row.get("can_send") is False:
                continue
            if not TRANSIENT.search(row.get("last_error") or ""):
                continue
            name = row.get("outlet_name") or row.get("counterparty_name") or ident
            if dry or not allowed(conn, "outlet_resend"):
                lines.append(_t(lang, f"🧪 «{name}»: arizani 1C ga qayta yuborish kerak (avtomatik o'chiq — mutaxassis bajaradi)",
                                f"🧪 «{name}»: нужно отправить заявку в 1С повторно (автоматически выключено — сделает специалист)"))
                continue
            try:
                if client is None:
                    client = Client(conn)
                    client.timeout = TIMEOUT
                client.post(f"/integrations/outlet-requests/{row['id']}/send/")
                with _lock:
                    _cache.pop(ident, None)
                _log("bot", None, "outlet_resend", True, f"«{name}» (ariza #{row['id']}) 1C ga qayta yuborildi",
                     before={"status": "failed", "error": (row.get("last_error") or "")[:300]}, after={"sent": row["id"]})
                lines.append(_t(lang, f"🔧 «{name}»: ariza 1C ga qayta yuborildi — natija bir necha daqiqada.",
                                f"🔧 «{name}»: заявка повторно отправлена в 1С — результат через несколько минут."))
            except PrbcError as e:
                _log("bot", None, "outlet_resend", False, f"«{name}» (ariza #{row['id']}): {e}")
                lines.append(_t(lang, f"❌ «{name}»: qayta yuborib bo'lmadi — mutaxassis ko'radi.",
                                f"❌ «{name}»: не удалось отправить повторно — посмотрит специалист."))
        # «Marshrutimga qo'shish» so'rovi: 1C xato bergan + vaqtinchalik sabab -> qayta navbat (amal «route_resend»)
        for row in (res.get("attachments") or [])[:1]:
            acts = row.get("actions")
            if row.get("status") != "failed" or (isinstance(acts, list) and "requeue" not in acts):
                continue
            if not TRANSIENT.search(row.get("last_error") or ""):
                continue
            name = row.get("counterparty_name") or ident
            if dry or not allowed(conn, "route_resend"):
                lines.append(_t(lang, f"🧪 «{name}»: marshrutga qo'shish so'rovini qayta yuborish kerak (avtomatik o'chiq — "
                                      "mutaxassis bajaradi)",
                                f"🧪 «{name}»: нужно повторить добавление в маршрут (автоматически выключено — сделает специалист)"))
                continue
            try:
                if client is None:
                    client = Client(conn)
                    client.timeout = TIMEOUT
                client.post(f"/integrations/route-attachments/{row['id']}/requeue/")
                with _lock:
                    _cache.pop(ident, None)
                _log("bot", None, "route_resend", True, f"«{name}» (marshrut so'rovi #{row['id']}) qayta navbatga qo'yildi",
                     before={"status": "failed", "error": (row.get("last_error") or "")[:300]}, after={"requeued": row["id"]})
                lines.append(_t(lang, f"🔧 «{name}»: marshrutga qo'shish 1C ga qayta yuborildi — natija bir necha daqiqada.",
                                f"🔧 «{name}»: добавление в маршрут повторно отправлено в 1С — результат через несколько минут."))
            except PrbcError as e:
                _log("bot", None, "route_resend", False, f"«{name}» (marshrut so'rovi #{row['id']}): {e}")
                lines.append(_t(lang, f"❌ «{name}»: marshrut so'rovini qayta yuborib bo'lmadi — mutaxassis ko'radi.",
                                f"❌ «{name}»: не удалось повторить добавление в маршрут — посмотрит специалист."))
    return lines


def status_for(text, lang="uz", client=None):
    """Matn/skrinshot matnidan identifikator topib, PRBC holati kartasini qaytaradi ("" — yo'q yoki o'chiq)."""
    ids = find_ids(text)
    if not ids:
        return "", []
    found = lookup(ids, client=client)
    text_out = card(found, lang)
    if text_out:
        try:
            extra = resend_failed(found, client=client, conn=connection(), lang=lang)
        except Exception:  # noqa: BLE001 — qo'shimcha amal: xatosi holat kartasini to'xtatmasin
            log.exception("PRBC arizani qayta yuborish")
            extra = []
        if extra:
            text_out += "\n\n" + "\n".join(extra)
    return text_out, ids
