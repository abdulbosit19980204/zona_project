"""PRBC integratsiyasi jadvallari (alohida: prbc_*). Boshqa ilovalarning jadvallariga faqat bog'lanadi (SET_NULL)."""
from django.db import models

KAMOLIDDIN = 2  # PRBC: ATAQULOV KAMOLIDDIN — IT bo'limi rahbari, vazifalarda kuzatuvchi (1C vazifalarida ham shunday)


def default_watchers():
    return [KAMOLIDDIN]


class Connection(models.Model):
    """PRBC ulanishi va sinxronlash sozlamalari (yagona yozuv, pk=1). Parol va tokenlar shifrlangan."""
    enabled = models.BooleanField(default=False)
    base_url = models.CharField(max_length=200, default="https://prbc.uz")
    phone = models.CharField(max_length=32, blank=True)
    password_enc = models.TextField(blank=True)
    access_enc = models.TextField(blank=True)
    refresh_enc = models.TextField(blank=True)
    access_until = models.DateTimeField(null=True, blank=True)
    organization = models.IntegerField(null=True, blank=True)
    me = models.JSONField(default=dict, blank=True)  # kim bo'lib ulandik: {id, full_name, position}
    # "Yangi xodim / Ishdan bo'shash" vazifalari tushadigan loyiha (1C → PRBC Kadrlar). Bo'sh — avtomatik topiladi
    lifecycle_project = models.IntegerField(null=True, blank=True)
    task_project = models.IntegerField(null=True, blank=True)  # biz yaratadigan vazifalar uchun standart loyiha
    task_default_assignees = models.JSONField(default=list, blank=True)  # PRBC user id'lari
    task_watchers = models.JSONField(default=default_watchers, blank=True)  # kuzatuvchilar (observer) — PRBC user id
    close_on_done = models.BooleanField(default=True)  # PRBC'da bajarildi -> bizdagi savol "hal bo'ldi" + hisobot
    group_projects = models.JSONField(default=dict, blank=True)  # Telegram guruh (support Group id) -> PRBC loyiha id
    projects = models.JSONField(default=list, blank=True)  # PRBC loyihalar ro'yxati (kesh): [{id, name}]
    watch_self = models.BooleanField(default=True)  # ulangan akkaunt egasi ham har vazifaga kuzatuvchi
    notify_done = models.BooleanField(default=True)  # bajarilganda guruhdagi savolga izohlari bilan javob
    notify_created = models.BooleanField(default=False)  # vazifa ochilganda guruhdagi savolga qisqa xabar
    attach_files = models.BooleanField(default=True)  # savoldagi rasm/fayllar PRBC vazifasiga yuklanadi
    assignee_map = models.JSONField(default=dict, blank=True)  # Telegram username -> PRBC user id (qo'lda moslash)
    outlet_lookup = models.BooleanField(default=True)  # bot savoldagi STIR/1C kodi bo'yicha mijoz arizasi holatini PRBC'dan o'qiydi
    sync_minutes = models.PositiveIntegerField(default=30)
    auto_left = models.BooleanField(default=True)  # bo'shaganni avtomatik belgilash (kontakt o'rni, inventar xodimi)
    comment_devices = models.BooleanField(default=True)  # bo'shash vazifasiga xodimdagi qurilmalar ro'yxati
    sync_requested = models.BooleanField(default=False)  # "Hozir sinxronlash" — worker bir necha soniyada bajaradi
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_ok_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    worker_beat = models.DateTimeField(null=True, blank=True)
    lifecycle_cursor = models.DateTimeField(null=True, blank=True)  # shu vaqtdan keyin o'zgargan vazifalar o'qiladi
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "PRBC ulanishi"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Person(models.Model):
    """PRBC/1C'dagi xodim — bizdagi kontakt, mas'ul, bot foydalanuvchisi va inventar xodimi bilan bog'lanadi."""
    ACTIVE, LEAVING, LEFT = "active", "leaving", "left"
    STATUSES = [(ACTIVE, "Ishlayapti"), (LEAVING, "Bo'shayapti (oxirgi kun oldinda)"), (LEFT, "Bo'shagan")]

    prbc_user = models.IntegerField(null=True, blank=True, unique=True)
    tab_number = models.CharField(max_length=40, blank=True, db_index=True)  # 1C tabel raqami
    full_name = models.CharField(max_length=200)
    name_key = models.CharField(max_length=200, db_index=True, blank=True)
    position = models.CharField(max_length=200, blank=True)
    department = models.CharField(max_length=200, blank=True)
    company = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=ACTIVE, db_index=True)
    hired_on = models.DateField(null=True, blank=True)
    left_on = models.DateField(null=True, blank=True)
    left_reason = models.CharField(max_length=300, blank=True)
    hire_task = models.CharField(max_length=40, blank=True)
    leave_task = models.CharField(max_length=40, blank=True)
    in_roster = models.BooleanField(default=False)  # PRBC'da vazifaga qo'yiladiganlar ro'yxatida bor
    agent_code = models.CharField(max_length=80, blank=True, db_index=True)  # "SR2 Tashkent", "Toshkent K1"...
    code_manual = models.BooleanField(default=False)  # kod qo'lda kiritilgan — sinxronlash o'zgartirmaydi
    sources = models.JSONField(default=list, blank=True)
    # bog'lanishlar (bizdagi yozuvlar)
    staff_person = models.ForeignKey("zona.StaffPerson", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    member = models.ForeignKey("zona.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    inv_employee = models.ForeignKey("inventory.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    tg_user = models.ForeignKey("support.TgUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    link_manual = models.BooleanField(default=False)  # qo'lda bog'langan — avtomatik o'zgartirilmaydi
    left_applied = models.BooleanField(default=False)  # bo'shash bizdagi yozuvlarga qo'llangan
    undo = models.JSONField(default=dict, blank=True)  # qaytarish uchun avvalgi holat
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "PRBC xodimi"
        verbose_name_plural = "PRBC xodimlari"

    def __str__(self):
        return self.full_name


class Change(models.Model):
    """Har bir o'zgarish jurnali: yangi xodim, ma'lumot yangilandi, bo'shadi, qaytarildi, bog'landi."""
    NEW, UPDATED, LEAVING, LEFT, RETURNED, LINKED, APPLIED, REVERTED, TASK = (
        "new", "updated", "leaving", "left", "returned", "linked", "applied", "reverted", "task")
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.CASCADE, related_name="changes")
    kind = models.CharField(max_length=12, db_index=True)
    text = models.CharField(max_length=500)
    data = models.JSONField(default=dict, blank=True)
    actor = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["-at", "-id"]


class SyncRun(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    ok = models.BooleanField(default=False)
    stats = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]


class Task(models.Model):
    """PRBC vazifasi nusxasi: biz yaratganlar va 1C'dan kelgan "Yangi xodim / Ishdan bo'shash" vazifalari."""
    HIRE, LEAVE, OURS, OTHER = "hire", "leave", "ours", "other"
    prbc_id = models.IntegerField(unique=True)
    code = models.CharField(max_length=40, blank=True)
    title = models.CharField(max_length=300)
    kind = models.CharField(max_length=8, default=OTHER, db_index=True)
    status_name = models.CharField(max_length=60, blank=True)
    status_category = models.CharField(max_length=20, blank=True, db_index=True)  # new / in_progress / done / cancelled
    project_id = models.IntegerField(null=True, blank=True)
    project_name = models.CharField(max_length=200, blank=True)
    assignee = models.CharField(max_length=200, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    prbc_created_at = models.DateTimeField(null=True, blank=True)
    prbc_updated_at = models.DateTimeField(null=True, blank=True)
    person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    support_task = models.ForeignKey("support.SupportTask", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    fields = models.JSONField(default=dict, blank=True)  # tavsifdan olingan: Xodim, Lavozim, Tabel raqami, sanalar
    devices_commented = models.BooleanField(default=False)
    people = models.JSONField(default=list, blank=True)  # [{id, name, position, role: assignee|co_assignee|observer}]
    watchers = models.CharField(max_length=300, blank=True)  # kuzatuvchilar ismi (ro'yxatda ko'rsatish uchun)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.CharField(max_length=200, blank=True)  # kim "bajarildi" qildi (vazifa tarixidan)
    spent_minutes = models.PositiveIntegerField(null=True, blank=True)
    report = models.JSONField(default=dict, blank=True)  # bajarilganda: izohlar, chek-list, sarflangan vaqt, tarix
    checked_at = models.DateTimeField(null=True, blank=True, db_index=True)  # oxirgi marta PRBC'dan tekshirilgan
    # savoldan PRBC'ga o'tkazilganlar: {"media": [Media id], "info": [qo'shimcha xabar id], "files": n, "notified": [...]}
    sync = models.JSONField(default=dict, blank=True)
    created_by = models.CharField(max_length=150, blank=True)  # biz yaratganda: kim (panel foydalanuvchisi / bot)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-prbc_updated_at", "-id"]
