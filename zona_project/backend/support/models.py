"""Support bot: guruhlardagi savollarga avto-javob, bilim bazasi va xodimlar javoblaridan o'rganish.

Faqat yangi jadvallar (support_*). Zona jadvallariga faqat o'qish uchun bog'lanadi (Member, TeamContact, Zone):
xodim yoki jamoa o'chirilsa, bu yerdagi bog'lanish bo'shaydi (SET_NULL), hech narsa yo'qolmaydi.
"""
from django.db import models

from zona.models import Member, StaffPerson, TeamContact, Zone


class Settings(models.Model):
    """Umumiy sozlamalar (bitta qator). Telegram API ID/hash — barcha botlar uchun bir xil (egasining nomida)."""

    api_id = models.CharField("Telegram API ID", max_length=20, blank=True)
    api_hash_enc = models.TextField(blank=True)
    ai_enabled = models.BooleanField("AI javoblari yoqilgan", default=False)
    ai_daily_limit = models.PositiveIntegerField("AI: kunlik so'rov limiti", default=200)
    ai_min_confidence = models.PositiveIntegerField("AI: minimal ishonch (%)", default=70)
    faq_threshold = models.PositiveIntegerField("Bazadan javob: o'xshashlik chegarasi (%)", default=72)
    route_threshold = models.PositiveIntegerField("Qoida bo'yicha javob: ishonch chegarasi (%)", default=60)
    learn_from_staff = models.BooleanField("Xodimlar javoblaridan o'rganish", default=True)
    ocr_enabled = models.BooleanField("Rasmdagi matnni o'qish (OCR)", default=True)
    media_days = models.PositiveIntegerField("O'rgatilmagan rasmlarni saqlash (kun, 0 — doim)", default=0)
    image_match = models.BooleanField("Rasm turini o'rgatilgan namunalar bo'yicha tanish", default=True)
    image_threshold = models.PositiveIntegerField("Rasm o'xshashligi chegarasi (0–64, kichik — qattiqroq)", default=10)
    image_autolabel = models.BooleanField("Xodim javobi va ishonchli moslikdan rasmni avtomatik o'rgatish", default=True)
    signature = models.CharField("Javob imzosi", max_length=120, blank=True, default="🤖 Avto-javob")
    # --- xatti-harakat (har biri yoqib/o'chiriladi) ---
    drafts_to_admin = models.BooleanField("Soya rejimi: javob taklifini admin chatiga yuborish", default=True)
    escalation_ack = models.BooleanField("Jonli: javob topilmasa guruhga «qabul qilindi» deb yozish", default=True)
    mention_responsible = models.BooleanField("Jonli: mas'ulni @ bilan belgilash", default=True)
    feedback_buttons = models.BooleanField("Jonli: javob ostida 👍/👎 tugmalari", default=True)
    notify_candidates = models.BooleanField("Yangi javob nomzodini admin chatiga yuborish (✅/❌)", default=True)
    learn_clarifications = models.BooleanField("Xodimning aniqlashtiruvchi savollarini javob deb olmaslik", default=True)
    ask_first_prompt = models.BooleanField("Jonli: kerakli ma'lumot yo'q bo'lsa avval uni so'rash", default=True)
    mention_asker = models.BooleanField("Jonli: javobda savol beruvchini belgilash", default=True)
    mention_supervisor = models.BooleanField("Jonli: supervayzer harakati kerak bo'lsa — savol beruvchining supervayzerini belgilash", default=True)
    workers = models.PositiveIntegerField("Bir vaqtda qayta ishlanadigan savollar", default=3)
    contact_lookup = models.BooleanField("Kontakt qidiruvi (shaxsiy chatda, xodimlar va rahbarlar uchun)", default=True)
    ai_primary = models.BooleanField("AI asosiy javob beradi (bilim bazasi asosida javob tuzadi)", default=True)
    ai_primary_below = models.PositiveIntegerField("Bazadan moslik shundan past bo'lsa — javobni AI tuzadi (%)", default=95)
    album_window = models.PositiveIntegerField("Bir xodimning ketma-ket rasmlari bitta savol (soniya)", default=90)
    # --- guruh tarixini o'rganish (MTProto, egasining akkaunti orqali, faqat o'qish) ---
    history_days = models.PositiveIntegerField("Tarix: necha kunlik", default=30)
    history_photos = models.BooleanField("Tarix: rasmlarni ham o'qish (OCR)", default=True)
    history_max = models.PositiveIntegerField("Tarix: bitta guruhdan ko'pi bilan xabar", default=5000)
    mtproto_session_enc = models.TextField(blank=True)
    mtproto_user = models.CharField("Ulangan akkaunt", max_length=150, blank=True)
    mtproto_pending_enc = models.TextField(blank=True)  # kod kutilmoqda: telefon, hash, vaqtinchalik seans
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Support sozlamalari"
        verbose_name_plural = "Support sozlamalari"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


MODE_OFF, MODE_COLLECT, MODE_SHADOW, MODE_LIVE = "off", "collect", "shadow", "live"
MODES = [(MODE_OFF, "O'chiq"), (MODE_COLLECT, "Faqat yig'ish (hech kimga yozmaydi)"),
         (MODE_SHADOW, "Soya rejimi (faqat admin chatiga)"), (MODE_LIVE, "Jonli (guruhga javob)")]


class Bot(models.Model):
    """Telegram bot. Token shifrlangan; admin paneldan qo'shiladi, o'zgartiriladi, o'chiriladi."""

    name = models.CharField("Nomi", max_length=80)
    username = models.CharField("Username", max_length=64, blank=True)
    tg_id = models.BigIntegerField(null=True, blank=True)
    token_enc = models.TextField(blank=True)
    enabled = models.BooleanField("Yoqilgan", default=True)
    mode = models.CharField("Rejim", max_length=8, choices=MODES, default=MODE_SHADOW)
    admin_chat_id = models.BigIntegerField("Admin chat ID", null=True, blank=True,
                                           help_text="Soya rejimidagi javoblar va tasdiqlash so'rovlari shu chatga keladi")
    welcome = models.TextField("Shaxsiy chatdagi salom matni", blank=True)
    last_update_id = models.BigIntegerField(default=0)
    last_ok_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Support bot"
        verbose_name_plural = "Support botlar"

    def __str__(self):
        return f"{self.name} (@{self.username})" if self.username else self.name


class Group(models.Model):
    """Bot qo'shilgan Telegram guruh. Rejim guruh bo'yicha alohida (standart — bot rejimi)."""

    INHERIT = "inherit"
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name="groups")
    chat_id = models.BigIntegerField()
    title = models.CharField(max_length=200, blank=True)
    username = models.CharField(max_length=64, blank=True)  # ochiq guruh: t.me/<username>/<id>
    mode = models.CharField(max_length=8, choices=[(INHERIT, "Bot rejimi"), *MODES], default=INHERIT)
    is_active = models.BooleanField(default=True)
    is_admin = models.BooleanField("Bot guruhda admin", default=False)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(null=True, blank=True)

    def message_link(self, message_id):
        """Telegram'dagi aniq manzil: ochiq guruh — t.me/<username>/<id>, yopiq superguruh — t.me/c/<ichki_id>/<id>."""
        if self.username:
            return f"https://t.me/{self.username}/{message_id}"
        cid = str(self.chat_id)
        return f"https://t.me/c/{cid[4:]}/{message_id}" if cid.startswith("-100") else ""

    class Meta:
        ordering = ["title", "id"]
        constraints = [models.UniqueConstraint(fields=["bot", "chat_id"], name="support_unique_group")]

    def effective_mode(self):
        if not self.is_active or not self.bot.enabled:
            return MODE_OFF
        return self.bot.mode if self.mode == self.INHERIT else self.mode

    def __str__(self):
        return self.title or str(self.chat_id)


class Entry(models.Model):
    """Bilim bazasi yozuvi: standart holat (shablon) yoki savol-javob.

    Hayot sikli: new → review → approved (bot ishlatadi) / rejected; approved → archived.
    Tasdiqlangan javob tahrirlansa — tahrir `pending` da turadi, tasdiqlanmaguncha bot eski javobni ishlatadi.
    """

    TEMPLATE, FAQ = "template", "faq"
    KINDS = [(TEMPLATE, "Standart holat (shablon)"), (FAQ, "Savol-javob")]
    NEW, REVIEW, APPROVED, REJECTED, ARCHIVED = "new", "review", "approved", "rejected", "archived"
    STATUSES = [(NEW, "Yangi"), (REVIEW, "Ko'rib chiqilmoqda"), (APPROVED, "Tasdiqlangan"),
                (REJECTED, "Rad etilgan"), (ARCHIVED, "Arxiv")]
    SOURCES = [("manual", "Qo'lda"), ("staff", "Xodim javobi"), ("history", "Guruh tarixi"), ("bot", "Bot yig'di"),
               ("seed", "Boshlang'ich"),
               ("panel", "Paneldan javob")]

    kind = models.CharField(max_length=10, choices=KINDS, default=FAQ)
    title = models.CharField("Sarlavha", max_length=200)
    questions = models.JSONField("Savol ko'rinishlari", default=list, blank=True)
    triggers = models.JSONField("Shartlar (shablon)", default=list, blank=True,
                                help_text="Har biri: 'so'z' yoki 'so'z && boshqa so'z' yoki 're:regex'")
    extract = models.JSONField("Ajratib olinadigan maydonlar (regex, nomli guruh)", default=list, blank=True)
    answer = models.TextField("Javob (uz)")
    answer_ru = models.TextField("Javob (ru)", blank=True)
    zone = models.ForeignKey(Zone, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    responsible = models.ForeignKey(Member, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=10, choices=STATUSES, default=NEW)
    source = models.CharField(max_length=8, choices=SOURCES, default="manual")
    priority = models.BooleanField("Ustuvor (bot javobini xodim tuzatgan)", default=False)
    pending = models.JSONField("Tasdiq kutayotgan tahrir", null=True, blank=True)
    attachments = models.JSONField("Javob bilan yuboriladigan fayllar (Media id)", default=list, blank=True)
    ask_first = models.TextField("Javobdan oldin so'raladigan ma'lumot", blank=True,
                                 help_text="Xodimlar odatda avval nimani so'raydi (masalan: STIR, skrinshot)")
    author = models.CharField(max_length=150, blank=True)
    approved_by = models.CharField(max_length=150, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    uses = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    dislikes = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "-updated_at", "-id"]
        verbose_name = "Bilim bazasi yozuvi"
        verbose_name_plural = "Bilim bazasi"

    def __str__(self):
        return self.title


class EntryVersion(models.Model):
    """Yozuvning oldingi holati: kim, qachon, nimani o'zgartirgan; bir tugma bilan qaytariladi."""

    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="versions")
    title = models.CharField(max_length=200)
    questions = models.JSONField(default=list)
    triggers = models.JSONField(default=list)
    extract = models.JSONField(default=list)
    answer = models.TextField()
    answer_ru = models.TextField(blank=True)
    editor = models.CharField(max_length=150, blank=True)
    note = models.CharField(max_length=200, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at", "-id"]


class TgUser(models.Model):
    """Guruhlarda yozgan Telegram foydalanuvchi; xodim bo'lsa — Member yoki jamoa kontaktiga bog'lanadi."""

    tg_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=64, blank=True)
    name = models.CharField(max_length=150, blank=True)
    member = models.ForeignKey(Member, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    contact = models.ForeignKey(TeamContact, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # kontaktlardagi dala xodimi (agent/supervayzer): supervayzerini topish uchun. auto — ism bo'yicha aniq moslik, manual — paneldan
    staff_person = models.ForeignKey(StaffPerson, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    staff_link = models.CharField(max_length=8, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    @property
    def is_staff(self):
        return bool(self.member_id or self.contact_id)

    def staff_name(self):
        if self.contact_id:
            return self.contact.name
        if self.member_id:
            return self.member.name
        return self.name

    def staff_level(self):
        m = self.contact.member if self.contact_id else self.member
        return m.level if m else ""

    def __str__(self):
        return f"{self.name} (@{self.username})" if self.username else self.name


class Message(models.Model):
    """Guruhga kelgan xabar (savol yoki xodim javobi) va bot nima qilgani."""

    QUESTION, STAFF, CLARIFY, INFO, OTHER = "question", "staff", "clarify", "info", "other"
    NEW, ANSWERED, DRAFTED, ESCALATED, IGNORED, CLOSED = "new", "answered", "drafted", "escalated", "ignored", "closed"
    STATUSES = [(NEW, "Yangi"), (ANSWERED, "Javob berildi"), (DRAFTED, "Qoralama (soya rejimi)"),
                (ESCALATED, "Odamga uzatildi"), (IGNORED, "Savol emas"), (CLOSED, "Yopildi")]

    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name="messages")
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    chat_id = models.BigIntegerField()
    message_id = models.BigIntegerField()
    reply_to_id = models.BigIntegerField(null=True, blank=True)
    user = models.ForeignKey(TgUser, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    kind = models.CharField(max_length=10, default=QUESTION)
    text = models.TextField(blank=True)
    photo_file_id = models.CharField(max_length=200, blank=True)
    photo_path = models.CharField(max_length=300, blank=True)
    ocr_text = models.TextField(blank=True)
    lang = models.CharField(max_length=5, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=NEW)
    stage = models.CharField(max_length=10, blank=True)  # template / faq / rule / ai / staff / panel
    source = models.CharField(max_length=8, default="live")  # live / history
    media_group_id = models.CharField(max_length=64, blank=True, db_index=True)  # albom: bir nechta rasm — bitta savol
    entry = models.ForeignKey(Entry, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    confidence = models.PositiveIntegerField(default=0)
    answer_text = models.TextField(blank=True)
    answered_by = models.CharField(max_length=150, blank=True)
    bot_reply_id = models.BigIntegerField(null=True, blank=True)
    question = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="staff_replies")
    feedback = models.SmallIntegerField(default=0)  # 1 / -1
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["bot", "chat_id", "message_id"], name="support_unique_message")]
        indexes = [models.Index(fields=["status", "created_at"])]


class HistoryJob(models.Model):
    """Guruh tarixini o'qib o'rganish vazifasi (bot jarayoni fonda bajaradi)."""

    QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="history_jobs")
    days = models.PositiveIntegerField(default=30)
    photos = models.BooleanField(default=True)
    status = models.CharField(max_length=8, default=QUEUED)
    progress = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=500, blank=True)
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Media(models.Model):
    """Serverda saqlanadigan fayl: savoldagi rasm/video yoki javob biriktirmasi.

    Rasmlar uchun "vizual iz" (perceptual hash) hisoblanadi: agentlar yuboradigan skrinshotlar deyarli bir xil ekran
    bo'ladi (faqat foydalanuvchi ma'lumoti farq qiladi), shuning uchun yangi rasm o'rgatilgan namunalarga (label)
    eng yaqin qo'shni bo'yicha solishtiriladi — OCR'siz, bir zumda. O'rgatilgan va biriktirilgan fayllar o'chirilmaydi.
    """

    PHOTO, VIDEO, VIDEO_NOTE, ANIMATION, DOCUMENT = "photo", "video", "video_note", "animation", "document"
    KINDS = [(PHOTO, "Rasm"), (VIDEO, "Video"), (VIDEO_NOTE, "Dumaloq video"), (ANIMATION, "GIF"), (DOCUMENT, "Fayl")]
    kind = models.CharField(max_length=12, choices=KINDS, default=PHOTO)
    path = models.CharField(max_length=400, blank=True)
    name = models.CharField(max_length=200, blank=True)
    mime = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    dhash = models.CharField(max_length=16, blank=True)
    dhash_mid = models.CharField(max_length=16, blank=True)
    ocr_text = models.TextField(blank=True)
    source = models.CharField(max_length=10, default="question")  # question / history / answer / seed
    message = models.ForeignKey(Message, null=True, blank=True, on_delete=models.SET_NULL, related_name="media")
    label = models.ForeignKey(Entry, null=True, blank=True, on_delete=models.SET_NULL, related_name="image_examples")
    label_auto = models.BooleanField(default=False)
    label_by = models.CharField(max_length=150, blank=True)
    tg_file_ids = models.JSONField(default=dict, blank=True)  # {bot_id: file_id} — qayta yuklamasdan yuborish
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["kind", "label"])]


class AIJob(models.Model):
    """Bot bo'yicha AI tahlili: bilim bazasini ko'rib chiqish yoki javobsiz savollardan yangi javob taklif qilish."""

    REVIEW_ENTRIES, REVIEW_UNANSWERED = "entries", "unanswered"
    KINDS = [(REVIEW_ENTRIES, "Bilim bazasini ko'rib chiqish"), (REVIEW_UNANSWERED, "Javobsiz savollar tahlili")]
    QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"
    kind = models.CharField(max_length=12, choices=KINDS)
    params = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=8, default=QUEUED)
    progress = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=500, blank=True)
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Suggestion(models.Model):
    """AI taklifi. Xodim tasdiqlaguncha hech narsa o'zgarmaydi; tasdiqlansa — eski holat versiyaga yoziladi."""

    IMPROVE, QUESTIONS, MERGE, NEW, ARCHIVE = "improve", "questions", "merge", "new", "archive"
    KINDS = [(IMPROVE, "Javobni yaxshilash"), (QUESTIONS, "Savol ko'rinishlari qo'shish"), (MERGE, "Takrorni birlashtirish"),
             (NEW, "Yangi yozuv"), (ARCHIVE, "Arxivlash")]
    PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"
    job = models.ForeignKey(AIJob, null=True, blank=True, on_delete=models.SET_NULL, related_name="suggestions")
    kind = models.CharField(max_length=10, choices=KINDS)
    entry = models.ForeignKey(Entry, null=True, blank=True, on_delete=models.CASCADE, related_name="suggestions")
    target = models.ForeignKey(Entry, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    payload = models.JSONField(default=dict, blank=True)  # title, answer, answer_ru, ask_first, questions
    reason = models.TextField(blank=True)
    question_ids = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=9, default=PENDING)
    decided_by = models.CharField(max_length=150, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
