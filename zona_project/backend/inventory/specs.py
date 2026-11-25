"""Qurilma turlariga xos texnik xususiyatlar (ixtiyoriy maydonlar): RAM, disk, protsessor, diagonal...

Maydon ta'rifi: {key, label, label_ru, kind: select|text|number, options: [...], unit}.
Ta'riflar DeviceType.specs da (katalogdan tahrirlanadi), qiymatlar Item.specs da ({key: qiymat}).
"select" maydonida ro'yxatda yo'q qiymatni ham yozish mumkin — u keyin shu tur uchun takliflarga qo'shiladi.
"""


def f(key, label, label_ru, kind="select", options=None, unit=""):
    return {"key": key, "label": label, "label_ru": label_ru, "kind": kind, "options": list(options or []), "unit": unit}


YES_NO = ["Bor", "Yo'q"]
STATE = ["Yaxshi", "O'rtacha", "Yomon"]
SIZES = ["128 GB", "256 GB", "512 GB", "1 TB", "2 TB", "4 TB"]

CPU = f("cpu", "Protsessor", "Процессор", options=[
    "Intel Celeron", "Intel Pentium", "Intel Core i3", "Intel Core i5", "Intel Core i7", "Intel Core i9", "Intel Xeon",
    "AMD Athlon", "AMD Ryzen 3", "AMD Ryzen 5", "AMD Ryzen 7", "AMD Ryzen 9", "Apple M1", "Apple M2", "Apple M3"])
CPU_MODEL = f("cpu_model", "Protsessor modeli / avlodi", "Модель / поколение процессора", "text")
RAM = f("ram", "Operativ xotira (RAM)", "Оперативная память (ОЗУ)",
        options=["2 GB", "4 GB", "6 GB", "8 GB", "12 GB", "16 GB", "24 GB", "32 GB", "64 GB"])
RAM_TYPE = f("ram_type", "RAM turi", "Тип ОЗУ", options=["DDR3", "DDR4", "DDR5", "LPDDR4", "LPDDR5"])
DISK_TYPE = f("disk_type", "Disk turi", "Тип диска", options=["SSD", "NVMe SSD", "HDD", "SSD + HDD", "eMMC"])
DISK = f("disk", "Disk hajmi", "Объём диска", options=SIZES)
DISK2 = f("disk2", "Qo'shimcha disk", "Дополнительный диск",
          options=["HDD 500 GB", "HDD 1 TB", "HDD 2 TB", "SSD 256 GB", "SSD 512 GB", "SSD 1 TB"])
GPU = f("gpu", "Videokarta", "Видеокарта", options=["Integrallashgan", "NVIDIA GeForce", "AMD Radeon", "Intel Arc"])
OS = f("os", "Operatsion tizim", "Операционная система",
       options=["Windows 7", "Windows 8.1", "Windows 10", "Windows 11", "Windows Server", "Linux", "macOS", "Yo'q"])
OS_LIC = f("os_license", "Windows litsenziyasi", "Лицензия Windows", options=["Litsenziyali", "Litsenziyasiz", "Noma'lum"])
OFFICE = f("office", "MS Office", "MS Office",
           options=["Office 2013", "Office 2016", "Office 2019", "Office 2021", "Microsoft 365", "LibreOffice", "Yo'q"])
ANTIVIRUS = f("antivirus", "Antivirus", "Антивирус", options=["Kaspersky", "ESET NOD32", "Windows Defender", "Dr.Web", "Yo'q"])
HOSTNAME = f("hostname", "Kompyuter nomi (tarmoqda)", "Имя компьютера (в сети)", "text")
IP = f("ip", "IP manzil", "IP-адрес", "text")
MAC = f("mac", "MAC manzil", "MAC-адрес", "text")
CONNECT = f("connection", "Ulanish", "Подключение", options=["USB", "Tarmoq (LAN)", "Wi-Fi", "Bluetooth", "COM"])

PC = [CPU, CPU_MODEL, RAM, RAM_TYPE, DISK_TYPE, DISK, DISK2, GPU, OS, OS_LIC, OFFICE, ANTIVIRUS, HOSTNAME, IP, MAC]
SCREEN_LAPTOP = f("screen", "Ekran diagonali", "Диагональ экрана", options=['11.6"', '13.3"', '14"', '15.6"', '16"', '17.3"'])
SCREEN_AIO = f("screen", "Ekran diagonali", "Диагональ экрана", options=['21.5"', '23.8"', '27"'])
DIAGONAL = f("diagonal", "Diagonal", "Диагональ", options=['19"', '20"', '21.5"', '22"', '23.8"', '24"', '27"', '32"'])
RESOLUTION = f("resolution", "Ruxsat (sifat)", "Разрешение", options=["HD", "Full HD (1920×1080)", "2K", "4K"])

TEMPLATES = {
    "Stol kompyuteri (sistem blok)": PC,
    "Monoblok": PC[:2] + [SCREEN_AIO] + PC[2:],
    "Noutbuk": PC[:2] + [SCREEN_LAPTOP] + PC[2:] + [
        f("battery", "Batareya holati", "Состояние батареи", options=STATE),
        f("charger", "Zaryadlovchi", "Зарядное устройство", options=YES_NO)],
    "Monitor": [DIAGONAL, RESOLUTION,
                f("ports", "Ulanish portlari", "Порты подключения", options=["VGA", "HDMI", "DisplayPort", "VGA + HDMI", "HDMI + DisplayPort"])],
    "Klaviatura va sichqoncha": [f("kind", "Turi", "Тип", options=["Simli", "Simsiz"]), f("set", "Komplekt", "Комплект",
                                  options=["Klaviatura + sichqoncha", "Faqat klaviatura", "Faqat sichqoncha"])],
    "Veb-kamera": [RESOLUTION],
    "Printer": [f("print_type", "Chop etish turi", "Тип печати", options=["Lazer", "Siyohli", "Termo"]),
                f("color", "Rang", "Цвет", options=["Oq-qora", "Rangli"]),
                f("cartridge", "Kartrij modeli", "Модель картриджа", "text"), CONNECT, IP,
                f("duplex", "Ikki tomonlama chop etish", "Двусторонняя печать", options=YES_NO)],
    "MFU (printer + skaner + nusxa)": [f("print_type", "Chop etish turi", "Тип печати", options=["Lazer", "Siyohli"]),
                                       f("color", "Rang", "Цвет", options=["Oq-qora", "Rangli"]),
                                       f("cartridge", "Kartrij modeli", "Модель картриджа", "text"), CONNECT, IP,
                                       f("adf", "Avtomatik varaq uzatgich (ADF)", "Автоподатчик (ADF)", options=YES_NO)],
    "Etiketka / shtrix-kod printeri": [CONNECT, f("label_width", "Etiketka kengligi", "Ширина этикетки", "text", unit="mm")],
    "Chek printeri": [CONNECT, f("paper", "Qog'oz kengligi", "Ширина бумаги", options=["58 mm", "80 mm"])],
    "Router (internet qurilmasi)": [IP, f("wifi", "Wi-Fi", "Wi-Fi", options=YES_NO),
                                    f("speed", "Port tezligi", "Скорость портов", options=["100 Mbit", "1 Gbit", "2.5 Gbit", "10 Gbit"]),
                                    f("provider", "Provayder", "Провайдер", "text"), MAC],
    "Switch (kommutator)": [f("ports_count", "Portlar soni", "Количество портов", options=["5", "8", "16", "24", "48"]),
                            f("speed", "Port tezligi", "Скорость портов", options=["100 Mbit", "1 Gbit", "10 Gbit"]),
                            f("poe", "PoE", "PoE", options=YES_NO),
                            f("managed", "Boshqariladigan", "Управляемый", options=YES_NO), IP],
    "Wi-Fi qurilmasi (Access Point)": [IP, f("band", "Diapazon", "Диапазон", options=["2.4 GHz", "5 GHz", "2.4 + 5 GHz"]), MAC],
    "VPN qurilmasi (filial – bosh ofis)": [IP, f("provider", "Provayder", "Провайдер", "text")],
    "UPS (uzluksiz quvvat manbai)": [
        f("power", "Quvvati", "Мощность", options=["600 VA", "650 VA", "800 VA", "1000 VA", "1500 VA", "2000 VA", "3000 VA"]),
        f("battery", "Batareya holati", "Состояние батареи", options=STATE),
        f("connected", "Nimaga ulangan", "К чему подключён", "text")],
    "SKUD (eshik nazorati)": [IP, f("door", "Eshik", "Дверь", "text")],
    "Davomat terminali (FaceID / barmoq izi)": [IP, f("method", "Usul", "Способ", options=["Yuz (FaceID)", "Barmoq izi", "Karta", "Yuz + barmoq izi"])],
    "Korporativ mobil telefon": [f("storage", "Xotira", "Память", options=["32 GB", "64 GB", "128 GB", "256 GB", "512 GB"]),
                                 f("ram", "Operativ xotira (RAM)", "Оперативная память (ОЗУ)", options=["2 GB", "3 GB", "4 GB", "6 GB", "8 GB", "12 GB"]),
                                 f("phone_os", "Tizim", "Система", options=["Android", "iOS"]),
                                 f("imei2", "IMEI 2", "IMEI 2", "text"),
                                 f("number", "Telefon raqami", "Номер телефона", "text")],
    "Korporativ SIM-karta": [f("tariff", "Tarif", "Тариф", "text"), f("device", "Qaysi qurilmada", "В каком устройстве", "text")],
    "Ratsiya": [f("range", "Masofa", "Дальность", "text", unit="km")],
    "POS-terminal / kassa kompyuteri": [f("pos_os", "Tizim", "Система", options=["Android", "Windows"]), RAM, DISK, IP],
    "Onlayn kassa / fiskal modul": [f("fm_number", "Fiskal modul raqami", "Номер фискального модуля", "text")],
    "Bank to'lov terminali": [f("bank", "Bank", "Банк", "text"), f("terminal_id", "Terminal ID", "ID терминала", "text"), CONNECT],
    "Shtrix-kod skaneri": [f("kind", "Turi", "Тип", options=["Simli", "Simsiz"]), f("code", "O'qiydi", "Считывает", options=["1D", "2D (QR)"])],
    "TSD (ombor terminali)": [f("tsd_os", "Tizim", "Система", options=["Android", "Windows CE / Mobile"]),
                              f("battery", "Batareya holati", "Состояние батареи", options=STATE)],
    "Proyektor": [RESOLUTION, f("lumen", "Yorqinlik", "Яркость", "text", unit="lm")],
    "Televizor / displey": [f("diagonal", "Diagonal", "Диагональ", options=['32"', '43"', '50"', '55"', '65"', '75"']),
                            RESOLUTION, f("smart", "Smart TV", "Smart TV", options=YES_NO)],
}


def default_specs(type_name):
    from .catalog_extra import SPECS
    return [dict(x) for x in TEMPLATES.get(type_name) or SPECS.get(type_name, [])]


def summary(specs_def, values, limit=None):
    """'Intel Core i5 · 8 GB · SSD · 256 GB' — ta'rif tartibida, bo'sh bo'lmaganlari."""
    out = []
    for d in specs_def or []:
        v = str((values or {}).get(d.get("key"), "") or "").strip()
        if v:
            out.append(f"{v} {d.get('unit')}".strip() if d.get("unit") else v)
    return " · ".join(out[:limit] if limit else out)


def labeled(specs_def, values):
    """'Protsessor: Intel Core i5; RAM: 8 GB' — eksport va tarix uchun."""
    parts = []
    for d in specs_def or []:
        v = str((values or {}).get(d.get("key"), "") or "").strip()
        if v:
            parts.append(f"{d.get('label')}: {v}{(' ' + d['unit']) if d.get('unit') else ''}")
    return "; ".join(parts)


def clean_defs(raw):
    """Katalogdan kelgan maydon ta'riflarini tekshiradi (boshqaruvchi tahrirlaydi)."""
    import re
    out, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()[:60]
        if not label:
            continue
        key = re.sub(r"[^a-z0-9_]", "", str(item.get("key") or "").lower())[:30]
        if not key:
            key = re.sub(r"[^a-z0-9]+", "_", label.lower().replace("'", "")).strip("_")[:30] or "field"
        base, n = key, 2
        while key in seen:
            key, n = f"{base}_{n}", n + 1
        seen.add(key)
        kind = item.get("kind") if item.get("kind") in ("select", "text", "number") else "select"
        opts = item.get("options") or []
        if isinstance(opts, str):
            opts = opts.split(",")
        options = []
        for o in opts:
            o = str(o).strip()[:60]
            if o and o not in options:
                options.append(o)
        out.append({"key": key, "label": label, "label_ru": str(item.get("label_ru") or "").strip()[:60], "kind": kind,
                    "options": options[:60] if kind == "select" else [], "unit": str(item.get("unit") or "").strip()[:12]})
    return out[:40]
