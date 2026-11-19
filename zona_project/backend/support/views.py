"""Support bot admin API: /api/support/...

Rollar (zona Profile): viewer — ko'rish, savolga javob yozish, yangi javob taklif qilish;
editor — javoblarni tasdiqlash/tahrirlash, shablonlar; admin — botlar va sozlamalar.
"""
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response

from zona.api import ZonaViewSet, zona_api
from zona.crypto import decrypt, encrypt, mask
from zona.models import Member, Profile, TeamContact
from zona.permissions import CanView, IsZonaAdmin, ReadOrEdit, has_role

from . import ocr, runner
from .engine import ai_quota_left, decide, detect_lang, to_html
from .models import MODES, Bot, Entry, EntryVersion, Group, Message, Settings
from .telegram import Client, TelegramError


def _actor(request):
    u = request.user
    return (u.get_full_name() or u.get_username()) if u and u.is_authenticated else ""


def _can_edit(request):
    return has_role(request, Profile.EDITOR)


class AdminOnly(IsZonaAdmin):
    pass


# ====================================================================== sozlamalar
SETTINGS_FIELDS = ["api_id", "ai_enabled", "ai_daily_limit", "ai_min_confidence", "faq_threshold", "route_threshold",
                   "learn_from_staff", "ocr_enabled", "media_days", "signature"]


def _settings_payload(s):
    from zona.ai import service as ai
    return {**{f: getattr(s, f) for f in SETTINGS_FIELDS}, "api_hash": mask(decrypt(s.api_hash_enc)),
            "has_api_hash": bool(s.api_hash_enc), "ocr_available": ocr.available(), "ocr_languages": ocr.languages(),
            "ai_ready": bool(ai.status().get("support")), "ai_quota_left": ai_quota_left(s)}


@zona_api(["GET", "PATCH"], [AdminOnly])
def settings_view(request):
    s = Settings.load()
    if request.method == "PATCH":
        data = request.data
        for f in SETTINGS_FIELDS:
            if f in data:
                setattr(s, f, data[f])
        if data.get("api_hash"):
            s.api_hash_enc = encrypt(str(data["api_hash"]).strip())
        if data.get("api_hash") == "" and data.get("clear_api_hash"):
            s.api_hash_enc = ""
        s.full_clean()
        s.save()
    return Response(_settings_payload(s))


# ====================================================================== botlar
class BotSerializer(serializers.ModelSerializer):
    token = serializers.CharField(write_only=True, required=False, allow_blank=True)
    token_masked = serializers.SerializerMethodField()
    groups_count = serializers.SerializerMethodField()

    class Meta:
        model = Bot
        fields = ["id", "name", "username", "enabled", "mode", "admin_chat_id", "welcome", "last_ok_at", "last_error",
                  "token", "token_masked", "groups_count", "created_at", "updated_at"]
        read_only_fields = ["username", "last_ok_at", "last_error", "created_at", "updated_at"]

    def get_token_masked(self, obj):
        return mask(decrypt(obj.token_enc))

    def get_groups_count(self, obj):
        return obj.groups.filter(is_active=True).count()

    def validate_token(self, value):
        value = value.strip()
        if value and (":" not in value or len(value) < 30):
            raise serializers.ValidationError("Token formati noto'g'ri (BotFather beradi: 123456:ABC...).")
        return value

    def _apply_token(self, validated):
        token = validated.pop("token", None)
        if token:
            for b in Bot.objects.exclude(pk=getattr(self.instance, "pk", None)):
                if decrypt(b.token_enc) == token:
                    raise serializers.ValidationError({"token": "Bu token boshqa botda ishlatilgan."})
            validated["token_enc"] = encrypt(token)
            validated["username"] = ""  # yangi token — username qayta olinadi
        return validated

    def create(self, validated):
        validated = self._apply_token(validated)
        if not validated.get("token_enc"):
            raise serializers.ValidationError({"token": "Token kiriting."})
        return super().create(validated)

    def update(self, instance, validated):
        return super().update(instance, self._apply_token(validated))


class BotViewSet(ZonaViewSet):
    queryset = Bot.objects.all()
    serializer_class = BotSerializer
    permission_classes = [AdminOnly]

    @action(detail=True, methods=["post"])
    def check(self, request, pk=None):
        bot = self.get_object()
        try:
            me = Client(decrypt(bot.token_enc)).get_me()
        except TelegramError as e:
            return Response({"ok": False, "error": str(e)})
        Bot.objects.filter(pk=bot.pk).update(username=me.get("username", ""), tg_id=me.get("id"))
        return Response({"ok": True, "username": me.get("username"), "name": me.get("first_name"),
                         "can_read_all_group_messages": me.get("can_read_all_group_messages")})


# ====================================================================== guruhlar
class GroupSerializer(serializers.ModelSerializer):
    bot_name = serializers.CharField(source="bot.name", read_only=True)
    effective_mode = serializers.CharField(read_only=True)
    questions_7d = serializers.IntegerField(read_only=True)

    class Meta:
        model = Group
        fields = ["id", "bot", "bot_name", "chat_id", "title", "mode", "effective_mode", "is_active", "is_admin",
                  "joined_at", "last_message_at", "questions_7d"]
        read_only_fields = ["bot", "chat_id", "title", "is_admin", "joined_at", "last_message_at"]


class GroupViewSet(ZonaViewSet):
    serializer_class = GroupSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        return [AdminOnly()] if self.request.method == "PATCH" else [CanView()]

    def get_queryset(self):
        since = timezone.now() - timezone.timedelta(days=7)
        return Group.objects.select_related("bot").annotate(
            questions_7d=Count("messages", filter=Q(messages__kind=Message.QUESTION, messages__created_at__gte=since)))


# ====================================================================== bilim bazasi
def _clean_list(value, limit=50, size=1000):
    if not isinstance(value, list):
        raise serializers.ValidationError("Ro'yxat bo'lishi kerak.")
    return list(dict.fromkeys(str(x).strip()[:size] for x in value if str(x).strip()))[:limit]


class VersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntryVersion
        fields = ["id", "title", "questions", "triggers", "extract", "answer", "answer_ru", "editor", "note", "at"]


class EntrySerializer(serializers.ModelSerializer):
    zone_name = serializers.CharField(source="zone.name", read_only=True, default="")
    responsible_name = serializers.CharField(source="responsible.name", read_only=True, default="")

    class Meta:
        model = Entry
        fields = ["id", "kind", "title", "questions", "triggers", "extract", "answer", "answer_ru", "zone", "zone_name",
                  "responsible", "responsible_name", "status", "source", "priority", "pending", "author",
                  "approved_by", "approved_at", "uses", "likes", "dislikes", "last_used_at", "created_at", "updated_at"]
        read_only_fields = ["status", "source", "priority", "pending", "author", "approved_by", "approved_at", "uses",
                            "likes", "dislikes", "last_used_at", "created_at", "updated_at"]

    def validate_questions(self, v):
        return _clean_list(v)

    def validate_triggers(self, v):
        return _clean_list(v, 30, 300)

    def validate_extract(self, v):
        import re
        out = _clean_list(v, 10, 300)
        for p in out:
            try:
                re.compile(p)
            except re.error as e:
                raise serializers.ValidationError(f"Regex xato: {p} ({e})") from e
        return out

    def validate(self, attrs):
        if not str(attrs.get("answer", getattr(self.instance, "answer", "")) or "").strip():
            raise serializers.ValidationError({"answer": "Javob matni bo'sh bo'lmasin."})
        return attrs


EDITABLE = ("title", "questions", "triggers", "extract", "answer", "answer_ru")


class EntryViewSet(ZonaViewSet):
    serializer_class = EntrySerializer
    permission_classes = [CanView]  # viewer ham taklif qila oladi; tasdiqlash — editor

    def get_queryset(self):
        qs = Entry.objects.select_related("zone", "responsible")
        p = self.request.query_params
        if p.get("status") and p["status"] != "all":
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("kind"):
            qs = qs.filter(kind=p["kind"])
        if p.get("source"):
            qs = qs.filter(source=p["source"])
        if p.get("pending") == "1":
            qs = qs.filter(pending__isnull=False)
        if p.get("q"):
            q = p["q"]
            qs = qs.filter(Q(title__icontains=q) | Q(answer__icontains=q) | Q(questions__icontains=q))
        return qs

    def retrieve(self, request, *args, **kwargs):
        e = self.get_object()
        return Response({**EntrySerializer(e).data, "versions": VersionSerializer(e.versions.all()[:50], many=True).data,
                         "messages": [{"id": m.id, "text": m.text[:300], "at": m.created_at, "status": m.status}
                                      for m in e.messages.order_by("-created_at")[:20]]})

    def perform_create(self, serializer):
        editor = _can_edit(self.request)
        approve_now = editor and self.request.data.get("approve")
        serializer.save(author=_actor(self.request), source="manual",
                        status=Entry.APPROVED if approve_now else Entry.REVIEW if editor else Entry.NEW,
                        approved_by=_actor(self.request) if approve_now else "",
                        approved_at=timezone.now() if approve_now else None)

    def perform_update(self, serializer):
        e = serializer.instance
        data = serializer.validated_data
        changes = {f: data[f] for f in EDITABLE if f in data and data[f] != getattr(e, f)}
        meta = {k: v for k, v in data.items() if k not in EDITABLE}
        if e.status == Entry.APPROVED and changes and not _can_edit(self.request):
            # tasdiqlangan javob: tahrir tasdiq kutadi, bot eski javobni ishlatishda davom etadi
            e.pending = {**(e.pending or {}), **changes, "by": _actor(self.request), "at": timezone.now().isoformat()}
            for k, v in meta.items():
                setattr(e, k, v)
            e.save()
            return
        if changes and e.status == Entry.APPROVED:
            runner.snapshot(e, _actor(self.request), "tahrir")
        serializer.save()

    def perform_destroy(self, instance):
        if not has_role(self.request, Profile.ADMIN):
            raise serializers.ValidationError("O'chirish faqat administrator uchun. Arxivlash mumkin.")
        instance.delete()

    def _editor_only(self):
        if not _can_edit(self.request):
            return Response({"detail": "Tasdiqlash uchun muharrir (editor) huquqi kerak."}, status=status.HTTP_403_FORBIDDEN)
        return None

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._editor_only() or Response(EntrySerializer(runner.approve(self.get_object(), _actor(request))).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._editor_only() or Response(EntrySerializer(runner.reject(self.get_object(), _actor(request))).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        if (denied := self._editor_only()):
            return denied
        e = self.get_object()
        e.status = Entry.ARCHIVED
        e.save(update_fields=["status", "updated_at"])
        return Response(EntrySerializer(e).data)

    @action(detail=True, methods=["post"], url_path="revert/(?P<vid>[0-9]+)")
    def revert(self, request, pk=None, vid=None):
        if (denied := self._editor_only()):
            return denied
        e = self.get_object()
        v = e.versions.filter(pk=vid).first()
        if not v:
            return Response({"detail": "Versiya topilmadi"}, status=404)
        runner.snapshot(e, _actor(request), f"#{v.id} versiyaga qaytarildi")
        for f in EDITABLE:
            setattr(e, f, getattr(v, f))
        e.save()
        return Response(EntrySerializer(e).data)

    @action(detail=True, methods=["post"])
    def merge(self, request, pk=None):
        """Bu yozuvni boshqasiga birlashtirish: savollari qo'shiladi, o'zi arxivga tushadi."""
        if (denied := self._editor_only()):
            return denied
        e = self.get_object()
        target = Entry.objects.filter(pk=request.data.get("target")).exclude(pk=e.pk).first()
        if not target:
            return Response({"detail": "Qaysi yozuvga birlashtirish kerak?"}, status=400)
        runner.snapshot(target, _actor(request), f"#{e.id} birlashtirildi")
        target.questions = list(dict.fromkeys([*(target.questions or []), e.title, *(e.questions or [])]))[:50]
        target.save()
        e.status = Entry.ARCHIVED
        e.save(update_fields=["status", "updated_at"])
        return Response(EntrySerializer(target).data)

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        if (denied := self._editor_only()):
            return denied
        act = request.data.get("action")
        done = 0
        for e in Entry.objects.filter(pk__in=request.data.get("ids") or []):
            if act == "approve":
                runner.approve(e, _actor(request))
            elif act == "reject":
                runner.reject(e, _actor(request))
            elif act == "archive":
                e.status = Entry.ARCHIVED
                e.save(update_fields=["status", "updated_at"])
            else:
                continue
            done += 1
        return Response({"done": done})

    @action(detail=False, methods=["post"])
    def test(self, request):
        """Panelda sinab ko'rish: matn -> bot qaysi javobni tanlardi (tasdiqlanmaganlar bilan ham)."""
        text = str(request.data.get("text") or "").strip()[:3000]
        if len(text) < 3:
            return Response({"detail": "Matn kiriting"}, status=400)
        lang = detect_lang(text)
        d = decide(text, lang, allow_unapproved=bool(request.data.get("all")))
        return Response({"stage": d.stage, "confidence": d.confidence, "text": d.text, "needs_human": d.needs_human,
                         "entry": d.entry.id if d.entry else None, "entry_title": d.entry.title if d.entry else "",
                         "unapproved": d.unapproved, "fields": d.fields, "responsible": d.responsible, "note": d.note,
                         "lang": lang})


# ====================================================================== savollar
class MessageSerializer(serializers.ModelSerializer):
    group_title = serializers.CharField(source="group.title", read_only=True, default="")
    user_name = serializers.CharField(source="user.name", read_only=True, default="")
    user_username = serializers.CharField(source="user.username", read_only=True, default="")
    entry_title = serializers.CharField(source="entry.title", read_only=True, default="")
    has_photo = serializers.SerializerMethodField()
    staff_answers = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ["id", "group", "group_title", "user_name", "user_username", "text", "ocr_text", "has_photo", "lang",
                  "status", "stage", "entry", "entry_title", "confidence", "answer_text", "answered_by", "feedback",
                  "created_at", "answered_at", "staff_answers"]

    def get_has_photo(self, obj):
        return bool(obj.photo_file_id)

    def get_staff_answers(self, obj):
        return [{"by": (r.user.staff_name() if r.user else ""), "text": r.text[:1000], "at": r.created_at}
                for r in obj.staff_replies.all()]


class MessageViewSet(ZonaViewSet):
    serializer_class = MessageSerializer
    permission_classes = [CanView]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = (Message.objects.filter(kind=Message.QUESTION)
              .select_related("group", "user", "entry").prefetch_related("staff_replies__user__member",
                                                                          "staff_replies__user__contact"))
        p = self.request.query_params
        if p.get("status") and p["status"] != "all":
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("group"):
            qs = qs.filter(group_id=p["group"])
        if p.get("stage"):
            qs = qs.filter(stage=p["stage"])
        if p.get("q"):
            qs = qs.filter(Q(text__icontains=p["q"]) | Q(ocr_text__icontains=p["q"]))
        return qs

    def list(self, request, *args, **kwargs):
        limit = min(int(request.query_params.get("limit") or 200), 500)
        return Response(MessageSerializer(self.get_queryset()[:limit], many=True).data)

    def create(self, request, *args, **kwargs):
        return Response(status=405)

    @action(detail=True, methods=["post"])
    def answer(self, request, pk=None):
        """Xodim paneldan javob yozadi: bot uni guruhga savolga reply qilib yuboradi; javob bazaga nomzod bo'ladi."""
        q = Message.objects.select_related("bot", "group").get(pk=pk)
        text = str(request.data.get("text") or "").strip()
        if len(text) < 2:
            return Response({"detail": "Javob matnini yozing"}, status=400)
        who = _actor(request)
        body = f"👤 <b>{to_html(who)}</b>:\n{to_html(text)}"
        try:
            sent = Client(decrypt(q.bot.token_enc)).send(q.chat_id, body, reply_to=q.message_id)
        except TelegramError as e:
            return Response({"detail": f"Telegram: {e}"}, status=502)
        q.status, q.stage, q.answered_by, q.answered_at = Message.ANSWERED, "panel", who, timezone.now()
        q.answer_text = text
        q.bot_reply_id = sent.get("message_id")
        q.save()
        entry = None
        if request.data.get("save", True):
            entry = runner.learn(q, text, who)
            if entry:
                entry.source = "panel"
                if _can_edit(request) and request.data.get("approve"):
                    runner.approve(entry, who)
                entry.save()
        return Response({"ok": True, "entry": entry.id if entry else None})

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        Message.objects.filter(pk=pk).update(status=Message.CLOSED)
        return Response({"ok": True})


# ====================================================================== statistika va xodimlar
@zona_api(["GET"], [CanView])
def stats(request):
    since = timezone.now() - timezone.timedelta(days=int(request.query_params.get("days") or 7))
    qs = Message.objects.filter(kind=Message.QUESTION, created_at__gte=since)
    by_status = dict(qs.values_list("status").annotate(c=Count("id")))
    by_stage = dict(qs.exclude(stage="").values_list("stage").annotate(c=Count("id")))
    entries = dict(Entry.objects.values_list("status").annotate(c=Count("id")))
    top = list(Entry.objects.filter(status=Entry.APPROVED, uses__gt=0).order_by("-uses")
               .values("id", "title", "uses", "likes", "dislikes")[:10])
    bots = [{"id": b.id, "name": b.name, "username": b.username, "enabled": b.enabled, "mode": b.mode,
             "last_ok_at": b.last_ok_at, "last_error": b.last_error, "admin_chat": bool(b.admin_chat_id)}
            for b in Bot.objects.all()]
    return Response({"total": qs.count(), "by_status": by_status, "by_stage": by_stage, "entries": entries,
                     "pending_edits": Entry.objects.filter(pending__isnull=False).count(),
                     "top": top, "bots": bots, "modes": dict(MODES)})


@zona_api(["GET"], [CanView])
def staff(request):
    """Bot taniydigan xodimlar: Telegram'i bor xodimlar va jamoa a'zolari (javoblaridan o'rganiladi)."""
    out = [{"type": "member", "id": m.id, "name": m.name, "role": m.role, "level": m.level, "telegram": m.telegram,
            "phone": m.phone, "team": ""} for m in Member.objects.filter(is_team=False).exclude(telegram="")]
    out += [{"type": "contact", "id": c.id, "name": c.name, "role": c.role or c.member.role, "level": c.member.level,
             "telegram": c.telegram, "phone": c.phone, "team": c.member.name, "linked": bool(c.telegram_id)}
            for c in TeamContact.objects.select_related("member")]
    return Response(out)
