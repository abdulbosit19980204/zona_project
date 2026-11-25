"""Katalogga qo'shimcha IT qurilma turlari (2026-11-25): video kuzatuv va filialda bo'lishi mumkin bo'lgan boshqa IT vositalar.

Video kuzatuv turlari — faol (darhol ishlatiladi). Qolganlari — nofaol: boshqaruvchi tekshirib, katalogda yoqadi.
Migratsiya faqat YO'Q turlarni yaratadi (nomi bo'yicha, katta-kichik harfsiz) — mavjud turlar, ularning holati,
maydonlari va kiritilgan qurilmalarga tegilmaydi.
"""
from .specs import IP, MAC, YES_NO, f

VIDEO = "Videokuzatuv"

CAM_TYPE = f("cam_type", "Kamera turi", "Тип камеры", options=[
    "Gumbaz (dome)", "Silindr (bullet)", "Aylanuvchi (PTZ)", "Panoramik (fisheye)", "Kubik (ichki)"])
MEGAPIXEL = f("megapixel", "Sifati (megapiksel)", "Разрешение (мегапиксели)", options=["1 MP", "2 MP", "4 MP", "5 MP", "8 MP (4K)"])
PLACEMENT = f("placement", "O'rnatilgan joyi", "Место установки", options=["Ichkarida", "Tashqarida"])
NIGHT = f("night", "Tungi ko'rish (IK)", "Ночное видение (ИК)", options=YES_NO)
AUDIO = f("audio", "Mikrofon (ovoz)", "Микрофон (звук)", options=YES_NO)
POE = f("poe", "PoE (kabel orqali quvvat)", "PoE (питание по кабелю)", options=YES_NO)
VIEW = f("view", "Nimani ko'radi", "Что снимает", "text")
CHANNEL = f("channel", "Registratordagi kanal", "Канал на регистраторе", "text")
PORTS = f("ports_count", "Portlar soni", "Количество портов", options=["4", "5", "8", "16", "24", "48"])
STORAGE = f("storage", "Xotira", "Память", options=["32 GB", "64 GB", "128 GB", "256 GB", "512 GB"])
RAM_M = f("ram", "Operativ xotira (RAM)", "Оперативная память (ОЗУ)", options=["2 GB", "3 GB", "4 GB", "6 GB", "8 GB", "12 GB"])
CONN = f("connection", "Ulanish", "Подключение", options=["USB", "Tarmoq (LAN)", "Wi-Fi", "Bluetooth", "COM"])


def t(name, name_ru, group, description, description_ru, serial_hint, serial_hint_ru, brands, specs=(), active=False,
      extra_hint="", extra_hint_ru=""):
    return {"name": name, "name_ru": name_ru, "group": group, "description": description, "description_ru": description_ru,
            "serial_hint": serial_hint, "serial_hint_ru": serial_hint_ru, "extra_hint": extra_hint,
            "extra_hint_ru": extra_hint_ru, "brands": list(brands), "specs": [dict(x) for x in specs], "is_active": active}


LABEL = "Korpusdagi yorliqda (S/N)"
LABEL_RU = "На наклейке на корпусе (S/N)"

TYPES = [
    # ------------------------------------------------------------------ video kuzatuv — FAOL
    t("IP kamera (videokuzatuv)", "IP-камера видеонаблюдения", VIDEO,
      "Tarmoq kabeli yoki Wi-Fi orqali ulanadigan kuzatuv kamerasi (devorda yoki shiftda)",
      "Камера наблюдения, подключённая сетевым кабелем или по Wi-Fi (на стене или потолке)",
      "Kamera korpusidagi yorliqda (S/N) yoki registrator/ilova sozlamalarida",
      "На наклейке на корпусе камеры (S/N) или в настройках регистратора/приложения",
      ["Hikvision", "Dahua", "HiWatch", "Uniview", "EZVIZ", "Imou", "TP-Link", "Axis"],
      [CAM_TYPE, MEGAPIXEL, PLACEMENT, NIGHT, AUDIO, POE, VIEW, CHANNEL, IP, MAC], active=True,
      extra_hint="Qayerni ko'rishini yozing (kassa, kirish, ombor...)", extra_hint_ru="Укажите, что снимает (касса, вход, склад...)"),
    t("Analog (HD) kamera", "Аналоговая (HD) камера", VIDEO,
      "Koaksial kabel bilan videoregistratorga (DVR) ulanadigan kamera",
      "Камера, подключённая коаксиальным кабелем к видеорегистратору (DVR)",
      LABEL, LABEL_RU, ["Hikvision", "HiWatch", "Dahua", "Uniview"],
      [CAM_TYPE, MEGAPIXEL, PLACEMENT, NIGHT, VIEW, CHANNEL], active=True),
    t("Videoregistrator (NVR / DVR)", "Видеорегистратор (NVR / DVR)", VIDEO,
      "Kameralar yozuvini saqlaydigan qurilma (ichida qattiq disk bor)",
      "Устройство, которое записывает и хранит видео с камер (внутри жёсткий диск)",
      "Pastki qismidagi yorliqda (S/N) yoki menyu → Ma'lumot", "На наклейке снизу (S/N) или в меню → Информация",
      ["Hikvision", "Dahua", "HiWatch", "Uniview", "EZVIZ", "TP-Link"],
      [f("rec_kind", "Turi", "Тип", options=["NVR (IP kameralar)", "DVR (analog kameralar)", "Gibrid (XVR)"]),
       f("channels", "Kanallar soni", "Количество каналов", options=["4", "8", "16", "32", "64"]),
       f("cams_connected", "Ulangan kameralar soni", "Подключено камер", "number"),
       f("hdd", "Disk hajmi", "Объём диска", options=["Yo'q", "1 TB", "2 TB", "4 TB", "6 TB", "8 TB", "10 TB va ko'p"]),
       f("archive_days", "Arxiv necha kun saqlanadi", "Сколько дней хранится архив", "number"),
       f("remote", "Masofadan ko'rish", "Удалённый просмотр", options=["Hik-Connect", "DMSS (Dahua)", "EZVIZ", "Imou", "Yo'q"]),
       POE, IP, MAC], active=True),
    t("PoE switch / injektor (kameralar uchun)", "PoE-коммутатор / инжектор (для камер)", VIDEO,
      "Kameralarga tarmoq kabeli orqali internet va quvvat beradigan qurilma",
      "Устройство, которое подаёт камерам сеть и питание по сетевому кабелю",
      LABEL, LABEL_RU, ["Hikvision", "Dahua", "TP-Link", "Ubiquiti", "Mercusys"],
      [f("poe_kind", "Turi", "Тип", options=["PoE switch", "PoE injektor"]), PORTS,
       f("poe_budget", "PoE quvvati", "Мощность PoE", "number", unit="W")], active=True),
    t("Videokuzatuv monitori", "Монитор видеонаблюдения", VIDEO,
      "Kameralar tasviri doim ko'rsatiladigan ekran (kassa yoki rahbar xonasida)",
      "Экран, на котором постоянно показываются камеры (на кассе или у руководителя)",
      LABEL, LABEL_RU, ["Hikvision", "Dahua", "Samsung", "LG", "Philips", "AOC"],
      [f("diagonal", "Diagonal", "Диагональ", options=['19"', '22"', '24"', '27"', '32"', '43"'])], active=True),

    # ------------------------------------------------------------------ kompyuter va periferiya — nofaol
    t("Server", "Сервер", "Kompyuter",
      "Dasturlar, 1C yoki fayllar ishlaydigan doimiy yoqilgan kompyuter",
      "Постоянно включённый компьютер, на котором работают программы, 1С или файлы",
      "Korpus orqasidagi yoki yon tomonidagi yorliqda (S/N, Service Tag)",
      "На наклейке сзади или сбоку корпуса (S/N, Service Tag)",
      ["HPE", "Dell", "Lenovo", "Supermicro", "Huawei", "Yig'ma"],
      [f("form", "Ko'rinishi", "Форм-фактор", options=["Rack (shkafda)", "Tower (alohida)"]),
       f("cpu_model", "Protsessor", "Процессор", "text"),
       f("ram", "Operativ xotira (RAM)", "Оперативная память (ОЗУ)", options=["8 GB", "16 GB", "32 GB", "64 GB", "128 GB", "256 GB"]),
       f("disks", "Disklar", "Диски", "text"),
       f("os", "Operatsion tizim", "Операционная система", options=["Windows Server", "Linux", "VMware ESXi", "Proxmox"]),
       f("role", "Vazifasi", "Назначение", "text"), IP]),
    t("Tarmoq xotirasi (NAS)", "Сетевое хранилище (NAS)", "Kompyuter",
      "Fayllar va zaxira nusxalar saqlanadigan tarmoq qurilmasi", "Сетевое устройство для хранения файлов и резервных копий",
      LABEL, LABEL_RU, ["Synology", "QNAP", "WD", "TerraMaster", "Asustor"],
      [f("bays", "Disk o'rinlari", "Отсеков для дисков", options=["1", "2", "4", "6", "8"]),
       f("capacity", "Umumiy hajm", "Общий объём", options=["1 TB", "2 TB", "4 TB", "8 TB", "16 TB", "32 TB"]), IP]),
    t("Planshet", "Планшет", "Kompyuter",
      "Sensorli ekranli qurilma (agentlar, buyurtma yoki namoyish uchun)", "Устройство с сенсорным экраном (для агентов, заказов или показа)",
      "Sozlamalar → Telefon haqida (S/N) yoki orqa qopqoqda", "Настройки → О планшете (S/N) или на задней крышке",
      ["Samsung", "Lenovo", "Apple", "Xiaomi", "Huawei", "Honor"],
      [STORAGE, RAM_M, f("tablet_os", "Tizim", "Система", options=["Android", "iPadOS", "Windows"]),
       f("screen", "Ekran diagonali", "Диагональ экрана", options=['8"', '10.1"', '10.4"', '11"', '12.4"']),
       f("sim", "SIM-karta", "SIM-карта", options=YES_NO)]),
    t("Mini kompyuter / tonkiy klient", "Мини-ПК / тонкий клиент", "Kompyuter",
      "Kichik korpusli kompyuter (monitor orqasiga yoki stol ostiga o'rnatiladi)",
      "Компьютер в маленьком корпусе (крепится за монитором или под столом)",
      LABEL, LABEL_RU, ["Intel NUC", "HP", "Dell", "Lenovo", "Beelink"],
      [f("cpu_model", "Protsessor", "Процессор", "text"),
       f("ram", "Operativ xotira (RAM)", "Оперативная память (ОЗУ)", options=["4 GB", "8 GB", "16 GB", "32 GB"]),
       f("disk", "Disk hajmi", "Объём диска", options=["128 GB", "256 GB", "512 GB", "1 TB"]),
       f("os", "Operatsion tizim", "Операционная система", options=["Windows 10", "Windows 11", "Linux"]), IP]),
    t("Tashqi disk (HDD / SSD)", "Внешний диск (HDD / SSD)", "Periferiya",
      "USB orqali ulanadigan ko'chma disk (zaxira nusxa, fayllar)", "Переносной диск с подключением по USB (резервные копии, файлы)",
      LABEL, LABEL_RU, ["WD", "Seagate", "Transcend", "Samsung", "Toshiba", "Kingston"],
      [f("disk_type", "Disk turi", "Тип диска", options=["HDD", "SSD"]),
       f("disk", "Disk hajmi", "Объём диска", options=["500 GB", "1 TB", "2 TB", "4 TB", "5 TB"])]),
    t("Dok-stansiya / USB-hab", "Док-станция / USB-хаб", "Periferiya",
      "Noutbukka monitor, klaviatura va boshqalarni bitta kabel bilan ulaydigan qurilma",
      "Устройство для подключения монитора, клавиатуры и др. к ноутбуку одним кабелем",
      LABEL, LABEL_RU, ["Dell", "HP", "Lenovo", "Ugreen", "Baseus"], [CONN]),
    t("Elektron kalit (USB-token / ERI)", "USB-токен (ЭЦП)", "Periferiya",
      "Elektron raqamli imzo (ERI) saqlanadigan USB kalit — soliq, bank, EDO uchun",
      "USB-ключ с электронной цифровой подписью (ЭЦП) — для налоговой, банка, ЭДО",
      "Kalitning o'zida yozilgan raqam", "Номер, написанный на самом ключе",
      ["E-IMZO", "Rutoken", "JaCarta", "eToken"],
      [f("owner", "Kimning nomiga", "На чьё имя", "text"), f("valid_to", "Amal qilish muddati", "Срок действия", "text"),
       f("purpose", "Nima uchun", "Для чего", options=["Soliq", "Bank", "EDO (Didox / Faktura)", "Bojxona", "Boshqa"])]),
    t("Hujjat skaneri", "Сканер документов", "Printer",
      "Faqat skanerlaydigan qurilma (printersiz)", "Устройство только для сканирования (без печати)",
      LABEL, LABEL_RU, ["Canon", "Epson", "HP", "Fujitsu", "Kodak", "Avision"],
      [f("scan_kind", "Turi", "Тип", options=["Planshetli", "Oqimli (ADF)"]), CONN]),
    t("Plotter (keng formatli printer)", "Плоттер (широкоформатный принтер)", "Printer",
      "Katta formatdagi (A1, A0) chizma va bannerlarni chop etadigan printer",
      "Принтер для печати чертежей и баннеров большого формата (A1, A0)",
      LABEL, LABEL_RU, ["HP", "Canon", "Epson"],
      [f("format", "Format", "Формат", options=["A2", "A1", "A0"]), CONN, IP]),

    # ------------------------------------------------------------------ tarmoq — nofaol
    t("4G modem / mobil router", "4G-модем / мобильный роутер", "Tarmoq",
      "SIM-karta bilan internet beradigan qurilma (zaxira internet)", "Устройство, раздающее интернет через SIM-карту (резервный интернет)",
      "Qopqoq ostidagi yorliqda (S/N, IMEI)", "На наклейке под крышкой (S/N, IMEI)",
      ["Huawei", "ZTE", "TP-Link", "Tenda"],
      [f("operator", "Operator", "Оператор", options=["Beeline", "Ucell", "Mobiuz", "Uzmobile", "Humans"]),
       f("number", "SIM raqami", "Номер SIM", "text")]),
    t("Media konverter (optika)", "Медиаконвертер (оптика)", "Tarmoq",
      "Optik kabelni oddiy tarmoq kabeliga ulaydigan kichik qurilma", "Небольшое устройство, переводящее оптический кабель в обычный сетевой",
      LABEL, LABEL_RU, ["TP-Link", "D-Link", "Mercusys", "Netis"],
      [f("speed", "Port tezligi", "Скорость портов", options=["100 Mbit", "1 Gbit"])]),
    t("Firewall (tarmoq himoyasi)", "Межсетевой экран (Firewall)", "Tarmoq",
      "Internet va ichki tarmoq orasidagi himoya qurilmasi", "Устройство защиты между интернетом и внутренней сетью",
      LABEL, LABEL_RU, ["FortiGate", "MikroTik", "Cisco", "Sophos", "pfSense"], [IP]),
    t("Server / telekom shkafi", "Серверный / телекоммуникационный шкаф", "Tarmoq",
      "Router, switch, registrator o'rnatiladigan metall shkaf", "Металлический шкаф, где стоят роутер, свитч, регистратор",
      "Shkaf eshigi ichidagi yorliqda", "На наклейке внутри двери шкафа",
      ["Hyperline", "ЦМО", "Lande", "Yig'ma"],
      [f("units", "Hajmi (U)", "Размер (U)", options=["6U", "9U", "12U", "15U", "18U", "22U", "42U"]),
       f("mount", "O'rnatilishi", "Установка", options=["Devorda", "Polda"])]),
    t("Patch-panel", "Патч-панель", "Tarmoq",
      "Shkafdagi tarmoq kabellari ulanadigan panel", "Панель в шкафу, к которой подключены сетевые кабели",
      "Panel yon tomonida (odatda yo'q — bo'sh qoldiring)", "Сбоку панели (обычно нет — оставьте пустым)",
      ["Hyperline", "TP-Link", "Cabeus"], [PORTS]),

    # ------------------------------------------------------------------ elektr — nofaol
    t("Kuchlanish stabilizatori", "Стабилизатор напряжения", "Elektr",
      "Tok kuchlanishini tekislab, qurilmalarni himoya qiladigan qurilma", "Выравнивает напряжение в сети и защищает технику",
      LABEL, LABEL_RU, ["Resanta", "Ruself", "APC", "Энергия", "Powercom"],
      [f("power", "Quvvati", "Мощность", options=["500 VA", "1000 VA", "2000 VA", "3000 VA", "5000 VA", "10000 VA"])]),
    t("Tarmoq filtri / uzaytirgich", "Сетевой фильтр / удлинитель", "Elektr",
      "Bir nechta rozetkali uzaytirgich (himoyali)", "Удлинитель на несколько розеток (с защитой)",
      "Odatda yo'q — bo'sh qoldiring", "Обычно нет — оставьте пустым",
      ["APC", "Pilot", "Defender", "Buro"],
      [f("sockets", "Rozetkalar soni", "Количество розеток", options=["3", "4", "5", "6", "8"])]),
    t("Generator", "Генератор", "Elektr",
      "Tok o'chganda elektr beradigan benzin yoki dizel generator", "Бензиновый или дизельный генератор на случай отключения света",
      LABEL, LABEL_RU, ["Huter", "Fubag", "Honda", "Champion"],
      [f("power", "Quvvati", "Мощность", "number", unit="kW"),
       f("fuel", "Yoqilg'i", "Топливо", options=["Benzin", "Dizel", "Gaz"])]),

    # ------------------------------------------------------------------ aloqa — nofaol
    t("IP telefon", "IP-телефон", "Aloqa",
      "Internet (tarmoq kabeli) orqali ishlaydigan stol telefoni", "Настольный телефон, работающий через сеть (интернет)",
      "Telefon ostidagi yorliqda (S/N, MAC)", "На наклейке снизу телефона (S/N, MAC)",
      ["Yealink", "Grandstream", "Cisco", "Fanvil", "Panasonic"],
      [f("ext", "Ichki raqam", "Внутренний номер", "text"), POE, IP, MAC]),
    t("Stol telefoni (oddiy)", "Стационарный телефон", "Aloqa",
      "Oddiy simli yoki radio stol telefoni", "Обычный проводной или радиотелефон",
      "Telefon ostidagi yorliqda", "На наклейке снизу телефона",
      ["Panasonic", "Gigaset", "Texet", "Philips"],
      [f("number", "Telefon raqami", "Номер телефона", "text")]),
    t("Mini ATS", "Мини-АТС", "Aloqa",
      "Ofis ichidagi telefonlarni ulaydigan stansiya", "Станция, объединяющая телефоны в офисе",
      LABEL, LABEL_RU, ["Panasonic", "Yeastar", "Grandstream", "Asterisk"],
      [f("lines", "Liniyalar soni", "Количество линий", "number"), IP]),

    # ------------------------------------------------------------------ xavfsizlik — nofaol
    t("Video domofon", "Видеодомофон", "Xavfsizlik",
      "Eshik oldidagi kamerali qo'ng'iroq va ichkaridagi ekran", "Вызывная панель с камерой у двери и экран внутри",
      LABEL, LABEL_RU, ["Hikvision", "Dahua", "Commax", "Tantos"], [IP]),
    t("Turniket", "Турникет", "Xavfsizlik",
      "Kirishda odamlarni karta yoki yuz orqali o'tkazadigan to'siq", "Проходная с пропуском по карте или лицу",
      LABEL, LABEL_RU, ["PERCo", "Hikvision", "ZKTeco", "Oxgard"],
      [f("method", "Usul", "Способ", options=["Karta", "Yuz (FaceID)", "Barmoq izi", "QR-kod"]), IP]),

    # ------------------------------------------------------------------ savdo — nofaol
    t("Elektron tarozi (etiketka chop etadigan)", "Весы с печатью этикеток", "Savdo",
      "Mahsulotni tortib, narxli etiketka chiqaradigan tarozi", "Весы, которые взвешивают товар и печатают этикетку с ценой",
      LABEL, LABEL_RU, ["CAS", "Mettler Toledo", "DIGI", "Штрих", "Масса-К"],
      [f("max_kg", "Eng ko'p og'irlik", "Наибольший вес", options=["6 kg", "15 kg", "30 kg", "60 kg", "150 kg"]),
       f("label_print", "Etiketka chop etadi", "Печатает этикетки", options=YES_NO), CONN, IP]),
    t("Pul sanash mashinasi", "Счётчик банкнот", "Savdo",
      "Kupyuralarni sanaydigan va soxtasini aniqlaydigan qurilma", "Устройство для пересчёта купюр и проверки подлинности",
      LABEL, LABEL_RU, ["Magner", "Cassida", "DORS", "Glory", "Pro"],
      [f("detect", "Soxta pulni aniqlaydi", "Определяет подделки", options=YES_NO)]),
    t("Kassa yashigi (pul qutisi)", "Денежный ящик", "Savdo",
      "Chek printeri yoki kassaga ulanadigan pul qutisi", "Денежный ящик, подключаемый к чековому принтеру или кассе",
      "Odatda yo'q — bo'sh qoldiring", "Обычно нет — оставьте пустым", ["Атол", "Штрих", "Posiflex", "Mercury"], []),
    t("Mijoz displeyi", "Дисплей покупателя", "Savdo",
      "Kassada xaridorga narxni ko'rsatadigan kichik ekran", "Небольшой экран на кассе, показывающий покупателю цену",
      LABEL, LABEL_RU, ["Posiflex", "Атол", "Штрих", "Sunmi"], [CONN]),
    t("Narx tekshirish terminali (prays-cheker)", "Прайс-чекер", "Savdo",
      "Xaridor shtrix-kodni o'qitib, narxni ko'radigan terminal", "Терминал, где покупатель сканирует штрихкод и видит цену",
      LABEL, LABEL_RU, ["Sunmi", "Honeywell", "Атол", "Zebra"], [IP]),

    # ------------------------------------------------------------------ multimedia — nofaol
    t("Interaktiv panel / doska", "Интерактивная панель / доска", "Multimedia",
      "Sensorli katta ekran (o'quv, yig'ilish xonasi)", "Большой сенсорный экран (учебный, переговорный класс)",
      LABEL, LABEL_RU, ["Samsung", "LG", "Hikvision", "SMART", "Promethean"],
      [f("diagonal", "Diagonal", "Диагональ", options=['55"', '65"', '75"', '86"'])]),
    t("Videokonferensiya tizimi", "Система видеоконференцсвязи", "Multimedia",
      "Yig'ilish xonasidagi kamera, mikrofon va karnay to'plami", "Комплект камеры, микрофона и динамика в переговорной",
      LABEL, LABEL_RU, ["Logitech", "Poly", "Yealink", "Jabra"], [CONN]),
    t("Fotoapparat", "Фотоаппарат", "Multimedia",
      "Raqamli fotoapparat yoki videokamera", "Цифровой фотоаппарат или видеокамера",
      "Pastki qismida yoki batareya qopqog'i ostida", "Снизу или под крышкой батареи",
      ["Canon", "Nikon", "Sony", "Fujifilm"], []),
]

SPECS = {x["name"]: x["specs"] for x in TYPES}


def add_missing(DeviceType):
    """Faqat yo'q turlarni yaratadi (nomi bo'yicha). Qaytaradi: yaratilgan nomlar."""
    existing = {n.lower() for n in DeviceType.objects.values_list("name", flat=True)}
    order = (DeviceType.objects.order_by("-order").values_list("order", flat=True).first() or 0) + 1
    made = []
    for x in TYPES:
        if x["name"].lower() in existing:
            continue
        DeviceType.objects.create(order=order, **x)
        order += 1
        made.append(x["name"])
    return made
