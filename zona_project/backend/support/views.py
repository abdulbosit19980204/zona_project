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
from .models import (MODES, AIJob, Bot, Entry, EntryVersion, Group, HistoryJob, Media, Message, Settings,
                     Suggestion, TgUser)
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
                   "learn_from_staff", "ocr_enabled", "media_days", "signature", "drafts_to_admin", "escalation_ack",
                   "mention_responsible", "feedback_buttons", "notify_candidates", "learn_clarifications",
                   "ask_first_prompt", "history_days", "history_photos", "history_max", "image_match",
                   "image_threshold", "image_autolabel", "mention_asker", "mention_supervisor", "workers",
                   "contact_lookup", "ai_primary", "ai_primary_below", "album_window",
                   "tasks_enabled", "task_bot", "task_default_assignee", "task_departments", "task_members",
                   "task_daily_limit", "task_gap", "task_attach", "task_mode", "task_remind_group", "task_remind_dm",
                   "merge_window"]


def _settings_payload(s):
    import json

    from zona.ai import service as ai

    from . import history
    pending = json.loads(decrypt(s.mtproto_pending_enc) or "{}")
    return {**{f: getattr(s, f) for f in SETTINGS_FIELDS}, "api_hash": mask(decrypt(s.api_hash_enc)),
            "has_api_hash": bool(s.api_hash_enc), "ocr_available": ocr.available(), "ocr_languages": ocr.languages(),
            "ai_ready": bool(ai.status().get("support")), "ai_quota_left": ai_quota_left(s),
            "mtproto_available": history.available(), "mtproto_connected": bool(s.mtproto_session_enc),
            "mtproto_user": s.mtproto_user, "mtproto_pending": bool(pending),
            "mtproto_need_password": bool(pending.get("need_password")),
            "mtproto_phone": (pending.get("phone", "")[:5] + "•••" + pending.get("phone", "")[-2:]) if pending else ""}


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
    attachments_info = serializers.SerializerMethodField()
    image_examples_count = serializers.SerializerMethodField()

    def get_attachments_info(self, obj):
        files = {m.id: m for m in Media.objects.filter(id__in=obj.attachments or [])}
        return [media_dict(files[i]) for i in obj.attachments or [] if i in files]

    def get_image_examples_count(self, obj):
        return obj.image_examples.count()

    def validate_attachments(self, v):
        if not isinstance(v, list):
            raise serializers.ValidationError("Ro'yxat bo'lishi kerak.")
        ids = [int(x) for x in v][:10]
        if Media.objects.filter(id__in=ids).count() != len(set(ids)):
            raise serializers.ValidationError("Fayl topilmadi.")
        return list(dict.fromkeys(ids))

    class Meta:
        model = Entry
        fields = ["id", "kind", "title", "questions", "triggers", "extract", "answer", "answer_ru", "ask_first",
                  "attachments", "attachments_info", "image_examples_count", "zone", "zone_name", "creates_task", "task_assignee",
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


VERSIONED = ("title", "questions", "triggers", "extract", "answer", "answer_ru")
EDITABLE = (*VERSIONED, "ask_first", "attachments")


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
        if p.get("approved_since"):  # oxirgi N soatda tasdiqlanganlar (qayta tekshirish uchun)
            qs = qs.filter(approved_at__gte=timezone.now() - timezone.timedelta(hours=int(p["approved_since"])))
        if p.get("approved_by"):
            qs = qs.filter(approved_by=p["approved_by"])
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
        for f in VERSIONED:
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

    # ---------------------------------------------------------------- takrorlar
    @action(detail=False, methods=["get"])
    def duplicates(self, request):
        """O'xshash yozuvlar guruhlari, har birida eng yaxshi (qoldiriladigan) yozuv belgilangan."""
        from .dedupe import find_groups
        th = max(50, min(98, int(request.query_params.get("threshold") or 75)))
        groups = find_groups(th)
        return Response({"threshold": th, "groups": groups[:150], "total": len(groups),
                         "entries": sum(len(g["entries"]) for g in groups)})

    @action(detail=False, methods=["post"], url_path="dedupe-merge")
    def dedupe_merge(self, request):
        """Guruhni birlashtirish: keep qoladi (kerak bo'lsa yangi javob bilan), merge'dagilar arxivga tushadi."""
        if (denied := self._editor_only()):
            return denied
        from .dedupe import merge_group
        d = request.data
        if not Entry.objects.filter(pk=d.get("keep")).exists():
            return Response({"detail": "Qoldiriladigan yozuvni tanlang."}, status=400)
        keep, n = merge_group(int(d["keep"]), [int(x) for x in d.get("merge") or []], _actor(request),
                              answer=d.get("answer") or None, answer_ru=d.get("answer_ru") or None, title=d.get("title") or None)
        return Response({"entry": EntrySerializer(keep).data, "merged": n})

    @action(detail=False, methods=["post"], url_path="dedupe-auto")
    def dedupe_auto(self, request):
        """Deyarli bir xil takrorlarni avtomatik eng yaxshisiga birlashtirish (dry_run — faqat sanash)."""
        if (denied := self._editor_only()):
            return denied
        from .dedupe import auto_clean
        th = max(85, min(100, int(request.data.get("threshold") or 92)))
        return Response(auto_clean(_actor(request), th, dry_run=bool(request.data.get("dry_run"))))

    @action(detail=False, methods=["post"], url_path="dedupe-compose")
    def dedupe_compose(self, request):
        """AI: guruhdan eng yaxshi yozuvni tanlash va optimal javob yozish (hech narsa saqlanmaydi — faqat taklif)."""
        from zona.ai import service as ai

        from .ai_review import ai_merge_groups
        ids = [int(x) for x in request.data.get("ids") or []][:8]
        rows = list(Entry.objects.filter(pk__in=ids))
        if len(rows) < 2:
            return Response({"detail": "Kamida ikkita yozuv kerak."}, status=400)
        if not ai.status().get("support"):
            return Response({"detail": "AI sozlanmagan."}, status=400)
        try:
            res = ai_merge_groups([rows])
        except Exception as e:  # noqa: BLE001
            return Response({"detail": str(e)[:300]}, status=503)
        if not res:
            return Response({"detail": "AI javob bermadi, qayta urinib ko'ring."}, status=503)
        return Response(res[0])

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
            elif act == "review":  # tasdiqni bekor qilish: bot ishlatmaydi, tasdiqlash navbatiga qaytadi
                if e.status != Entry.APPROVED:
                    continue
                e.status = Entry.REVIEW
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
    media = serializers.SerializerMethodField()
    link = serializers.SerializerMethodField()
    task = serializers.SerializerMethodField()

    def get_task(self, obj):
        t = getattr(obj, "task", None)
        return {"id": t.id, "status": t.status, "assignee": t.assignee, "reply": t.reply[:300], "error": t.error} if t else None

    def get_media(self, obj):
        return [media_dict(m) for m in obj.media.all()]

    def get_link(self, obj):
        return obj.group.message_link(obj.message_id) if obj.group_id else ""

    class Meta:
        model = Message
        fields = ["id", "group", "group_title", "user_name", "user_username", "text", "ocr_text", "has_photo", "media", "link", "lang",
                  "status", "stage", "entry", "entry_title", "confidence", "answer_text", "answered_by", "feedback",
                  "created_at", "answered_at", "staff_answers", "task"]

    def get_has_photo(self, obj):
        return bool(obj.photo_file_id)

    def get_staff_answers(self, obj):
        """Zanjir: aniqlashtirish (clarify), savol egasining ma'lumoti (info), xodimning yakuniy javobi (staff)."""
        return [{"by": (r.user.staff_name() if r.user else ""), "text": r.text[:1000], "at": r.created_at, "kind": r.kind,
                 "ocr": r.ocr_text[:500], "media": [media_dict(m) for m in r.media.all()]}
                for r in sorted(obj.staff_replies.all(), key=lambda r: r.created_at)]


class MessageViewSet(ZonaViewSet):
    serializer_class = MessageSerializer
    permission_classes = [CanView]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = (Message.objects.filter(kind=Message.QUESTION).exclude(stage="dup")
              .select_related("group", "user", "entry").prefetch_related("media", "staff_replies__media",
                                                                          "staff_replies__user__member",
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
            asks = "\n".join(q.staff_replies.filter(kind=Message.CLARIFY).values_list("text", flat=True))
            entry, new = runner.learn(q, text, who, ask_first=asks, source="panel")
            if entry and _can_edit(request) and request.data.get("approve") and entry.status != Entry.APPROVED:
                runner.approve(entry, who)
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


# ====================================================================== Telegram akkaunt (guruh tarixi uchun)
def _mt_error(e):
    from . import history
    if isinstance(e, history.NeedPassword):
        return Response({"need_password": True, "detail": "Akkauntda 2FA yoqilgan — parolni kiriting."}, status=200)
    return Response({"detail": f"{type(e).__name__}: {e}"[:300]}, status=400)


@zona_api(["POST"], [AdminOnly])
def mtproto_send_code(request):
    from . import history
    if not request.data.get("confirm"):
        return Response({"detail": "Ogohlantirishni o'qib, rozilik belgisini qo'ying."}, status=400)
    phone = str(request.data.get("phone") or "").strip().replace(" ", "")
    if not phone.startswith("+") or len(phone) < 10:
        return Response({"detail": "Telefon raqamini +998... ko'rinishida kiriting."}, status=400)
    try:
        history.send_code(phone)
    except Exception as e:  # noqa: BLE001
        return _mt_error(e)
    return Response(_settings_payload(Settings.load()))


@zona_api(["POST"], [AdminOnly])
def mtproto_sign_in(request):
    from . import history
    try:
        history.sign_in(str(request.data.get("code") or "").strip(), str(request.data.get("password") or ""))
    except Exception as e:  # noqa: BLE001
        return _mt_error(e)
    return Response(_settings_payload(Settings.load()))


@zona_api(["POST"], [AdminOnly])
def mtproto_logout(request):
    from . import history
    history.logout()
    return Response(_settings_payload(Settings.load()))


# ====================================================================== guruh tarixini o'rganish
def _job(j):
    return {"id": j.id, "group": j.group_id, "group_title": j.group.title, "days": j.days, "photos": j.photos,
            "status": j.status, "progress": j.progress, "error": j.error, "created_by": j.created_by,
            "created_at": j.created_at, "started_at": j.started_at, "finished_at": j.finished_at}


@zona_api(["GET", "POST"], [AdminOnly])
def history_jobs(request):
    if request.method == "POST":
        s = Settings.load()
        if not s.mtproto_session_enc:
            return Response({"detail": "Avval Telegram akkauntni ulang."}, status=400)
        group = Group.objects.filter(pk=request.data.get("group")).first()
        if not group:
            return Response({"detail": "Guruhni tanlang."}, status=400)
        if HistoryJob.objects.filter(group=group, status__in=[HistoryJob.QUEUED, HistoryJob.RUNNING]).exists():
            return Response({"detail": "Bu guruh tarixi allaqachon o'qilmoqda."}, status=400)
        # akkaunt xavfsizligi: Telegram ko'p so'rovni yoqtirmaydi — bitta guruh 6 soatda bir marta, sutkada 3 tadan ko'p emas
        now = timezone.now()
        if HistoryJob.objects.filter(group=group, created_at__gte=now - timezone.timedelta(hours=6)).exists():
            return Response({"detail": "Bu guruh tarixi yaqinda o'qilgan. Akkaunt xavfsizligi uchun 6 soatdan keyin qayta urining."}, status=400)
        if HistoryJob.objects.filter(created_at__gte=now - timezone.timedelta(days=1)).count() >= 3:
            return Response({"detail": "Sutkalik chegara (3 ta) tugadi — ertaga davom eting."}, status=400)
        days = max(1, min(int(request.data.get("days") or s.history_days), 365))
        photos = bool(request.data.get("photos", s.history_photos))
        HistoryJob.objects.create(group=group, days=days, photos=photos, created_by=_actor(request))
    return Response([_job(j) for j in HistoryJob.objects.select_related("group")[:30]])


# ====================================================================== tahlil: xodimlar javoblari va aniqlashtirishlar
@zona_api(["GET"], [CanView])
def analytics(request):
    from collections import Counter, defaultdict
    from statistics import median

    from .engine import tokens_text
    days = max(1, min(int(request.query_params.get("days") or 30), 365))
    since = timezone.now() - timezone.timedelta(days=days)
    msgs = Message.objects.filter(created_at__gte=since)
    questions = msgs.filter(kind=Message.QUESTION)

    # xodimlar: kim nechta savolga javob berdi, qanchalik tez, qancha ishladi
    per = defaultdict(lambda: {"answers": 0, "clarifications": 0, "times": [], "groups": set(), "questions": set(),
                               "days": set(), "topics": Counter(), "last": None, "user": None})
    for r in (msgs.filter(kind__in=[Message.STAFF, Message.CLARIFY], user__isnull=False)
              .select_related("user__member", "user__contact", "question__entry", "group")):
        name = r.user.staff_name()
        row = per[name]
        row["user"] = row["user"] or r.user
        row["groups"].add(r.group.title if r.group else "")
        row["days"].add(timezone.localtime(r.created_at).date())
        row["last"] = max(row["last"], r.created_at) if row["last"] else r.created_at
        if r.kind == Message.CLARIFY:
            row["clarifications"] += 1
        else:
            row["answers"] += 1
            if r.question_id:
                row["questions"].add(r.question_id)
                row["times"].append(max(0.0, (r.created_at - r.question.created_at).total_seconds() / 60))
                if r.question.entry_id:
                    row["topics"][r.question.entry.title] += 1
    panel = Counter(questions.filter(stage="panel").values_list("answered_by", flat=True))
    authored = defaultdict(Counter)
    for author, st in Entry.objects.filter(source__in=["staff", "history", "panel"]).values_list("author", "status"):
        authored[author][st] += 1
    total_answers = sum(r["answers"] for r in per.values()) + sum(panel.values()) or 1
    staff = []
    for name in set(per) | set(panel):
        r = per[name]
        a = authored.get(name, Counter())
        answers = r["answers"] + panel.get(name, 0)
        u = r["user"]
        staff.append({"name": name, "answers": answers, "panel": panel.get(name, 0), "clarifications": r["clarifications"],
                      "questions": len(r["questions"]) + panel.get(name, 0),
                      "share": round(100 * answers / total_answers),
                      "median_minutes": round(median(r["times"]), 1) if r["times"] else None,
                      "avg_minutes": round(sum(r["times"]) / len(r["times"]), 1) if r["times"] else None,
                      "active_days": len(r["days"]), "per_day": round(answers / max(1, len(r["days"])), 1),
                      "messages": u.msg_count if u else 0, "last": r["last"],
                      "groups": sorted(g for g in r["groups"] if g),
                      "topics": [{"title": t, "n": n} for t, n in r["topics"].most_common(3)],
                      "candidates": sum(a.values()), "approved": a.get(Entry.APPROVED, 0),
                      "rejected": a.get(Entry.REJECTED, 0)})
    staff.sort(key=lambda x: -x["answers"])

    # qanday ma'lumot so'raladi (aniqlashtirishlar)
    asks = Counter()
    samples = {}
    for t in msgs.filter(kind=Message.CLARIFY).values_list("text", flat=True):
        key = tokens_text(t)
        if key:
            asks[key] += 1
            samples.setdefault(key, t[:200])
    top_asks = [{"text": samples[k], "count": c} for k, c in asks.most_common(15)]

    # savollar: kunlar, guruhlar, bosqichlar, javobsizlar
    daily = defaultdict(lambda: {"total": 0, "bot": 0, "staff": 0})
    for created, stage in questions.values_list("created_at", "stage"):
        d = daily[timezone.localtime(created).date().isoformat()]
        d["total"] += 1
        if stage in ("template", "faq", "rule", "ai"):
            d["bot"] += 1
        elif stage in ("staff", "panel"):
            d["staff"] += 1
    groups = list(questions.values("group__title").annotate(n=Count("id")).order_by("-n")[:15])
    unanswered = questions.exclude(status__in=[Message.ANSWERED, Message.CLOSED, Message.IGNORED]).count()
    return Response({
        "days": days, "questions": questions.count(), "unanswered": unanswered,
        "by_source": dict(questions.values_list("source").annotate(c=Count("id"))),
        "by_stage": dict(questions.exclude(stage="").values_list("stage").annotate(c=Count("id"))),
        "staff": staff, "top_asks": top_asks,
        "daily": [{"date": k, **v} for k, v in sorted(daily.items())],
        "groups": [{"title": g["group__title"] or "—", "n": g["n"]} for g in groups],
        "with_photo": questions.exclude(photo_file_id="").count(),
        "entries_with_ask_first": Entry.objects.exclude(ask_first="").count(),
        "zones": _zones(questions),
        "askers": _askers(questions),
        "top_types": [{"entry": r["entry"], "title": r["entry__title"], "n": r["n"]} for r in
                      questions.filter(entry__isnull=False).values("entry", "entry__title").annotate(n=Count("id")).order_by("-n")[:20]],
        "protarget": _protarget(questions, since),
        "images": {"total": Media.objects.filter(kind=Media.PHOTO).count(),
                   "labeled": Media.objects.filter(kind=Media.PHOTO, label__isnull=False).count(),
                   "types": Media.objects.filter(kind=Media.PHOTO, label__isnull=False).values("label").distinct().count(),
                   "by_image": questions.filter(stage="image").count()},
    })


@zona_api(["GET"], [CanView])
def analytics_workload(request):
    """Ish yuklamasi: soat × hafta kuni, haftalar, guruhlar, savol turlari, xodimlarning ish soatlari va javob tezligi."""
    from .workload import workload
    days = max(1, min(int(request.query_params.get("days") or 30), 365))
    return Response(workload(days))


@zona_api(["GET"], [CanView])
def analytics_speed(request):
    """Bot tezligi: savoldan javobgacha soniyalar, bosqichlar, soatlar, eng sekin savollar."""
    from .workload import speed
    days = max(1, min(int(request.query_params.get("days") or 7), 90))
    return Response(speed(days))


def _askers(questions):
    """Savol beruvchilar: kim nechta savol bergan, bot nechtasiga javob bergan, eng ko'p savol turlari."""
    from collections import Counter, defaultdict
    rows = defaultdict(lambda: {"questions": 0, "bot": 0, "escalated": 0, "types": Counter(), "groups": set(), "last": None})
    for uid, name, uname, sp, stage, status, title, group, at in questions.filter(user__isnull=False).values_list(
            "user_id", "user__name", "user__username", "user__staff_person__name", "stage", "status", "entry__title",
            "group__title", "created_at"):
        r = rows[uid]
        r.update(name=name, username=uname, staff=sp or "")
        r["questions"] += 1
        r["bot"] += stage in ("template", "faq", "rule", "ai", "image")
        r["escalated"] += status == Message.ESCALATED
        if title:
            r["types"][title] += 1
        if group:
            r["groups"].add(group)
        r["last"] = max(r["last"], at) if r["last"] else at
    out = [{"user": uid, "name": r["name"], "username": r["username"], "staff_person": r["staff"], "questions": r["questions"],
            "bot": r["bot"], "escalated": r["escalated"], "groups": sorted(r["groups"]), "last": r["last"],
            "top_types": [{"title": t, "n": n} for t, n in r["types"].most_common(3)]} for uid, r in rows.items()]
    return sorted(out, key=lambda x: -x["questions"])[:100]


def _zones(questions):
    """Savollar zonalar bo'yicha (topilgan yozuvning zonasi yoki mas'uli orqali)."""
    out = {}
    for zone, resp in questions.filter(entry__isnull=False).values_list("entry__zone__name", "entry__responsible__name"):
        key = zone or ("ProTarget va mobil ilova" if resp == "Pro-target" else "Boshqa")
        out[key] = out.get(key, 0) + 1
    return out


def _protarget(questions, since):
    """Pro-target'ga tegishli savollar: turlari, javobsizlari va Pro-target jamoasi javoblari."""
    from collections import Counter
    from statistics import median

    from zona.models import TeamContact
    pt = questions.filter(Q(entry__responsible__name="Pro-target") | Q(entry__zone__name="ProTarget va mobil ilova")
                          | Q(entry__title__istartswith="ProTarget"))
    types = Counter(pt.values_list("entry__title", flat=True))
    team = set(TeamContact.objects.filter(member__name="Pro-target").values_list("name", flat=True))
    times = [max(0.0, (r.created_at - r.question.created_at).total_seconds() / 60)
             for r in Message.objects.filter(kind=Message.STAFF, created_at__gte=since, question__isnull=False)
             .select_related("user__contact", "user__member", "question") if r.user and r.user.staff_name() in team]
    return {"questions": pt.count(), "by_bot": pt.filter(stage__in=["template", "faq", "rule", "ai", "image"]).count(),
            "unanswered": pt.exclude(status__in=[Message.ANSWERED, Message.CLOSED, Message.IGNORED]).count(),
            "types": [{"title": t, "n": n} for t, n in types.most_common(10)],
            "team_answers": len(times), "team_median_minutes": round(median(times), 1) if times else None}


# ====================================================================== fayllar va rasm turlari (o'rgatish)
def media_dict(m):
    return {"id": m.id, "kind": m.kind, "name": m.name, "mime": m.mime, "size": m.size, "width": m.width, "height": m.height,
            "label": m.label_id, "label_title": m.label.title if m.label_id else "", "label_auto": m.label_auto,
            "ocr": (m.ocr_text or "")[:300], "source": m.source, "created_at": m.created_at, "available": bool(m.path)}


def upload_api(fn):
    from rest_framework.decorators import (api_view, authentication_classes, parser_classes, permission_classes,
                                           renderer_classes)
    from rest_framework.parsers import FormParser, MultiPartParser
    from rest_framework.renderers import JSONRenderer

    from zona.auth import AUTHENTICATION
    fn = authentication_classes(AUTHENTICATION)(fn)
    fn = permission_classes([ReadOrEdit])(fn)
    fn = renderer_classes([JSONRenderer])(fn)
    fn = parser_classes([MultiPartParser, FormParser])(fn)
    return api_view(["POST"])(fn)


MAX_UPLOAD = 45 * 1024 * 1024  # Telegram bot fayl yuborish chegarasi ~50 MB


@upload_api
def media_upload(request):
    """Javob biriktirmasi (rasm, video, fayl) yoki o'rgatish namunasi (rasm). Bir nechta fayl bo'lishi mumkin."""
    from . import ocr, vision
    out = []
    for f in request.FILES.getlist("files") or request.FILES.getlist("file"):
        if f.size > MAX_UPLOAD:
            return Response({"detail": f"{f.name}: fayl juda katta (≤45 MB)."}, status=400)
        mime = f.content_type or ""
        kind = request.data.get("kind") or ("photo" if mime.startswith("image/") else "video" if mime.startswith("video/")
                                            else "document")
        data = f.read()
        m = vision.store(data, kind=kind, name=f.name, mime=mime, source=request.data.get("source") or "answer")
        label = request.data.get("label")
        if label and kind == Media.PHOTO:
            e = Entry.objects.filter(pk=label).first()
            if e:
                if Settings.load().ocr_enabled:
                    Media.objects.filter(pk=m.pk).update(ocr_text=ocr.read_text(data))
                vision.label([m], e, _actor(request))
                m.refresh_from_db()
        out.append(media_dict(m))
    if not out:
        return Response({"detail": "Fayl tanlang."}, status=400)
    return Response(out)


@zona_api(["GET"], [CanView])
def media_file(request, pk):
    from django.http import FileResponse, Http404
    m = Media.objects.filter(pk=pk).first()
    if not m or not m.path:
        raise Http404
    try:
        fh = open(m.path, "rb")
    except OSError as e:
        raise Http404 from e
    return FileResponse(fh, content_type=m.mime or ("image/jpeg" if m.kind == Media.PHOTO else "application/octet-stream"),
                        filename=m.name or None)


@zona_api(["GET"], [CanView])
def image_types(request):
    """Rasm turlari: o'rgatilgan namunalar (yozuv bo'yicha) va yorliqsiz rasmlar guruhlari."""
    from . import vision
    s = Settings.load()
    labeled = {}
    for m in Media.objects.filter(kind=Media.PHOTO, label__isnull=False).select_related("label").order_by("-created_at"):
        row = labeled.setdefault(m.label_id, {"entry": m.label_id, "title": m.label.title, "status": m.label.status,
                                              "count": 0, "auto": 0, "samples": []})
        row["count"] += 1
        row["auto"] += int(m.label_auto)
        if len(row["samples"]) < 4:
            row["samples"].append(media_dict(m))
    unl = (Media.objects.filter(kind=Media.PHOTO, label__isnull=True, ignored=False).exclude(dhash="").exclude(path="")
           .order_by("-created_at")[:600])
    ign = Media.objects.filter(kind=Media.PHOTO, ignored=True).exclude(path="").order_by("-created_at")[:300]
    ignored = [{"count": len(g), "ids": [m.id for m in g], "samples": [media_dict(m) for m in g[:4]]}
               for g in vision.clusters(list(ign), s.image_threshold)[:40]]
    groups = []
    for g in vision.clusters(list(unl), s.image_threshold)[:60]:
        guess, dist, _ = vision.match(g[0], s.image_threshold * 2, include_unapproved=True)
        groups.append({"count": len(g), "ids": [m.id for m in g], "samples": [media_dict(m) for m in g[:4]],
                       "ocr": next((m.ocr_text[:300] for m in g if m.ocr_text), ""),
                       "guess": guess.id if guess else None, "guess_title": guess.title if guess else ""})
    return Response({"labeled": sorted(labeled.values(), key=lambda r: -r["count"]), "unlabeled": groups, "ignored": ignored,
                     "threshold": s.image_threshold,
                     "total": Media.objects.filter(kind=Media.PHOTO).count()})


@zona_api(["POST"], [ReadOrEdit])
def image_label(request):
    """Rasmlarni yozuvga o'rgatish (entry=null — yorliqni olib tashlash)."""
    from . import vision
    ids = [int(x) for x in request.data.get("ids") or []][:1000]
    qs = Media.objects.filter(id__in=ids, kind=Media.PHOTO)
    entry_id = request.data.get("entry")
    if not entry_id:
        n = qs.update(label=None, label_auto=False, label_by=_actor(request))
        return Response({"done": n})
    e = Entry.objects.filter(pk=entry_id).first()
    if not e:
        return Response({"detail": "Yozuv topilmadi"}, status=400)
    return Response({"done": vision.label(qs, e, _actor(request))})


@zona_api(["POST"], [ReadOrEdit])
def image_ignore(request):
    """Noto'g'ri yuborilgan rasmlarni rad etish (ignored=true) yoki qaytarish (false). Rad etilgan rasm yorlig'idan ham ajraladi."""
    from . import vision
    ids = [int(x) for x in request.data.get("ids") or []][:1000]
    flag = bool(request.data.get("ignored", True))
    qs = Media.objects.filter(id__in=ids, kind=Media.PHOTO)
    n = qs.update(ignored=True, label=None, label_auto=False, label_by=_actor(request)) if flag else qs.update(ignored=False)
    vision._CACHE["key"] = None
    return Response({"done": n})


# ====================================================================== PRBC vazifalari
def _task_dict(t):
    m = t.message
    return {"id": t.id, "status": t.status, "assignee": t.assignee, "title": t.title, "text": t.text, "link": t.link,
            "reason": t.reason, "reply": t.reply, "error": t.error, "attempts": t.attempts, "files": len(t.media_ids or []),
            "duplicates": len(t.duplicates or []), "created_at": t.created_at, "sent_at": t.sent_at, "created_by": t.created_by,
            "post_id": t.post_id, "message": m.id if m else None, "asker": (m.user.name if m and m.user else ""),
            "group": (m.group.title if m and m.group_id else ""), "entry": t.entry_id, "entry_title": t.entry.title if t.entry_id else ""}


@zona_api(["GET"], [AdminOnly])
def support_tasks(request):
    from zona.models import Department, Member

    from .models import SupportTask
    qs = SupportTask.objects.select_related("message__user", "message__group", "entry")
    st = request.query_params.get("status")
    if st and st != "all":
        qs = qs.filter(status=st)
    since = timezone.now() - timezone.timedelta(days=1)
    return Response({
        "tasks": [_task_dict(t) for t in qs[:200]],
        "counts": {k: SupportTask.objects.filter(status=k).count() for k in ("queued", "sent", "failed", "skipped")},
        "sent_today": SupportTask.objects.filter(status="sent", sent_at__gte=since).count(),
        "entries_with_task": Entry.objects.filter(creates_task=True).count(),
        "departments": [{"id": d.id, "name": d.name} for d in Department.objects.order_by("name")],
        "members": [{"id": m.id, "name": m.name, "department": m.department.name if m.department_id else "", "telegram": m.telegram,
                     "is_team": m.is_team, "level": m.level} for m in Member.objects.select_related("department").order_by("name")],
    })


@zona_api(["POST"], [AdminOnly])
def support_task_action(request, pk, action):
    from .models import SupportTask
    t = SupportTask.objects.filter(pk=pk).first()
    if not t:
        return Response({"detail": "Topilmadi"}, status=404)
    if action == "retry":
        if request.data.get("assignee"):
            new = str(request.data["assignee"]).lstrip("@").strip()[:64]
            t.text = t.text.replace(f"/vazifa @{t.assignee}", f"/vazifa @{new}", 1) if t.assignee else f"/vazifa @{new} {t.title}"
            t.assignee = new
        t.status, t.attempts, t.error = SupportTask.QUEUED, 0, ""
        t.save()
    elif action == "skip":
        t.status = SupportTask.SKIPPED
        t.save(update_fields=["status"])
    else:
        return Response({"detail": "Noma'lum amal"}, status=400)
    return Response(_task_dict(t))


@zona_api(["POST"], [AdminOnly])
def support_task_test(request):
    from . import tasks
    try:
        t = tasks.test_task(_actor(request), request.data.get("assignee", ""))
    except ValueError as e:
        return Response({"detail": str(e)}, status=400)
    return Response(_task_dict(t))


# ====================================================================== Telegram foydalanuvchilar <-> kontaktlar
def _tg_user(u):
    from .engine import supervisor_of
    sp = u.staff_person
    sv = supervisor_of(u) if sp else None
    return {"id": u.id, "name": u.name, "username": u.username, "is_staff": u.is_staff,
            "staff_name": u.staff_name() if u.is_staff else "",
            "staff_person": sp.id if sp else None, "staff_person_name": sp.name if sp else "",
            "staff_person_role": sp.get_role_display() if sp else "", "project": sp.project.name if sp else "",
            "supervisor": sv.name if sv else "", "link": u.staff_link,
            "questions": u.messages.filter(kind=Message.QUESTION).count(), "last_seen": u.last_seen}


@zona_api(["GET"], [CanView])
def tg_users(request):
    qs = TgUser.objects.select_related("staff_person__project", "staff_person__manager__manager", "member", "contact")
    if request.query_params.get("unlinked") == "1":
        qs = qs.filter(staff_person__isnull=True, member__isnull=True, contact__isnull=True)
    return Response([_tg_user(u) for u in qs.order_by("-last_seen")[:500]])


@zona_api(["POST"], [ReadOrEdit])
def tg_user_link(request, pk):
    """Telegram foydalanuvchini kontaktlardagi dala xodimiga qo'lda bog'lash (null — bog'lamaslik, avtomatik ham qilinmaydi)."""
    from zona.models import StaffPerson
    u = TgUser.objects.filter(pk=pk).first()
    if not u:
        return Response({"detail": "Topilmadi"}, status=404)
    sp_id = request.data.get("staff_person")
    u.staff_person = StaffPerson.objects.filter(pk=sp_id).first() if sp_id else None
    u.staff_link = "manual" if u.staff_person else "none"
    u.save(update_fields=["staff_person", "staff_link", "last_seen"])
    return Response(_tg_user(u))


@zona_api(["GET"], [CanView])
def staff_people_search(request):
    from django.db.models import Q as _Q

    from zona.models import StaffPerson
    q = str(request.query_params.get("q") or "").strip()
    qs = StaffPerson.objects.filter(is_vacancy=False).exclude(name="").select_related("project", "manager")
    if q:
        qs = qs.filter(_Q(name__icontains=q) | _Q(territory__icontains=q) | _Q(phone__icontains=q))
    return Response([{"id": p.id, "name": p.name, "role": p.get_role_display(), "project": p.project.name,
                      "territory": p.territory, "manager": p.manager.name if p.manager_id else ""} for p in qs[:30]])


# ====================================================================== bot bo'yicha AI tahlili va takliflar
def _sugg(x):
    e = x.entry
    return {"id": x.id, "kind": x.kind, "status": x.status, "reason": x.reason, "payload": x.payload,
            "entry": e.id if e else None, "entry_title": e.title if e else "",
            "current": {"answer": e.answer, "answer_ru": e.answer_ru, "ask_first": e.ask_first,
                        "questions": e.questions} if e else None,
            "target": x.target_id, "target_title": x.target.title if x.target_id else "",
            "target_answer": x.target.answer[:800] if x.target_id else "",
            "question_ids": x.question_ids, "decided_by": x.decided_by, "created_at": x.created_at,
            "group": [{"id": g.id, "title": g.title, "answer": g.answer[:600], "status": g.status}
                      for g in Entry.objects.filter(pk__in=(x.payload or {}).get("merge") or [])] if x.kind == Suggestion.DEDUPE else []}


@zona_api(["GET", "POST"], [ReadOrEdit])
def ai_jobs(request):
    if request.method == "POST":
        from zona.ai import service as ai
        if not ai.status().get("support"):
            return Response({"detail": "AI sozlanmagan: Sozlamalar → AI → «Support bot javoblari» uchun model tanlang."}, status=400)
        kind = request.data.get("kind")
        if kind not in (AIJob.REVIEW_ENTRIES, AIJob.REVIEW_UNANSWERED, AIJob.DEDUPE):
            return Response({"detail": "Tahlil turini tanlang."}, status=400)
        if AIJob.objects.filter(status__in=[AIJob.QUEUED, AIJob.RUNNING]).exists():
            return Response({"detail": "AI tahlili allaqachon bajarilmoqda."}, status=400)
        AIJob.objects.create(kind=kind, created_by=_actor(request),
                             params={k: request.data[k] for k in ("scope", "limit", "days", "threshold", "auto", "ids") if k in request.data})
    return Response([{"id": j.id, "kind": j.kind, "status": j.status, "progress": j.progress, "error": j.error,
                      "created_by": j.created_by, "created_at": j.created_at, "finished_at": j.finished_at}
                     for j in AIJob.objects.all()[:20]])


@zona_api(["GET"], [CanView])
def suggestions(request):
    status_ = request.query_params.get("status") or Suggestion.PENDING
    qs = Suggestion.objects.select_related("entry", "target")
    if status_ != "all":
        qs = qs.filter(status=status_)
    return Response([_sugg(x) for x in qs[:300]])


@zona_api(["POST"], [ReadOrEdit])
def suggestion_decide(request, pk, action):
    from . import ai_review
    x = Suggestion.objects.select_related("entry", "target").filter(pk=pk, status=Suggestion.PENDING).first()
    if not x:
        return Response({"detail": "Taklif topilmadi yoki allaqachon ko'rib chiqilgan."}, status=404)
    try:
        if action == "approve":
            edits = request.data.get("payload") if isinstance(request.data.get("payload"), dict) else None
            ai_review.apply(x, _actor(request), edits)
        else:
            ai_review.reject(x, _actor(request))
    except ValueError as e:
        return Response({"detail": str(e)}, status=400)
    return Response(_sugg(x))
