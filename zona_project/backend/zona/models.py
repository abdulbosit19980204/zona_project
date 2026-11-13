"""Mas'uliyat arxitekturasi: kim nimaga javob beradi.

Tashkilot -> Bo'lim -> Xodim -> Jarayon -> Vazifa.
Vazifaning mas'uli (owner) savolga javob beradi va ishni bajaradi.
Jarayonda esa qo'shimcha rollar bor: egasi, tasdiqlovchi, nazoratchi, yordamchi, zaxira.
"""
from django.conf import settings
from django.db import models


class Department(models.Model):
    name = models.CharField("Nomi", max_length=80, unique=True)
    description = models.CharField("Tavsif", max_length=200, blank=True)
    order = models.PositiveIntegerField("Tartib", default=0)
    i18n = models.JSONField("Tarjimalar (AI)", default=dict, blank=True, editable=False)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Bo'lim"
        verbose_name_plural = "Bo'limlar"

    def __str__(self):
        return self.name


class System(models.Model):
    """Dastur yoki yo'nalish: ProTarget, 1C, Qurilma..."""

    name = models.CharField("Nomi", max_length=60, unique=True)
    order = models.PositiveIntegerField("Tartib", default=0)
    i18n = models.JSONField("Tarjimalar (AI)", default=dict, blank=True, editable=False)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Tizim"
        verbose_name_plural = "Tizimlar"

    def __str__(self):
        return self.name


class Team(models.Model):
    """Jamoa: bo'lim ichidagi guruh. Tuzilma: Kompaniya -> Bo'lim -> Jamoa -> Xodim."""

    department = models.ForeignKey(Department, verbose_name="Bo'lim", on_delete=models.CASCADE, related_name="teams")
    name = models.CharField("Nomi", max_length=80)
    description = models.CharField("Tavsif", max_length=200, blank=True)
    lead = models.ForeignKey("Member", verbose_name="Rahbari", null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="led_teams")
    order = models.PositiveIntegerField("Tartib", default=0)
    i18n = models.JSONField("Tarjimalar (AI)", default=dict, blank=True, editable=False)

    class Meta:
        ordering = ["department", "order", "id"]
        verbose_name = "Jamoa"
        verbose_name_plural = "Jamoalar"

    def __str__(self):
        return f"{self.department.name} / {self.name}"


class Member(models.Model):
    """Xodim yoki butun jamoa."""

    name = models.CharField("Ism yoki jamoa", max_length=80)
    role = models.CharField("Lavozim", max_length=80)
    department = models.ForeignKey(Department, verbose_name="Bo'lim", null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="members")
    team = models.ForeignKey(Team, verbose_name="Jamoa", null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="members")
    manager = models.ForeignKey("self", verbose_name="Rahbar", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="reports")
    is_team = models.BooleanField("Jamoa", default=False)
    trigger = models.CharField("Qaysi savol turi keladi", max_length=200, blank=True)
    does = models.TextField("Nima bilan shug'ullanadi", blank=True)
    excludes = models.TextField("Nima bilan shug'ullanmaydi", blank=True)
    # aloqa
    email = models.EmailField("Email", blank=True)
    phone = models.CharField("Telefon", max_length=40, blank=True)
    telegram = models.CharField("Telegram", max_length=64, blank=True)
    location = models.CharField("Joylashuv / ofis", max_length=120, blank=True)
    order = models.PositiveIntegerField("Tartib", default=0)
    i18n = models.JSONField("Tarjimalar (AI)", default=dict, blank=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Xodim"
        verbose_name_plural = "Xodimlar"

    def __str__(self):
        return f"{self.name} ({self.role})"


class Process(models.Model):
    """Biznes jarayon: bir yo'nalishdagi vazifalar to'plami."""

    name = models.CharField("Nomi", max_length=120)
    system = models.ForeignKey(System, verbose_name="Tizim", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="processes")
    description = models.TextField("Tavsif", blank=True)
    order = models.PositiveIntegerField("Tartib", default=0)
    i18n = models.JSONField("Tarjimalar (AI)", default=dict, blank=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Jarayon"
        verbose_name_plural = "Jarayonlar"

    def __str__(self):
        return self.name


class ProcessRole(models.Model):
    """Xodimning jarayondagi roli. Ijrochi (executor) vazifalardan kelib chiqadi."""

    OWNER, APPROVER, SUPERVISOR, CONTRIBUTOR, BACKUP = "owner", "approver", "supervisor", "contributor", "backup"
    ROLES = [
        (OWNER, "Egasi"),
        (APPROVER, "Tasdiqlovchi"),
        (SUPERVISOR, "Nazoratchi"),
        (CONTRIBUTOR, "Yordamchi"),
        (BACKUP, "Zaxira"),
    ]

    process = models.ForeignKey(Process, on_delete=models.CASCADE, related_name="roles")
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="process_roles")
    role = models.CharField(max_length=12, choices=ROLES)

    class Meta:
        ordering = ["process", "role", "id"]
        constraints = [models.UniqueConstraint(fields=["process", "member", "role"], name="zona_unique_process_role")]
        verbose_name = "Jarayon roli"
        verbose_name_plural = "Jarayon rollari"

    def __str__(self):
        return f"{self.member.name}: {self.get_role_display()} ({self.process.name})"


class Task(models.Model):
    """Vazifa = agent yoki supervayzer bergan savol turi."""

    title = models.CharField("Savol turi / vazifa", max_length=300)
    process = models.ForeignKey(Process, verbose_name="Jarayon", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="tasks")
    owner = models.ForeignKey(Member, verbose_name="Mas'ul (bajaradi)", null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="tasks")
    note = models.TextField("Izoh", blank=True)
    is_custom = models.BooleanField("Qo'lda qo'shilgan", default=False)
    order = models.PositiveIntegerField("Tartib", default=0)
    i18n = models.JSONField("Tarjimalar (AI)", default=dict, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Vazifa"
        verbose_name_plural = "Vazifalar"

    def __str__(self):
        return self.title


class TaskFallback(models.Model):
    """Navbatdagi mas'ul: asosiy mas'ul qila olmasa, savol shu xodimga o'tadi.

    1-navbat har doim Task.owner; bu yerdagi yozuvlar 2-, 3-... navbat (order bo'yicha).
    """

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="fallbacks")
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="fallback_tasks")
    condition = models.CharField("Qachon unga o'tadi", max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)
    i18n = models.JSONField("Tarjimalar (AI)", default=dict, blank=True, editable=False)

    class Meta:
        ordering = ["task", "order", "id"]
        constraints = [models.UniqueConstraint(fields=["task", "member"], name="zona_unique_task_fallback")]
        verbose_name = "Navbatdagi mas'ul"
        verbose_name_plural = "Navbatdagi mas'ullar"

    def __str__(self):
        return f"{self.task.title}: {self.member.name}"


class Event(models.Model):
    """O'zgarishlar tarixi. Nomlar nusxa sifatida saqlanadi: o'chirilsa ham tarix qoladi."""

    CREATED, MOVED, EDITED, DELETED, MEMBER, ROLE, APPROVAL = (
        "created", "moved", "edited", "deleted", "member", "role", "approval")
    KINDS = [(CREATED, "Qo'shildi"), (MOVED, "O'tkazildi"), (EDITED, "Tahrirlandi"),
             (DELETED, "O'chirildi"), (MEMBER, "Tuzilma"), (ROLE, "Rol"), (APPROVAL, "Tasdiqlash")]

    kind = models.CharField(max_length=10, choices=KINDS)
    subject = models.CharField(max_length=300, blank=True)
    from_name = models.CharField(max_length=80, blank=True)
    to_name = models.CharField(max_length=80, blank=True)
    text = models.CharField(max_length=300, blank=True)
    actor = models.CharField(max_length=150, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at", "-id"]
        verbose_name = "Tarix yozuvi"
        verbose_name_plural = "Tarix"


class EdgeCase(models.Model):
    """Aralash holat: savol ikki zona chegarasida bo'lsa avval kimga yoziladi."""

    situation = models.CharField("Vaziyat", max_length=200)
    first_owner = models.ForeignKey(Member, verbose_name="Avval kimga", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="edge_cases")
    then_text = models.CharField("Qachon boshqa zonaga o'tadi", max_length=300, blank=True)
    order = models.PositiveIntegerField("Tartib", default=0)
    i18n = models.JSONField("Tarjimalar (AI)", default=dict, blank=True, editable=False)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Aralash holat"
        verbose_name_plural = "Aralash holatlar"

    def __str__(self):
        return self.situation


class Authority(models.Model):
    """Vakolat: xodim nimani hal qilishga, tasdiqlashga haqli."""

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="authorities")
    title = models.CharField("Vakolat", max_length=200)
    scope = models.CharField("Doirasi / chegarasi", max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)
    i18n = models.JSONField("Tarjimalar (AI)", default=dict, blank=True, editable=False)

    class Meta:
        ordering = ["member", "order", "id"]
        verbose_name = "Vakolat"
        verbose_name_plural = "Vakolatlar"

    def __str__(self):
        return f"{self.member.name}: {self.title}"


class Synonym(models.Model):
    """Qidiruv lug'ati: bir ma'noli so'zlar guruhi (har qanday til/yozuvda), vergul bilan."""

    words = models.TextField("So'zlar (vergul bilan)")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Sinonim guruhi"
        verbose_name_plural = "Qidiruv lug'ati"

    def __str__(self):
        return self.words[:60]


# ---------------------------------------------------------------- foydalanuvchilar

class Profile(models.Model):
    """Saytdagi foydalanuvchi: roli va aloqa ma'lumotlari."""

    ADMIN, EDITOR, VIEWER = "admin", "editor", "viewer"
    ROLES = [(ADMIN, "Administrator"), (EDITOR, "Muharrir"), (VIEWER, "Kuzatuvchi")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="zona_profile")
    role = models.CharField("Rol", max_length=10, choices=ROLES, default=VIEWER)
    member = models.ForeignKey(Member, verbose_name="Xodim kartasi", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="accounts")
    position = models.CharField("Lavozim", max_length=120, blank=True)
    phone = models.CharField("Telefon", max_length=40, blank=True)
    telegram = models.CharField("Telegram", max_length=64, blank=True)
    address = models.CharField("Manzil", max_length=255, blank=True)
    note = models.CharField("Izoh", max_length=255, blank=True)

    class Meta:
        verbose_name = "Foydalanuvchi profili"
        verbose_name_plural = "Foydalanuvchi profillari"

    def __str__(self):
        return f"{self.user} ({self.role})"


class ChangeRequest(models.Model):
    """Tasdiqlash jarayoni: mas'uliyatni o'zgartirish taklifi. Tasdiqlansa, o'zgarish avtomatik qo'llanadi.

    kind / payload:
      task_owner  {"task": id, "owner": id | null}            vazifani boshqa xodimga o'tkazish
      role_add    {"process": id, "member": id, "role": str}  jarayonda rol berish
      role_remove {"role_id": id}                            rolni olib tashlash
    """

    TASK_OWNER, ROLE_ADD, ROLE_REMOVE = "task_owner", "role_add", "role_remove"
    KINDS = [(TASK_OWNER, "Vazifa mas'ulini o'zgartirish"), (ROLE_ADD, "Rol berish"), (ROLE_REMOVE, "Rolni olish")]
    PENDING, APPROVED, REJECTED, CANCELLED = "pending", "approved", "rejected", "cancelled"
    STATUSES = [(PENDING, "Kutilmoqda"), (APPROVED, "Tasdiqlandi"), (REJECTED, "Rad etildi"), (CANCELLED, "Bekor qilindi")]

    kind = models.CharField(max_length=20, choices=KINDS)
    payload = models.JSONField(default=dict)
    title = models.CharField(max_length=300)
    reason = models.TextField("Sabab", blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decision_note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Tasdiqlash so'rovi"
        verbose_name_plural = "Tasdiqlash so'rovlari"

    def __str__(self):
        return self.title


# ---------------------------------------------------------------- AI

class AIProvider(models.Model):
    """AI provayder ulanishi. API kalit shifrlangan holda saqlanadi."""

    KINDS = [
        ("anthropic", "Anthropic Claude"),
        ("openai", "OpenAI"),
        ("gemini", "Google Gemini"),
        ("xai", "xAI Grok"),
        ("deepseek", "DeepSeek"),
        ("mistral", "Mistral"),
        ("groq", "Groq"),
        ("openrouter", "OpenRouter"),
        ("azure_openai", "Azure OpenAI"),
        ("ollama", "Ollama (lokal)"),
        ("openai_compatible", "OpenAI-mos (boshqa)"),
    ]

    name = models.CharField("Nomi", max_length=80, unique=True)
    kind = models.CharField("Turi", max_length=20, choices=KINDS)
    base_url = models.CharField("Manzil (base URL)", max_length=255, blank=True)
    api_key_enc = models.TextField(blank=True)
    api_version = models.CharField("API versiya (Azure)", max_length=40, blank=True)
    is_active = models.BooleanField("Faol", default=True)
    models_cache = models.JSONField(default=list, blank=True)
    last_check_at = models.DateTimeField(null=True, blank=True)
    last_check_ok = models.BooleanField(null=True)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "AI provayder"
        verbose_name_plural = "AI provayderlar"

    def __str__(self):
        return f"{self.name} ({self.kind})"


class AITaskConfig(models.Model):
    """Har bir ish uchun alohida model sozlamasi."""

    ROUTE, PERSON, AUDIT, TRANSLATE = "route", "person", "audit", "translate"
    TASKS = [
        (ROUTE, "Savol kimga: savolni mas'ulga yo'naltirish"),
        (PERSON, "Xodim tahlili: vazifa, vakolat va chegaralar"),
        (AUDIT, "Tashkilot auditi: bo'shliq va kesishmalar"),
        (TRANSLATE, "Tarjima: matnlarni uz/ru/en tillariga o'girish"),
    ]
    EFFORTS = [("", "Standart"), ("low", "Past"), ("medium", "O'rta"), ("high", "Yuqori"),
               ("xhigh", "Juda yuqori"), ("max", "Maksimal")]

    task = models.CharField(max_length=20, choices=TASKS, unique=True)
    enabled = models.BooleanField(default=False)
    provider = models.ForeignKey(AIProvider, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    model = models.CharField(max_length=120, blank=True)
    effort = models.CharField(max_length=10, choices=EFFORTS, blank=True)
    temperature = models.FloatField(null=True, blank=True)
    max_tokens = models.PositiveIntegerField(default=4000)
    fallback_provider = models.ForeignKey(AIProvider, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    fallback_model = models.CharField(max_length=120, blank=True)
    instructions = models.TextField("Qo'shimcha ko'rsatma", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["task"]
        verbose_name = "AI vazifa sozlamasi"
        verbose_name_plural = "AI vazifa sozlamalari"


class AIUsage(models.Model):
    """Har bir AI so'rovi: kim, qaysi model, nechta token, qancha vaqt."""

    task = models.CharField(max_length=20)
    provider = models.CharField(max_length=80)
    model = models.CharField(max_length=120)
    ok = models.BooleanField(default=True)
    error = models.CharField(max_length=500, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    user = models.CharField(max_length=150, blank=True)
    prompt = models.CharField(max_length=300, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at", "-id"]
        verbose_name = "AI so'rov"
        verbose_name_plural = "AI so'rovlar jurnali"
