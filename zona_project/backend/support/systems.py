"""Savol qaysi tizim haqida: ILOVA (muammo qayerda ko'rindi) va MANBA (xato qaysi tizimdan chiqdi), TOIFA.

Agentlar turli dasturlar bilan ishlaydi: Telegram'dagi PRBC mini-ilovasi, mobil ProTarget, 1C. Bir xil "aksiya
ishlamayapti" ProTarget'da ko'rinishi, lekin sababi 1C'da (aksiya 1C'da sozlanmagan) bo'lishi mumkin — javob ham,
mas'ul ham shunga qarab farq qiladi. Bu yerda — tez qoidalar (skrinshot matni, savol matni, tanilgan yozuv sarlavhasi);
aniqroq belgini AI tahlili qo'yadi (ai_review.label_questions), xodim panelda tuzatishi mumkin.
"""
import re

APPS = ("prbc", "protarget", "1c", "telegram", "other")
ORIGINS = ("1c", "prbc", "protarget", "telegram", "network", "user", "other")
CATEGORIES = ("client", "order", "promo", "payment", "product", "stock", "visit", "login", "route", "report", "sync",
              "network", "other")

APP_RX = {
    "prbc": re.compile(r"(?<!\w)(prbc|прбц|рвс\b|мини-приложени|mini.?app|savdo nuqtasi so.ro|so.rovni ochish|"
                       r"awaiting approval|outlet created in 1c|marshrutga qo.shildi|команды продаж|sotuv jamoa)", re.I),
    "protarget": re.compile(r"(pro.?target|протаргет|визиты|корзин|геотег|радиус активной зоны|active visit|"
                            r"inactive user account|торговая точка .{0,80}модерац|новая торговая точка|"
                            r"синхронизир|начать визит|tashrif|vizit)", re.I),
    "1c": re.compile(r"(1с:предприят|1c:enterprise|конфигураци|проведени[ея] документ|1[сc] (da|de|ga)\b|"
                     r"в 1[сc]\b|1[сc]['’]?da)", re.I),
    "telegram": re.compile(r"(telegram|телеграм)", re.I),
}
ORIGIN_RX = [
    ("1c", re.compile(r"(1[сc] не принял|1[сc]['’]?da allaqachon|allaqachon bor|уже есть в 1[сc]|"
                      r"данные контрагента не получены|контрагент.{0,40}(не найден|не получен)|"
                      r"остат|ostatka|qoldiq|склад|sklad|nonfood|dms\b|1[сc] (xato|ошибк))", re.I)),
    ("network", re.compile(r"(vpn|internet|интернет|связ[ьи] нет|нет связи|сервер (недоступ|vaqtincha)|"
                           r"server vaqtincha|timeout|тайм-аут|aloqa yo.q|uzildi)", re.I)),
    ("user", re.compile(r"(парол|parol|неверн(ый|ые) (логин|данные)|noto.g.ri kirit|не заполнен|"
                        r"to.ldirilmagan|обязательное поле|majburiy maydon)", re.I)),
]
CAT_RX = [
    ("promo", r"aksiya|акци|skidka|скидк|bonus|бонус|promo"),
    ("payment", r"perechisl|перечисл|безнал|нақд|naqd|to.lov|оплат|kassa|касс|chek|чек\b"),
    ("order", r"zakaz|заказ|buyurtma|корзин|savat"),
    ("client", r"klient|клиент|контрагент|торгов\w* точк|savdo nuqta|nuqta|outlet|stir|инн\b|magazin|магазин|do.kon"
               r"|(?<!\w)(тт|tt|т\.т\.?)(?!\w)|точк|tochk"),
    ("product", r"sku|tovar|товар|mahsulot|штрих|shtrix|артикул"),
    ("stock", r"ostatka|остат|qoldiq|склад|sklad"),
    ("visit", r"vizit|визит|tashrif|геотег|lokatsiya|локаци|joylashuv|координат"),
    ("login", r"kirish|login|логин|парол|parol|akkaunt|аккаунт|account|inactive|rol\b|роль"
              r"|доступ|dostup|ruxsat|рухсат|позывн|pozivn|позивн"),
    ("route", r"marshrut|маршрут"),
    ("report", r"hisobot|отчет|отчёт|plan\b|план\b|bajarilish"),
    ("sync", r"sinxron|синхрон|almashinuv|обмен"),
    ("network", r"vpn|internet|интернет|aloqa|связ"),
]
CAT_RX = [(k, re.compile(v, re.I)) for k, v in CAT_RX]

APP_LABEL = {"prbc": "PRBC", "protarget": "ProTarget", "1c": "1C", "telegram": "Telegram", "other": "Boshqa"}
ORIGIN_LABEL = {**APP_LABEL, "network": "Tarmoq / server", "user": "Foydalanuvchi xatosi"}


def _from_title(title):
    """Bilim bazasi sarlavhasi: "PRBC → 1C: ..." -> (prbc, 1c); "ProTarget: ..." -> (protarget, protarget)."""
    head = (title or "").split(":", 1)[0] if ":" in (title or "") else ""
    parts = [p.strip().lower() for p in re.split(r"→|->", head)]
    norm = {"prbc": "prbc", "protarget": "protarget", "1c": "1c", "1с": "1c", "telegram": "telegram"}
    sys_ = [norm[p] for p in parts if p in norm]
    if not sys_:
        return "", ""
    return sys_[0], sys_[-1]


def detect(text="", ocr="", entry_title=""):
    """-> {"app", "origin", "category", "conf"} (bo'sh — aniqlanmadi)."""
    blob = " ".join(x for x in (text, ocr) if x)
    app, origin = _from_title(entry_title)
    conf = 85 if app else 0
    if not app:
        hits = [k for k, rx in APP_RX.items() if rx.search(blob)]
        if hits:
            # skrinshot ilovasi matndan ustun: ProTarget menyusi ko'rinsa — ilova ProTarget
            app = next((k for k in ("protarget", "prbc", "1c", "telegram") if k in hits), hits[0])
            conf = 70 if len(hits) == 1 else 55
    for k, rx in ORIGIN_RX:
        if rx.search(blob):
            origin = k
            break
    if not origin and app:
        origin = app
    cat = next((k for k, rx in CAT_RX if rx.search(" ".join(x for x in (entry_title, text) if x) or blob)), "")
    if not cat:
        cat = next((k for k, rx in CAT_RX if rx.search(blob)), "")
    return {"app": app, "origin": origin, "category": cat, "conf": conf}


def apply(q, entry=None, save=False):
    """Qoidalar bo'yicha belgi — faqat AI yoki xodim belgilamagan bo'lsa (ularniki aniqroq)."""
    if q.labeled_by in ("ai", "staff"):
        return q
    r = detect(q.text or "", q.ocr_text or "", entry.title if entry is not None else "")
    q.app, q.origin, q.category = r["app"], r["origin"], r["category"]
    q.label_conf, q.labeled_by = r["conf"], "rule" if (r["app"] or r["category"]) else ""
    if save:
        from .models import Message
        Message.objects.filter(pk=q.pk).update(app=q.app, origin=q.origin, category=q.category, label_conf=q.label_conf,
                                               labeled_by=q.labeled_by)
    return q
