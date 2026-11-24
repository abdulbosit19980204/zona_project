"""IT inventarizatsiyasi: filiallardagi qurilmalarni telefondan rasm bilan ro'yxatga olish.

Jadvallar alohida (inventory_*): mavjud Zona/Support ma'lumotlariga tegilmaydi. Katalog (qurilma turlari, brendlar,
filiallar, tashkilotlar, joylar) "StarGroup_IT_inventarizatsiya_shablon.xlsx" dan olingan (data/catalog.json).
"""
import calendar
from datetime import date

from django.conf import settings
from django.db import models


def add_months(start, months):
    """Sanaga oy qo'shadi (31-yanvar + 1 oy = 28/29-fevral). Biri bo'sh bo'lsa — None."""
    if not start or not months:
        return None
    m = start.month - 1 + int(months)
    year, month = start.year + m // 12, m % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


class Org(models.Model):
    """Tashkilot / loyiha: STAR BEVERAGE, Star Distribution, STAR FMCG..."""

    name = models.CharField("Nomi", max_length=120, unique=True)
    code = models.CharField("Kodi", max_length=60, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Tashkilot"
        verbose_name_plural = "Tashkilotlar"

    def __str__(self):
        return self.name


class Branch(models.Model):
    PLANNED, ACTIVE, DONE = "planned", "active", "done"
    STATUSES = [(PLANNED, "Rejada"), (ACTIVE, "Jarayonda"), (DONE, "Yakunlandi")]

    code = models.CharField("Kod", max_length=12, unique=True)
    name = models.CharField("Filial", max_length=120, unique=True)
    region = models.CharField("Viloyat", max_length=120, blank=True)
    note = models.CharField("Izoh", max_length=255, blank=True)
    status = models.CharField("Holati", max_length=10, choices=STATUSES, default=PLANNED)
    conductor = models.CharField("Inventarizatsiya o'tkazuvchi", max_length=150, blank=True)
    started_at = models.DateField("Boshlangan sana", null=True, blank=True)
    finished_at = models.DateField("Yakunlangan sana", null=True, blank=True)
    seq = models.PositiveIntegerField("Inventar raqam hisoblagichi", default=0)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Filial"
        verbose_name_plural = "Filiallar"

    def __str__(self):
        return self.name


class Location(models.Model):
    """Qayerda turibdi: Ofis, Ombor, Kassa... (ro'yxatda yo'q joyni ham yozish mumkin)."""

    name = models.CharField("Nomi", max_length=120, unique=True)
    name_ru = models.CharField("Nomi (rus)", max_length=120, blank=True, default="")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Joy"
        verbose_name_plural = "Joylar"

    def __str__(self):
        return self.name


class DeviceType(models.Model):
    name = models.CharField("Qurilma turi", max_length=120, unique=True)
    group = models.CharField("Guruh", max_length=60, blank=True)
    description = models.CharField("Bu nima?", max_length=255, blank=True)
    serial_hint = models.CharField("Seriya raqami qayerda?", max_length=255, blank=True)
    extra_hint = models.CharField("Qo'shimcha nima yozish kerak", max_length=255, blank=True)
    brands = models.JSONField("Brendlar", default=list, blank=True)
    # rus tilida (filial xodimlarining bir qismi faqat ruschani biladi)
    name_ru = models.CharField("Qurilma turi (rus)", max_length=120, blank=True, default="")
    description_ru = models.CharField("Bu nima? (rus)", max_length=255, blank=True, default="")
    serial_hint_ru = models.CharField("Seriya raqami qayerda? (rus)", max_length=255, blank=True, default="")
    extra_hint_ru = models.CharField("Qo'shimcha (rus)", max_length=255, blank=True, default="")
    is_active = models.BooleanField("Faol", default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Qurilma turi"
        verbose_name_plural = "Qurilma turlari"

    def __str__(self):
        return self.name


class Employee(models.Model):
    """Filial xodimi: qurilma kimda turganini bildiradi. Tashkilot (loyiha) va filial bo'yicha filtrlanadi."""

    MANUAL, IMPORT, STAFF = "manual", "import", "staff"

    full_name = models.CharField("F.I.Sh.", max_length=150)
    position = models.CharField("Lavozimi", max_length=120, blank=True)
    phone = models.CharField("Telefon", max_length=40, blank=True)
    telegram = models.CharField("Telegram", max_length=64, blank=True, default="")  # username, @ siz
    org = models.ForeignKey(Org, verbose_name="Tashkilot", null=True, blank=True, on_delete=models.SET_NULL,
                            related_name="employees")
    branch = models.ForeignKey(Branch, verbose_name="Filial", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="employees")
    project = models.CharField("Loyiha / brend", max_length=120, blank=True)
    department = models.CharField("Bo'lim", max_length=120, blank=True)
    note = models.CharField("Izoh", max_length=255, blank=True)
    is_active = models.BooleanField("Faol", default=True)
    source = models.CharField(max_length=10, default=MANUAL)
    external_id = models.CharField(max_length=40, blank=True)  # Xodimlar tuzilmasidan (StaffPerson) kelganlar uchun
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name", "id"]
        indexes = [models.Index(fields=["branch", "full_name"], name="inv_emp_branch_name")]
        verbose_name = "Xodim"
        verbose_name_plural = "Xodimlar"

    def __str__(self):
        return self.full_name


class Access(models.Model):
    """Modulga kirish huquqi. Zona administratori avtomatik — boshqarish; qolganlar faqat shu yozuv bilan kiradi."""

    MANAGER, DIRECTOR, COLLECTOR = "manager", "director", "collector"
    LEVELS = [(MANAGER, "Boshqaruvchi (IT)"), (DIRECTOR, "Rahbar (faqat ko'rish)"), (COLLECTOR, "Filial xodimi")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inv_access")
    level = models.CharField("Daraja", max_length=10, choices=LEVELS, default=COLLECTOR)
    branches = models.ManyToManyField(Branch, blank=True, related_name="accesses", verbose_name="Filiallar")
    password_enc = models.TextField(blank=True)  # berilgan boshlang'ich parol (shifrlangan) — loginlar faylini chiqarish uchun
    note = models.CharField("Izoh", max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Inventarizatsiya huquqi"
        verbose_name_plural = "Inventarizatsiya huquqlari"

    def __str__(self):
        return f"{self.user} ({self.level})"


class Item(models.Model):
    OK, REPAIR, BROKEN, SPARE, MISSING = "ok", "repair", "broken", "spare", "missing"
    CONDITIONS = [(OK, "Ishlayapti"), (REPAIR, "Ta'mirga muhtoj"), (BROKEN, "Ishlamaydi"),
                  (SPARE, "Ishlatilmayapti (zaxirada)"), (MISSING, "Topilmadi")]

    inv_number = models.CharField("Inventar raqam", max_length=24, unique=True)
    org = models.ForeignKey(Org, verbose_name="Tashkilot", null=True, blank=True, on_delete=models.SET_NULL,
                            related_name="items")
    branch = models.ForeignKey(Branch, verbose_name="Filial", on_delete=models.PROTECT, related_name="items")
    location = models.CharField("Qayerda turibdi", max_length=120, blank=True)
    device_type = models.ForeignKey(DeviceType, verbose_name="Qurilma turi", on_delete=models.PROTECT,
                                    related_name="items")
    brand = models.CharField("Brend", max_length=80, blank=True)
    model = models.CharField("Model", max_length=150, blank=True)
    serial = models.CharField("Seriya raqami", max_length=120, blank=True, db_index=True)
    quantity = models.PositiveIntegerField("Soni", default=1)
    condition = models.CharField("Holati", max_length=10, choices=CONDITIONS, default=OK)
    employee = models.ForeignKey(Employee, verbose_name="Kimda turibdi", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="items")
    note = models.TextField("Izoh", blank=True)
    # xarid va kafolat (ixtiyoriy). "Kafolat tugaydi" saqlanmaydi — sana + oydan hisoblanadi (warranty_until)
    purchase_price = models.PositiveBigIntegerField("Sotib olingan narxi (so'm)", null=True, blank=True)
    purchase_date = models.DateField("Sotib olingan sana", null=True, blank=True)
    warranty_months = models.PositiveSmallIntegerField("Kafolat muddati (oy)", null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [models.Index(fields=["branch", "is_deleted"], name="inv_item_branch")]
        verbose_name = "Qurilma"
        verbose_name_plural = "Qurilmalar"

    def __str__(self):
        return f"{self.inv_number} {self.device_type}"

    @property
    def warranty_until(self):
        return add_months(self.purchase_date, self.warranty_months)


class Photo(models.Model):
    item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.CASCADE, related_name="photos")
    path = models.CharField(max_length=400)
    thumb = models.CharField(max_length=400, blank=True)
    size = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Rasm"
        verbose_name_plural = "Rasmlar"


class Log(models.Model):
    """Kim, qachon, qaysi filialda nima qildi — tarix va statistika shu jadvaldan."""

    CREATE, UPDATE, DELETE, RESTORE, IMPORT, STATUS, LOGIN = "create", "update", "delete", "restore", "import", "status", "login"
    SIGN = "sign"
    ACTIONS = [(CREATE, "Qo'shdi"), (UPDATE, "O'zgartirdi"), (DELETE, "O'chirdi"), (RESTORE, "Tikladi"),
               (IMPORT, "Import"), (STATUS, "Holat"), (LOGIN, "Kirdi"), (SIGN, "Imzoladi")]

    at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name="logs")
    item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="logs")
    entity = models.CharField(max_length=12, default="item")  # item / employee / branch / user / catalog
    action = models.CharField(max_length=10, choices=ACTIONS)
    summary = models.CharField(max_length=300, blank=True)
    changes = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-at", "-id"]
        indexes = [models.Index(fields=["branch", "at"], name="inv_log_branch_at"),
                   models.Index(fields=["user", "at"], name="inv_log_user_at")]
        verbose_name = "Tarix yozuvi"
        verbose_name_plural = "Tarix"


class Ack(models.Model):
    """Xodimning tasdiqnomasi: unga biriktirilgan qurilmalar ro'yxatini havola orqali ochib, imzo bilan tasdiqlaydi.

    Ro'yxat havola yaratilgan paytdagi holatda saqlanadi (items) — keyin qurilmalar o'zgarsa, tasdiqnoma "eskirgan"
    deb ko'rsatiladi va yangisini yuborish mumkin.
    """

    PENDING, SIGNED, REVOKED = "pending", "signed", "revoked"
    STATUSES = [(PENDING, "Kutilmoqda"), (SIGNED, "Imzolangan"), (REVOKED, "Bekor qilingan")]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="acks")
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name="acks")
    token = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    items = models.JSONField(default=list, blank=True)  # [{id, inv_number, type, brand, model, serial, quantity, ...}]
    result = models.JSONField(default=list, blank=True)  # [{id, ok, comment}]
    comment = models.TextField(blank=True)
    signer_name = models.CharField(max_length=150, blank=True)
    signature = models.CharField(max_length=400, blank=True)  # PNG fayl yo'li
    lang = models.CharField(max_length=4, blank=True)
    ip = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Tasdiqnoma"
        verbose_name_plural = "Tasdiqnomalar"
