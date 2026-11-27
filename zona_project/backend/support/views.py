"""Support bot admin API: /api/support/...

Rollar (zona Profile): viewer — ko'rish, savolga javob yozish, yangi javob taklif qilish;
editor — javoblarni tasdiqlash/tahrirlash, shablonlar; admin — botlar va sozlamalar.
"""
from django.db.models import Case, Count, Q, When
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
                   "history_night_from", "history_night_to",
                   "image_threshold", "image_autolabel", "mention_asker", "mention_supervisor", "workers",
                   "contact_lookup", "ai_primary", "ai_primary_below", "album_window",
                   "tasks_enabled", "task_bot", "task_default_assignee", "task_departments", "task_members",
                   "task_daily_limit", "task_gap", "task_attach", "task_mode", "task_remind_group", "task_remind_dm",
                   "merge_window", "self_learning", "auto_approve_level", "answer_variety",
                   "progress_messages", "answer_policy", "confirm_resolution", "confirm_after", "thanks_reaction",
                   "thread_window", "category_owners", "category_backups", "answer_keep_days", "answer_test_note", "review_button",
                   "react_accept", "ask_staff_after", "reask_after", "remind_max", "collapse_after",
                   "media_full_days", "work_from", "work_to", "work_days"]


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
        for fld in ("category_owners", "category_backups"):  # {"promo": member_id | "c:34"} — asosiy va zaxira
            if fld not in data:
                continue
            from zona.models import Member, TeamContact

            from .systems import CATEGORIES
            raw = data.get(fld) or {}
            if not isinstance(raw, dict):
                return Response({"detail": f"{fld}: {{toifa: xodim id}}"}, status=400)
            # qiymat: xodim yoki jamoa id (12) yoki jamoa a'zosi "c:34"
            clean = {k: (int(v) if str(v).isdigit() else str(v)) for k, v in raw.items()
                     if k in CATEGORIES and (str(v).isdigit() or (str(v).startswith("c:") and str(v)[2:].isdigit()))}
            mids = {v for v in clean.values() if isinstance(v, int)}
            cids = {int(v[2:]) for v in clean.values() if isinstance(v, str)}
            if (Member.objects.filter(pk__in=mids).count() != len(mids)
                    or TeamContact.objects.filter(pk__in=cids).count() != len(cids)):
                return Response({"detail": "Xodim topilmadi"}, status=400)
            setattr(s, fld, clean or None)
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
                  "in_analytics", "creates_tasks", "joined_at", "last_message_at", "questions_7d", "redirect_to", "invite_link", "link",
                  "redirect_count", "sees_all"]
        read_only_fields = ["bot", "chat_id", "title", "is_admin", "joined_at", "last_message_at", "redirect_count"]

    link = serializers.SerializerMethodField()
    sees_all = serializers.SerializerMethodField()

    def get_sees_all(self, g):
        """Bot guruhdagi barcha xabarlarni ko'radimi: admin bo'lsa yoki botda privacy o'chiq bo'lsa."""
        return bool(g.is_admin or g.bot.read_all)

    def get_link(self, g):
        return g.invite_link or (f"https://t.me/{g.username}" if g.username else "")

    def validate_redirect_to(self, v):
        if v is not None and self.instance is not None and v.pk == self.instance.pk:
            raise serializers.ValidationError("Guruh o'ziga yo'naltirilmaydi")
        return v

    def validate_invite_link(self, v):
        v = (v or "").strip()
        if v and not v.startswith(("https://t.me/", "http://t.me/", "t.me/", "tg://")):
            raise serializers.ValidationError("Telegram havolasi bo'lishi kerak (https://t.me/...)")
        return ("https://" + v) if v.startswith("t.me/") else v


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
    responsible_tg = serializers.SerializerMethodField()
    claude_target_title = serializers.CharField(source="claude_target.title", read_only=True, default="")
    claude_covers_count = serializers.SerializerMethodField()
    attachments_info = serializers.SerializerMethodField()

    def get_claude_covers_count(self, obj):
        return obj.claude_covers.filter(status__in=[Entry.NEW, Entry.REVIEW]).count() if obj.claude_kind == "general" else 0

    def get_responsible_tg(self, obj):
        """Mas'ulning Telegram'lari (belgilash uchun): o'zi yoki jamoa a'zolari."""
        m = obj.responsible
        if m is None:
            return []
        tgs = [c.telegram.lstrip("@") for c in m.contacts.all() if c.telegram] if m.is_team else []
        if m.telegram:
            tgs.insert(0, m.telegram.lstrip("@"))
        return list(dict.fromkeys(tgs))[:4]
    image_examples_count = serializers.SerializerMethodField()
    sources_info = serializers.SerializerMethodField()

    def get_sources_info(self, obj):
        """Yozuv o'rganilgan savollar (oxirgi 5 tasi): matni, guruhi, muallifi va BARCHA fayllari — albomdagi har bir
        rasm hamda savol egasining keyin yuborgan qo'shimcha fayllari (aniqlashtirishga javob)."""
        ids = list(obj.sources or [])[-5:]
        view = self.context.get("view")
        detail = getattr(view, "action", "") == "retrieve"
        # og'ir (har savol uchun bir nechta so'rov): faqat bitta yozuv ochilganda yoki sahifalangan navbatda (sources=1)
        if not ids or not (detail or self.context.get("with_sources")):
            return []
        out = []
        for q in Message.objects.filter(pk__in=ids).select_related("group", "user").order_by("-created_at"):
            related = Message.objects.filter(question=q, kind=Message.INFO)
            if q.media_group_id:
                related = related | Message.objects.filter(bot_id=q.bot_id, chat_id=q.chat_id, media_group_id=q.media_group_id)
            mids = {q.pk, *related.values_list("pk", flat=True)}
            files = Media.objects.filter(message_id__in=mids).select_related("label").order_by("message_id", "id")
            info = [x for x in related.filter(kind=Message.INFO).order_by("created_at").values_list("text", flat=True) if x]
            out.append({"id": q.pk, "text": q.text, "ocr": (q.ocr_text or "")[:400], "info": info[:5],
                        "group": q.group.title if q.group_id else "", "user": q.user.name if q.user_id else "",
                        "link": q.group.message_link(q.message_id) if q.group_id else "", "at": q.created_at,
                        "media": [media_dict(m) for m in files[:30]]})
        return out

    def get_attachments_info(self, obj):
        if not obj.attachments:
            return []
        files = self.context.get("media_map")  # ro'yxatda — bir so'rov bilan oldindan yuklangan
        if files is None:
            files = {m.id: m for m in Media.objects.filter(id__in=obj.attachments)}
        return [media_dict(files[i]) for i in obj.attachments if i in files]

    def get_image_examples_count(self, obj):
        n = getattr(obj, "n_images", None)  # ro'yxatda — annotatsiya (har yozuvga alohida so'rov emas)
        return n if n is not None else obj.image_examples.count()

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
                  "attachments", "attachments_info", "image_examples_count", "sources_info", "zone", "zone_name", "creates_task", "task_assignee", "variants", "answer_mode",
                  "responsible", "responsible_name", "responsible_tg", "status", "source", "priority", "pending", "author",
                  "claude_kind", "claude_note", "claude_target", "claude_target_title", "claude_covers_count", "auto_close",
                  "approved_by", "approved_at", "uses", "likes", "dislikes", "last_used_at", "created_at", "updated_at"]
        read_only_fields = ["claude_kind", "claude_note", "claude_target",
                            "status", "source", "priority", "pending", "author", "approved_by", "approved_at", "uses",
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
        qs = Entry.objects.select_related("zone", "responsible", "claude_target").prefetch_related("responsible__contacts")
        p = self.request.query_params
        if p.get("claude"):  # Claude ko'rib chiqqanlar: any / status / handoff / same / general
            qs = qs.exclude(claude_kind="") if p["claude"] == "any" else qs.filter(claude_kind=p["claude"])
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

    def list(self, request, *args, **kwargs):
        """Tez ro'yxat. ?brief=1 — faqat id/sarlavha/holat (tanlash ro'yxatlari uchun);
        ?limit=&offset= — sahifa {"count", "results"} (navbat: muhimlari va yangilari oldin);
        ?sources=1 — manba savollar ham (faqat sahifalangan ro'yxatda — og'ir)."""
        from django.db.models import Count
        p = request.query_params
        qs = self.get_queryset()
        if p.get("brief") == "1":
            return Response(list(qs.order_by("title").values("id", "title", "status", "kind")))
        qs = qs.annotate(n_images=Count("image_examples"))
        count = None
        if p.get("limit"):
            limit, offset = max(1, min(int(p["limit"]), 100)), max(0, int(p.get("offset") or 0))
            qs = qs.order_by("-priority", "-created_at", "-id")
            count = qs.count()
            rows = list(qs[offset:offset + limit])
        else:
            rows = list(qs)
        att = {i for e in rows for i in (e.attachments or [])}
        ctx = {**self.get_serializer_context(), "media_map": {m.id: m for m in Media.objects.filter(id__in=att)},
               "with_sources": count is not None and p.get("sources") == "1"}
        data = EntrySerializer(rows, many=True, context=ctx).data
        return Response(data if count is None else {"count": count, "results": data})

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
            elif act == "absorb":  # Claude topgan standart javobga qo'shish (javob matni o'zgarmaydi, takror arxivga)
                from .dedupe import absorb
                if not e.claude_target_id or e.status not in (Entry.NEW, Entry.REVIEW):
                    continue
                absorb(e.claude_target_id, [e.pk], _actor(request))
            elif act in ("kind_template", "kind_faq"):  # turini o'zgartirish (matn o'zgarmaydi)
                e.kind = Entry.TEMPLATE if act == "kind_template" else Entry.FAQ
                e.save(update_fields=["kind", "updated_at"])
            elif act in ("mode_auto", "mode_on", "mode_off"):  # chatda javob: umumiy / har doim / faqat o'rganish
                e.answer_mode = {"mode_auto": "", "mode_on": "on", "mode_off": "off"}[act]
                e.save(update_fields=["answer_mode", "updated_at"])
            elif act == "review":  # tasdiqni bekor qilish: bot ishlatmaydi, tasdiqlash navbatiga qaytadi
                if e.status != Entry.APPROVED:
                    continue
                e.status = Entry.REVIEW
                e.save(update_fields=["status", "updated_at"])
            else:
                continue
            done += 1
        return Response({"done": done})

    @action(detail=False, methods=["get"], url_path="claude-counts")
    def claude_counts(self, request):
        """Tasdiqlash navbatida Claude ko'rib chiqqanlar soni: turi bo'yicha."""
        from django.db.models import Count
        rows = (Entry.objects.filter(status__in=[Entry.NEW, Entry.REVIEW]).exclude(claude_kind="")
                .values_list("claude_kind").annotate(n=Count("id")))
        c = dict(rows)
        return Response({**c, "any": sum(c.values())})

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
    ratings = serializers.SerializerMethodField()
    user_real = serializers.SerializerMethodField()

    def get_ratings(self, obj):
        return [{"stars": r.stars, "staff": r.staff_name, "by": r.by_name, "source": r.source, "comment": r.comment,
                 "at": r.created_at} for r in obj.ratings.all()]

    def get_user_real(self, obj):
        """Savol beruvchi asli kim: xodim kartasi (rol, loyiha, hudud) yoki PRBC dagi ism va lavozim."""
        u = obj.user
        if u is None:
            return None
        sp = u.staff_person if u.staff_person_id else None
        return {"name": sp.name if sp else u.real_name, "role": sp.get_role_display() if sp else u.position,
                "project": sp.project.name if sp and sp.project_id else u.department, "territory": sp.territory if sp else "",
                "phone": (sp.phone if sp else "") or u.phone}

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
                  "created_at", "answered_at", "staff_answers", "task", "problem", "resolution", "resolved_at",
                  "resolved_by", "app", "origin", "category", "solution", "labeled_by", "train", "ratings", "user_real",
                  "tags", "tags_locked"]

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
              .select_related("group", "user__staff_person__project", "entry").prefetch_related("media", "ratings", "staff_replies__media",
                                                                          "staff_replies__user__member",
                                                                          "staff_replies__user__contact"))
        p = self.request.query_params
        if p.get("status") and p["status"] != "all":
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("group"):
            qs = qs.filter(group_id=p["group"])
        if p.get("stage"):
            qs = qs.filter(stage=p["stage"])
        if p.get("id"):  # admin chatidagi "Panelda" havolasi: aynan shu savol
            return qs.filter(pk__in=[int(x) for x in str(p["id"]).split(",") if x.strip().isdigit()][:50])
        if p.get("ex"):
            # konstruktordan o'tish: aynan o'sha filtrlar (f_<o'lchov>=...) va davrga mos savollar
            from .explore import question_ids
            return qs.filter(pk__in=question_ids(p)).order_by("-created_at")
        if p.get("drill"):
            # tahlildan o'tish: aynan tahlil sanagan savollar (jonli, tahlilga qo'shilgan guruhlar, o'sha davr)
            from .workload import BOT_STAGES, period, scoped
            since, end, _info = period(p)
            qs = scoped(qs.filter(created_at__gte=since, created_at__lt=end)).exclude(status=Message.IGNORED)
            done = Q(status__in=[Message.ANSWERED, Message.CLOSED])
            d = p["drill"]
            if d == "bot":
                qs = qs.filter(done, stage__in=BOT_STAGES)
            elif d == "staff":
                qs = qs.filter(done, stage__in=["staff", "panel", "react"])
            elif d == "unanswered":
                qs = qs.exclude(done)
            elif d == "open":
                qs = qs.filter(resolution__in=[Message.NO, Message.WORK, Message.ASKED])
            elif d == "unknown":
                qs = qs.filter(resolution="")
            elif d in (Message.YES, Message.NO, Message.WORK, Message.ASKED):
                qs = qs.filter(resolution=d)
            return qs.order_by("-created_at")
        if p.get("resolution"):  # yes / no / asked / open (holati noma'lum yoki so'ralgan)
            r = p["resolution"]
            qs = qs.filter(resolution__in=["", "asked", "work"]) if r == "open" else qs.filter(resolution=r)
        for f in ("app", "origin", "category"):  # tizim bo'yicha filtr
            if p.get(f):
                qs = qs.filter(**{f: "" if p[f] == "none" else p[f]})
        if p.get("q"):
            qs = qs.filter(Q(text__icontains=p["q"]) | Q(ocr_text__icontains=p["q"]))
        return qs

    def list(self, request, *args, **kwargs):
        limit = min(int(request.query_params.get("limit") or 200), 500)
        return Response(MessageSerializer(self.get_queryset()[:limit], many=True).data)

    def create(self, request, *args, **kwargs):
        return Response(status=405)

    @action(detail=True, methods=["post"], url_path="tags", permission_classes=[ReadOrEdit])
    def set_tags(self, request, pk=None):
        """Teglarni qo'lda o'rnatish: {"tags": ["promo", "1c"]} — keyin avtomatik qayta yozilmaydi."""
        from .models import Tag
        known = set(Tag.objects.values_list("key", flat=True))
        tags = [t for t in dict.fromkeys(str(x) for x in (request.data.get("tags") or [])) if t in known][:12]
        Message.objects.filter(pk=pk, kind=Message.QUESTION).update(tags=tags, tags_locked=True)
        return Response({"tags": tags})

    @action(detail=True, methods=["post"])
    def rate(self, request, pk=None):
        """Panelda xodim javobini baholash: {"stars": 1..5, "comment"?: "", "staff"?: tg_user_id}."""
        from . import rating
        if not _can_edit(request):
            return Response({"detail": "Baholash uchun muharrir huquqi kerak."}, status=403)
        q = Message.objects.select_related("handler__member", "handler__contact").get(pk=pk)
        try:
            stars = int(request.data.get("stars"))
        except (TypeError, ValueError):
            return Response({"detail": "Baho 1 dan 5 gacha"}, status=400)
        staff = TgUser.objects.filter(pk=request.data.get("staff")).first() if request.data.get("staff") else None
        r = rating.rate(q, stars, by_name=_actor(request), source="panel", staff=staff, comment=str(request.data.get("comment") or ""))
        if r is None:
            return Response({"detail": "Bu savolga xodim javob bermagan — baholanadigan xodim yo'q"}, status=400)
        return Response({"stars": r.stars, "staff": r.staff_name})

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
        if q.resolution == "asked" and not q.confirm_msg_id:  # nazoratdagi savol: endi savol egasidan "hal bo'ldimi?"
            q.resolution, q.next_ask_at, q.remind_count = "", None, 0
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

    @action(detail=True, methods=["post"], permission_classes=[ReadOrEdit])
    def resolve(self, request, pk=None):
        """Xodim paneldan belgilaydi: hal bo'ldi (yes) / hal bo'lmadi (no) / noma'lum ("")."""
        from . import resolution
        value = str(request.data.get("value") or "")
        if value not in ("yes", "no", ""):
            return Response({"detail": "value: yes / no / ''"}, status=400)
        q = Message.objects.select_related("bot").get(pk=pk, kind=Message.QUESTION)
        _admin_resolve([q], value, _actor(request))
        return Response({"ok": True, "resolution": q.resolution, "status": q.status, "resolved_by": q.resolved_by})

    @action(detail=False, methods=["post"], url_path="resolve-bulk", permission_classes=[ReadOrEdit])
    def resolve_bulk(self, request):
        """Admin bir nechta savolni birdan belgilaydi (masalan, "tasdiq kutilmoqda" ro'yxatidagilarni)."""
        value = str(request.data.get("value") or "")
        ids = [int(x) for x in (request.data.get("ids") or [])][:500]
        if value not in ("yes", "no") or not ids:
            return Response({"detail": "ids va value (yes / no) kerak"}, status=400)
        qs = list(Message.objects.filter(pk__in=ids, kind=Message.QUESTION).select_related("bot"))
        _admin_resolve(qs, value, _actor(request))
        return Response({"ok": True, "done": len(qs)})

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        Message.objects.filter(pk=pk).update(status=Message.CLOSED)
        return Response({"ok": True})


# ====================================================================== statistika va xodimlar
@zona_api(["GET"], [CanView])
def stats(request):
    from .workload import period
    since, end, _info = period(request.query_params, default_days=7)
    qs = Message.objects.filter(kind=Message.QUESTION, created_at__gte=since, created_at__lt=end)
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


@zona_api(["GET", "POST"], [CanView])
def tags_list(request):
    """Teglar: GET — ro'yxat (savollar soni bilan); POST (admin) — {"tags": [{key, title, keywords, color, active}]} to'liq
    ro'yxatni saqlash va barcha savollarga avtomatik teglarni qayta qo'yish."""
    import re as _re
    from collections import Counter

    from . import tags as T
    from .models import Tag
    if request.method == "POST":
        if not has_role(request, Profile.ADMIN):
            return Response({"detail": "Faqat administrator"}, status=403)
        rows = request.data.get("tags") or []
        keep = []
        for i, r in enumerate(rows[:60]):
            key = _re.sub(r"[^a-z0-9_-]", "", str(r.get("key") or "").lower())[:40] or f"tag{i + 1}"
            Tag.objects.update_or_create(key=key, defaults={
                "title": str(r.get("title") or key)[:80], "order": i, "color": str(r.get("color") or "")[:16],
                "active": bool(r.get("active", True)),
                "keywords": [str(w).strip()[:120] for w in (r.get("keywords") or []) if str(w).strip()][:60]})
            keep.append(key)
        Tag.objects.exclude(key__in=keep).delete()
        T._CACHE["key"] = None
        T.backfill()
    counts = Counter(t for tags in Message.objects.filter(kind=Message.QUESTION).values_list("tags", flat=True) for t in (tags or []))
    return Response([{"key": t.key, "title": t.title, "keywords": t.keywords, "color": t.color, "active": t.active,
                      "questions": counts.get(t.key, 0)} for t in Tag.objects.all()])


@zona_api(["GET"], [CanView])
def owners(request):
    """Mas'ul tanlash ro'yxati: barcha xodimlar va jamoalar (Supervayzerlar, Pro-target...) — Telegram'lari bilan."""
    from .engine import _person
    return Response([{**_person(m), "role": m.role} for m in Member.objects.prefetch_related("contacts").order_by("name")])


@zona_api(["GET"], [CanView])
def staff(request):
    """Bot taniydigan xodimlar: Telegram'i bor xodimlar va jamoa a'zolari (javoblaridan o'rganiladi)."""
    out = [{"type": "member", "id": m.id, "name": m.name, "role": m.role, "level": m.level, "telegram": m.telegram,
            "phone": m.phone, "team": ""} for m in Member.objects.filter(is_team=False).exclude(telegram="")]
    out += [{"type": "contact", "id": c.id, "name": c.name, "role": c.role or c.member.role, "level": c.member.level,
             "telegram": c.telegram, "phone": c.phone, "team": c.member.name, "team_id": c.member_id,
             "linked": bool(c.telegram_id), "operator": c.operator.name if c.operator_id else ""}
            for c in TeamContact.objects.select_related("member", "operator")]
    # jamoaga qo'shilgan yakka xodimlar (Kamoliddin, Timur — Dasturchilar): jamoa ro'yxatida ham ko'rinadi
    for row in out:
        if row["type"] == "member":
            m = Member.objects.filter(pk=row["id"]).select_related("member_of").first()
            if m and m.member_of_id:
                row["team"], row["team_id"] = m.member_of.name, m.member_of_id
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
            "created_at": j.created_at, "started_at": j.started_at, "finished_at": j.finished_at,
            "date_from": j.date_from, "date_to": j.date_to, "run_after": j.run_after, "night_only": j.night_only}


def _day(value, end=False):
    """"2026-01-15" -> Toshkent vaqti bo'yicha kun boshi (end=True — keyingi kun boshi, ya'ni kun oxirigacha)."""
    from datetime import date, datetime, time

    from .workload import TZ
    if not value:
        return None
    d = date.fromisoformat(str(value)[:10])
    return datetime.combine(d + timezone.timedelta(days=1) if end else d, time.min, TZ)


@zona_api(["GET", "POST"], [AdminOnly])
def history_jobs(request):
    """Guruh tarixini o'rganish: bir yoki bir nechta guruh (yoki hammasi), sana oralig'i, rejalashtirish.

    Akkaunt xavfsizligi kunlik son bilan emas, tezlik bilan ta'minlanadi (history.py): bir vaqtda bitta guruh, guruhlar
    orasida tanaffus, sahifa/rasm oralig'ida pauza, Telegram FloodWait'iga to'liq rioya. Shuning uchun hamma guruhni
    birdan navbatga qo'yish mumkin — ular ketma-ket o'qiladi."""
    if request.method == "POST":
        from . import history as hist
        s = Settings.load()
        if not s.mtproto_session_enc:
            return Response({"detail": "Avval Telegram akkauntni ulang."}, status=400)
        raw = request.data.get("groups") or ([request.data["group"]] if request.data.get("group") else [])
        qs = Group.objects.all() if raw == "all" else Group.objects.filter(pk__in=[int(x) for x in raw])
        groups = list(qs.order_by("id"))
        if not groups:
            return Response({"detail": "Guruhni tanlang."}, status=400)
        try:
            date_from, date_to = _day(request.data.get("date_from")), _day(request.data.get("date_to"), end=True)
        except ValueError:
            return Response({"detail": "Sana noto'g'ri (YYYY-MM-DD)."}, status=400)
        if date_from and date_to and date_from >= date_to:
            return Response({"detail": "Boshlanish sanasi tugash sanasidan oldin bo'lishi kerak."}, status=400)
        days = max(1, min(int(request.data.get("days") or s.history_days), 3650))
        photos = bool(request.data.get("photos", s.history_photos))
        when = str(request.data.get("schedule") or "now")  # now / night / ISO vaqt
        night_only, run_after = when == "night", None
        if when == "night":
            run_after = None if hist.is_night(None, s) else hist.next_night_start(None, s)
        elif when != "now":
            try:
                run_after = timezone.datetime.fromisoformat(when)
                if timezone.is_naive(run_after):
                    from .workload import TZ
                    run_after = run_after.replace(tzinfo=TZ)
            except ValueError:
                return Response({"detail": "Vaqt noto'g'ri."}, status=400)
        busy = set(HistoryJob.objects.filter(group__in=groups, status__in=[HistoryJob.QUEUED, HistoryJob.RUNNING])
                   .values_list("group_id", flat=True))
        made = [HistoryJob.objects.create(group=g, days=days, photos=photos, created_by=_actor(request), date_from=date_from,
                                          date_to=date_to, run_after=run_after, night_only=night_only)
                for g in groups if g.pk not in busy]
        if not made:
            return Response({"detail": "Bu guruh(lar) tarixi allaqachon navbatda yoki o'qilmoqda."}, status=400)
    return Response(_jobs())


@zona_api(["POST"], [AdminOnly])
def history_job_action(request, pk):
    """Navbatdagi/ishlayotgan vazifani bekor qilish yoki darhol boshlash (ishlayotgani joriy 50 talikdan keyin to'xtaydi)."""
    j = HistoryJob.objects.filter(pk=pk).first()
    if j is None:
        return Response({"detail": "Topilmadi."}, status=404)
    action = request.data.get("action")
    if action == "cancel" and j.status in (HistoryJob.QUEUED, HistoryJob.RUNNING):
        HistoryJob.objects.filter(pk=pk).update(status=HistoryJob.CANCELED, finished_at=timezone.now())
    elif action == "now" and j.status == HistoryJob.QUEUED:
        HistoryJob.objects.filter(pk=pk).update(run_after=None, night_only=False)
    elif action in ("continue", "resume"):
        from . import history as hist
        if hist.continue_job(j, _actor(request)) is None:
            return Response({"detail": "Bu guruh tarixi allaqachon navbatda yoki o'qilmoqda."}, status=400)
    elif action == "delete":
        if j.status == HistoryJob.RUNNING:
            return Response({"detail": "Ishlayotgan vazifani avval bekor qiling."}, status=400)
        j.delete()  # faqat vazifa yozuvi; o'rganilgan savollar va bilim bazasi saqlanadi
    return Response(_jobs())


def _jobs():
    return [_job(x) for x in HistoryJob.objects.select_related("group")[:JOBS_LIMIT]]


JOBS_LIMIT = 1000


@zona_api(["POST"], [AdminOnly])
def history_delete(request):
    """Bir nechta vazifani o'chirish: {"ids": [...]} yoki {"statuses": ["canceled", "failed"]}. Ishlayotgani o'chirilmaydi;
    o'rganilgan ma'lumot (savollar, javoblar, bilim bazasi) o'chmaydi — faqat ro'yxatdagi yozuv."""
    qs = HistoryJob.objects.exclude(status=HistoryJob.RUNNING)
    ids, statuses = request.data.get("ids"), request.data.get("statuses")
    if ids:
        qs = qs.filter(pk__in=[int(x) for x in ids])
    elif statuses:
        allowed = {HistoryJob.CANCELED, HistoryJob.FAILED, HistoryJob.DONE, HistoryJob.QUEUED}
        qs = qs.filter(status__in=[x for x in statuses if x in allowed])
    else:
        return Response({"detail": "ids yoki statuses kerak"}, status=400)
    n, _ = qs.delete()
    return Response({"deleted": n, "jobs": _jobs()})


@zona_api(["POST"], [AdminOnly])
def history_continue(request):
    """Hammasini (yoki tanlangan guruhlarni) davom ettirish: har bir guruhning oxirgi vazifasi kelgan joyidan."""
    from . import history as hist
    raw = request.data.get("groups") or "all"
    ids = None if raw == "all" else [int(x) for x in raw]
    made = hist.continue_groups(ids, _actor(request))
    return Response({"continued": len(made), "jobs": _jobs()})


# ====================================================================== tahlil: xodimlar javoblari va aniqlashtirishlar
@zona_api(["GET"], [CanView])
def analytics(request):
    from collections import Counter, defaultdict
    from statistics import median

    from .engine import tokens_text
    from .workload import BOT_STAGES, local, period, scoped
    since, end, info = period(request.query_params)
    raw = Message.objects.filter(created_at__gte=since, created_at__lt=end)
    # faqat jonli savollar va tahlilga qo'shilgan guruhlar (guruh tarixi — faqat bilim uchun; test guruhlari — sozlamada)
    msgs = scoped(raw)
    all_q = msgs.filter(kind=Message.QUESTION)
    questions = all_q.exclude(stage="dup").exclude(status=Message.IGNORED)  # haqiqiy savollar (takror / savol emas — yo'q)
    raw_q = raw.filter(kind=Message.QUESTION)
    excluded = {"history": raw_q.filter(source="history").count(),
                "groups_off": raw_q.filter(source="live", group__in_analytics=False).count(),
                "duplicates": all_q.filter(stage="dup").count(), "ignored": all_q.filter(status=Message.IGNORED).count(),
                "groups": list(Group.objects.filter(in_analytics=False).values_list("title", flat=True))}

    # xodimlar: kim nechta savolga javob berdi, qanchalik tez, qancha ishladi
    per = defaultdict(lambda: {"answers": 0, "clarifications": 0, "times": [], "groups": set(), "questions": set(),
                               "days": set(), "topics": Counter(), "last": None, "user": None})
    for r in (msgs.filter(kind__in=[Message.STAFF, Message.CLARIFY], user__isnull=False)
              .select_related("user__member", "user__contact", "question__entry", "group")):
        name = r.user.staff_name()
        row = per[name]
        row["user"] = row["user"] or r.user
        row["groups"].add(r.group.title if r.group else "")
        row["days"].add(local(r.created_at).date())
        row["last"] = max(row["last"], r.created_at) if row["last"] else r.created_at
        if r.kind == Message.CLARIFY:
            row["clarifications"] += 1
        else:
            row["answers"] += 1
            if r.question_id:
                row["questions"].add(r.question_id)
                row["times"].append(max(0.0, (r.created_at - r.question.created_at).total_seconds()))  # soniya
                if r.question.entry_id:
                    row["topics"][r.question.entry.title] += 1
    panel = Counter(questions.filter(stage="panel").values_list("answered_by", flat=True))
    authored = defaultdict(Counter)
    for author, st in Entry.objects.filter(source__in=["staff", "history", "panel"]).values_list("author", "status"):
        authored[author][st] += 1
    total_answers = sum(r["answers"] for r in per.values()) + sum(panel.values()) or 1
    staff = []
    # bot taniydigan, lekin shu davrda hali javob yozmagan xodimlar ham ro'yxatda (0 bilan) — kim tanilgani ko'rinib tursin
    for u in TgUser.objects.filter(Q(member__isnull=False) | Q(contact__isnull=False)).select_related("member", "contact"):
        if u.staff_name() not in per and u.staff_name() not in panel:
            per[u.staff_name()]["user"] = u
    for name in set(per) | set(panel):
        r = per[name]
        a = authored.get(name, Counter())
        answers = r["answers"] + panel.get(name, 0)
        u = r["user"]
        staff.append({"name": name, "answers": answers, "panel": panel.get(name, 0), "clarifications": r["clarifications"],
                      "questions": len(r["questions"]) + panel.get(name, 0),
                      "share": round(100 * answers / total_answers),
                      "median_s": round(median(r["times"]), 1) if r["times"] else None,
                      "avg_s": round(sum(r["times"]) / len(r["times"]), 1) if r["times"] else None,
                      "active_days": len(r["days"]), "per_day": round(answers / max(1, len(r["days"])), 1),
                      "messages": u.msg_count if u else 0, "last": r["last"],
                      "groups": sorted(g for g in r["groups"] if g),
                      "topics": [{"title": t, "n": n} for t, n in r["topics"].most_common(3)],
                      "candidates": sum(a.values()), "approved": a.get(Entry.APPROVED, 0),
                      "rejected": a.get(Entry.REJECTED, 0)})
    # xodim javob bergan savollarning yakuni (savol egasi tasdiqlagan / rad etgan)
    res_of = dict(Message.objects.filter(pk__in={i for r in per.values() for i in r["questions"]})
                  .values_list("pk", "resolution"))
    # reaksiya bilan qabul qilgan savollar (qisman javob) va hozir "jarayonda" turganlari
    reacts, working = Counter(), Counter()
    for h in questions.filter(handler__isnull=False, stage="react").select_related("handler__member", "handler__contact"):
        reacts[h.handler.staff_name()] += 1
    for h in questions.filter(handler__isnull=False, resolution=Message.WORK).select_related("handler__member", "handler__contact"):
        working[h.handler.staff_name()] += 1
    for row in staff:
        qids = per[row["name"]]["questions"]
        row["resolved"] = sum(1 for i in qids if res_of.get(i) == Message.YES)
        row["unresolved"] = sum(1 for i in qids if res_of.get(i) == Message.NO)
        row["reactions"] = reacts.get(row["name"], 0)
        row["working"] = working.get(row["name"], 0)
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
    daily = defaultdict(lambda: {"total": 0, "bot": 0, "staff": 0, "resolved": 0, "unresolved": 0})
    for created, stage, res in questions.values_list("created_at", "stage", "resolution"):
        d = daily[local(created).date().isoformat()]
        d["total"] += 1
        if res == Message.YES:
            d["resolved"] += 1
        elif res == Message.NO:
            d["unresolved"] += 1
        if stage in BOT_STAGES:
            d["bot"] += 1
        elif stage in ("staff", "panel", "react"):
            d["staff"] += 1
    groups = list(questions.values("group__title").annotate(n=Count("id")).order_by("-n")[:15])
    unanswered = questions.exclude(status__in=[Message.ANSWERED, Message.CLOSED]).exclude(resolution=Message.YES).count()
    total = questions.count()
    answered = questions.filter(status__in=[Message.ANSWERED, Message.CLOSED])
    bot_n = answered.filter(stage__in=BOT_STAGES).count()
    staff_n = answered.filter(stage__in=["staff", "panel", "react"]).count()
    summary = {"total": total, "bot": bot_n, "staff": staff_n, "react": answered.filter(stage="react").count(),
               "unanswered": unanswered, "bot_share": round(100 * bot_n / total) if total else None,
               "staff_share": round(100 * staff_n / total) if total else None,
               "open": questions.filter(resolution__in=[Message.NO, Message.WORK, Message.ASKED]).count(),
               # mas'ul xodim ishni bajardi va o'zi tasdiqladi ("✅ Javob berildi / bajarildi")
               "staff_done": questions.filter(resolution=Message.YES, resolved_by__startswith="xodim: ").count()}
    return Response({
        **info, "questions": total, "unanswered": unanswered, "summary": summary, "excluded": excluded,
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
        "protarget": _protarget(questions, since, end),
        "resolution": _resolution(questions),
        "systems": _systems(questions),
        "images": {"total": Media.objects.filter(kind=Media.PHOTO).count(),
                   "labeled": Media.objects.filter(kind=Media.PHOTO, label__isnull=False).count(),
                   "types": Media.objects.filter(kind=Media.PHOTO, label__isnull=False).values("label").distinct().count(),
                   "by_image": questions.filter(stage="image").count()},
    })


@zona_api(["GET"], [CanView])
def analytics_workload(request):
    """Ish yuklamasi: soat × hafta kuni, haftalar, guruhlar, savol turlari, xodimlarning ish soatlari va javob tezligi."""
    from .workload import workload
    from .workload import period
    start, end, info = period(request.query_params)
    return Response(workload(start, end, info))


@zona_api(["GET"], [CanView])
def analytics_explore(request):
    """Konstruktor: ma'lumot turi, davr, 1–2 guruhlash, ko'rsatkichlar va filtrlar bo'yicha istalgan statistika."""
    from .explore import explore
    return Response(explore(request.query_params))


@zona_api(["GET"], [CanView])
def analytics_staff(request):
    """Xodimlar: guruhdagi xabarlari, ish vaqti (boshlash / tugatish), ish turlari va tezligi — butun tarix bo'yicha."""
    from .activity import board
    from .workload import period
    start, end, info = period(request.query_params, max_days=3660)
    return Response(board(start, end, info))


@zona_api(["GET"], [CanView])
def analytics_staff_one(request, pk):
    """Bitta xodim: kunma-kun ish grafigi, soat × hafta kuni, guruhlar va so'nggi harakatlari."""
    from .activity import detail
    from .workload import period
    user = TgUser.objects.filter(pk=pk).select_related("member", "contact").first()
    if user is None or not user.is_staff:
        return Response({"detail": "Xodim topilmadi"}, status=404)
    start, end, info = period(request.query_params, max_days=3660)
    from .activity import evaluate
    return Response({**detail(user, start, end, info), "eval": evaluate(user, start, end)})


@zona_api(["GET"], [CanView])
def analytics_asker_one(request, pk):
    """Bitta agent: savollari, natijalari, mavzulari, kim javob berdi va tavsiyalar (o'rgatish / yordam)."""
    from .agents import detail
    from .workload import period
    user = TgUser.objects.filter(pk=pk).select_related("staff_person__project").first()
    if user is None:
        return Response({"detail": "Topilmadi"}, status=404)
    start, end, info = period(request.query_params, max_days=3660)
    return Response(detail(user, start, end, info))


@zona_api(["GET"], [CanView])
def analytics_speed(request):
    """Bot tezligi: savoldan javobgacha soniyalar, bosqichlar, soatlar, eng sekin savollar."""
    from .workload import speed
    from .workload import period
    start, end, info = period(request.query_params, default_days=7)
    return Response(speed(start, end, info))


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
        r["bot"] += stage in ("template", "faq", "rule", "ai", "image", "prbc")
        r["escalated"] += status == Message.ESCALATED
        if title:
            r["types"][title] += 1
        if group:
            r["groups"].add(group)
        r["last"] = max(r["last"], at) if r["last"] else at
    out = [{"user": uid, "name": r["name"], "username": r["username"], "staff_person": r["staff"], "questions": r["questions"],
            "bot": r["bot"], "escalated": r["escalated"], "groups": sorted(r["groups"]), "last": r["last"],
            "top_types": [{"title": t, "n": n} for t, n in r["types"].most_common(3)]} for uid, r in rows.items()]
    return sorted(out, key=lambda x: -x["questions"])[:3000]


def _zones(questions):
    """Savollar zonalar bo'yicha (topilgan yozuvning zonasi yoki mas'uli orqali)."""
    out = {}
    for zone, resp in questions.filter(entry__isnull=False).values_list("entry__zone__name", "entry__responsible__name"):
        key = zone or ("ProTarget va mobil ilova" if resp == "Pro-target" else "Boshqa")
        out[key] = out.get(key, 0) + 1
    return out


def _review_row(q, media):
    return {"id": q.id, "text": q.text, "ocr": (q.ocr_text or "")[:400], "problem": q.problem,
            "group": q.group.title if q.group_id else "", "link": q.group.message_link(q.message_id) if q.group_id else "",
            "user": q.user.name if q.user_id else "", "at": q.created_at, "answered_at": q.answered_at,
            "answer_text": q.answer_text, "answered_by": q.answered_by, "stage": q.stage, "confidence": q.confidence,
            "entry": q.entry_id, "entry_title": q.entry.title if q.entry_id else "", "feedback": q.feedback,
            "review": q.review, "review_by": q.review_by, "review_at": q.review_at, "review_note": q.review_note,
            "fixed_text": q.fixed_text, "fixed_by": q.fixed_by, "fixed_at": q.fixed_at, "sent": bool(q.fixed_msg_id),
            "category": q.category, "app": q.app, "hidden": q.answer_hidden, "media": [media_dict(m) for m in media]}


@zona_api(["GET"], [CanView])
def reviews(request):
    """Bot javoblari baholash ro'yxati (backend'da sahifalanadi). ?status=open|wrong|check|fixed|ok|all|none; ?q=; limit/offset.
    none — hali baholanmagan bot javoblari (tahlil uchun ko'rib chiqish)."""
    p = request.query_params
    base = Message.objects.filter(kind=Message.QUESTION).exclude(stage="dup").filter(Q(answered_by="bot") | ~Q(review=""))
    counts = dict(base.exclude(review="").values_list("review").annotate(c=Count("id")))
    counts["none"] = base.filter(review="").count()
    st = p.get("status") or "open"
    qs = base
    if st == "open":
        qs = qs.filter(review__in=["wrong", "check"])
    elif st == "none":
        qs = qs.filter(review="")
    elif st != "all":
        qs = qs.filter(review=st)
    if p.get("q"):
        qs = qs.filter(Q(text__icontains=p["q"]) | Q(answer_text__icontains=p["q"]) | Q(ocr_text__icontains=p["q"]))
    limit, offset = max(1, min(int(p.get("limit") or 20), 100)), max(0, int(p.get("offset") or 0))
    # xatolar birinchi, keyin yangilari
    qs = qs.order_by(Case(When(review="wrong", then=0), When(review="check", then=1), default=2), "-review_at", "-created_at")
    total = qs.count()
    rows = list(qs.select_related("group", "user", "entry")[offset:offset + limit])
    infos = dict(Message.objects.filter(question_id__in=[q.pk for q in rows], kind=Message.INFO).values_list("pk", "question_id"))
    media = {}
    for m in Media.objects.filter(message_id__in=[*[q.pk for q in rows], *infos]).select_related("label").order_by("id"):
        media.setdefault(infos.get(m.message_id, m.message_id), []).append(m)
    return Response({"count": total, "counts": counts, "results": [_review_row(q, media.get(q.pk, [])[:12]) for q in rows]})


def _bot_client(q):
    """Savol kelgan botning Telegram klienti (guruhdagi xabarni tahrirlash / yuborish uchun) yoki None."""
    from zona.crypto import decrypt

    from .telegram import Client
    token = decrypt(q.bot.token_enc) if q.bot_id else ""
    return Client(token) if token else None


@zona_api(["POST"], [ReadOrEdit])
def review_action(request, pk):
    """{"action": "wrong"|"ok"|"check"|"clear", "note"} yoki {"action": "fix", "text", "send": true, "learn": false}."""
    from . import review
    q = Message.objects.filter(pk=pk, kind=Message.QUESTION).select_related("bot", "group", "user", "entry").first()
    if q is None:
        return Response({"detail": "Topilmadi"}, status=404)
    act, actor = request.data.get("action"), _actor(request)
    if act in ("wrong", "ok", "check"):
        review.mark(q, act, actor, str(request.data.get("note") or ""))
        if act == "wrong":  # guruhda xato javob ko'rsatilmaydi ("yangilanishga yuborildi")
            review.hide(_bot_client(q), q)
        elif act == "ok":  # aslida to'g'ri edi — guruhda qayta ko'rsatiladi
            review.restore(_bot_client(q), q)
    elif act == "clear":
        Message.objects.filter(pk=pk).update(review="", review_by="", review_at=None, review_note="")
        review.restore(_bot_client(q), q)
    elif act == "fix":
        text = str(request.data.get("text") or "").strip()
        if not text:
            return Response({"detail": "To'g'ri javobni yozing"}, status=400)
        send, tg = bool(request.data.get("send", True)), None
        if send:
            tg = _bot_client(q)
            if tg is None:
                return Response({"detail": "Bot tokeni yo'q — guruhga yuborib bo'lmaydi"}, status=400)
        try:
            _q, entry = review.fix(q, text, actor, tg=tg, send=send, learn_kb=bool(request.data.get("learn")))
        except Exception as e:  # noqa: BLE001
            return Response({"detail": f"Guruhga yuborib bo'lmadi: {e}"[:300]}, status=502)
        q.refresh_from_db()
        return Response({**_review_row(q, []), "kb_entry": entry.id if entry else None})
    else:
        return Response({"detail": "action noto'g'ri"}, status=400)
    q.refresh_from_db()
    return Response(_review_row(q, []))


def _admin_resolve(questions, value, actor):
    """Admin qarori — yakuniy. Guruhdagi "hal bo'ldimi?" xabarlari fon oqimida yopiladi (panel kutib qolmaydi)."""
    import threading

    from django.db import close_old_connections

    from . import resolution
    for q in questions:
        resolution.admin_mark(q, value, actor)
    pending = [q.pk for q in questions if q.confirm_msg_id and value in ("yes", "no")]
    if not pending:
        return

    def close():
        from zona.crypto import decrypt

        from .telegram import Client
        close_old_connections()
        try:
            clients = {}
            for q in Message.objects.filter(pk__in=pending).select_related("bot"):
                token = decrypt(q.bot.token_enc) if q.bot_id else ""
                if not token:
                    continue
                tg = clients.setdefault(q.bot_id, Client(token))
                resolution.close_prompt(tg, q, value)
        finally:
            close_old_connections()
    threading.Thread(target=close, name="support-resolve", daemon=True).start()


def _systems(questions):
    """Qaysi guruh qaysi tizim bilan ishlaydi va xatolar qayerdan chiqadi: ilova (qayerda ko'rindi) / manba (sabab),
    toifalar, ilova -> manba juftlari (masalan, ProTarget'da ko'rindi, 1C'dan chiqdi), belgilash va o'qitish holati."""
    from collections import Counter, defaultdict
    qs = questions.exclude(stage="dup")
    rows = list(qs.values("group__title", "app", "origin", "category", "labeled_by", "resolution", "train"))
    groups = defaultdict(lambda: {"total": 0, "apps": Counter(), "origins": Counter(), "cats": Counter(), "yes": 0})
    pairs, apps, origins, cats, by = Counter(), Counter(), Counter(), Counter(), Counter()
    for r in rows:
        g = groups[r["group__title"] or "—"]
        g["total"] += 1
        g["yes"] += r["resolution"] == Message.YES
        if r["app"]:
            g["apps"][r["app"]] += 1
            apps[r["app"]] += 1
        if r["origin"]:
            g["origins"][r["origin"]] += 1
            origins[r["origin"]] += 1
        if r["category"]:
            g["cats"][r["category"]] += 1
            cats[r["category"]] += 1
        if r["app"] and r["origin"] and r["app"] != r["origin"]:
            pairs[(r["app"], r["origin"])] += 1
        by[r["labeled_by"] or "none"] += 1
    return {
        "apps": dict(apps), "origins": dict(origins), "categories": dict(cats.most_common()),
        "pairs": [{"app": a, "origin": o, "n": n} for (a, o), n in pairs.most_common(10)],
        "labeled": dict(by), "train": sum(1 for r in rows if r["train"]), "total": len(rows),
        "groups": [{"title": t, "total": g["total"], "apps": dict(g["apps"]), "origins": dict(g["origins"]),
                    "top": [{"category": c, "n": n} for c, n in g["cats"].most_common(4)], "resolved": g["yes"]}
                   for t, g in sorted(groups.items(), key=lambda x: -x[1]["total"])][:30],
    }


@zona_api(["GET"], [AdminOnly])
def training_export(request):
    """O'z AI modelimizni o'qitish uchun ma'lumot (JSONL). ?kb=0 — bilim bazasisiz; ?all=1 — AI tekshirmaganlar ham."""
    from django.http import StreamingHttpResponse

    from . import training
    if request.query_params.get("stats"):
        return Response(training.stats())
    resp = StreamingHttpResponse(training.export_lines(include_kb=request.query_params.get("kb") != "0",
                                                       only_train=request.query_params.get("all") != "1"),
                                 content_type="application/x-ndjson; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="support-training-{timezone.now():%Y%m%d}.jsonl"'
    return resp


@zona_api(["POST"], [ReadOrEdit])
def message_label(request, pk):
    """Xodim belgini tuzatadi (eng ishonchli: AI va qoidalar uni qayta yozmaydi)."""
    from . import systems
    q = Message.objects.filter(pk=pk, kind=Message.QUESTION).first()
    if q is None:
        return Response({"detail": "Topilmadi."}, status=404)
    upd = {"labeled_by": "staff", "label_conf": 100}
    for f, allowed in (("app", systems.APPS), ("origin", systems.ORIGINS), ("category", systems.CATEGORIES)):
        if f in request.data:
            v = str(request.data[f] or "")
            if v and v not in allowed:
                return Response({"detail": f"{f} noto'g'ri"}, status=400)
            upd[f] = v
    if "solution" in request.data:
        upd["solution"] = str(request.data["solution"] or "")[:2000]
    if "train" in request.data:
        upd["train"] = None if request.data["train"] is None else bool(request.data["train"])
    Message.objects.filter(pk=pk).update(**upd)
    return Response({k: v for k, v in upd.items()})


def _resolution(questions):
    """Savollar yakuni: hal bo'ldi (savol egasi tasdiqladi), hal bo'lmadi, tasdiq kutilmoqda, noma'lum."""
    from collections import Counter
    real =questions.exclude(status=Message.IGNORED).exclude(stage="dup")
    c = dict(real.values_list("resolution").annotate(n=Count("id")))
    yes, no, asked = c.get(Message.YES, 0), c.get(Message.NO, 0), c.get(Message.ASKED, 0)
    work = c.get(Message.WORK, 0)
    total = sum(c.values())
    by = Counter()
    for who, n in real.filter(resolution=Message.YES).values_list("resolved_by").annotate(n=Count("id")):
        # kim yopdi — guruhlab: savol egasi / xodim / panel (ism bilan emas, aks holda ro'yxat uzun va noaniq)
        key = ("savol egasi" if (who or "").startswith("savol egasi") else "xodim" if (who or "").startswith("xodim:")
               else "panel" if (who or "").startswith("panel: ") else (who or "—"))
        by[key] += n
    return {"total": total, "yes": yes, "no": no, "asked": asked, "work": work,
            "unknown": total - yes - no - asked - work,
            "rate": round(100 * yes / (yes + no)) if yes + no else None,
            "confirmed_share": round(100 * yes / total) if total else None,
            "by": [{"by": k, "n": v} for k, v in by.most_common(6)]}


def _protarget(questions, since, end=None):
    """Pro-target'ga tegishli savollar: turlari, javobsizlari va Pro-target jamoasi javoblari."""
    from collections import Counter
    from statistics import median

    from zona.models import TeamContact
    pt = questions.filter(Q(entry__responsible__name="Pro-target") | Q(entry__zone__name="ProTarget va mobil ilova")
                          | Q(entry__title__istartswith="ProTarget"))
    types = Counter(pt.values_list("entry__title", flat=True))
    team = set(TeamContact.objects.filter(member__name="Pro-target").values_list("name", flat=True))
    times = [max(0.0, (r.created_at - r.question.created_at).total_seconds())
             for r in Message.objects.filter(kind=Message.STAFF, question__in=questions)
             .select_related("user__contact", "user__member", "question") if r.user and r.user.staff_name() in team]
    return {"questions": pt.count(), "by_bot": pt.filter(stage__in=["template", "faq", "rule", "ai", "image", "prbc"]).count(),
            "unanswered": pt.exclude(status__in=[Message.ANSWERED, Message.CLOSED, Message.IGNORED]).count(),
            "types": [{"title": t, "n": n} for t, n in types.most_common(10)],
            "team_answers": len(times), "team_median_s": round(median(times), 1) if times else None}


# ====================================================================== fayllar va rasm turlari (o'rgatish)
def media_dict(m):
    from . import slim
    lean = m.slim or not m.path  # asl nusxa serverda yo'q — Telegram havolasi (va jonli bo'lsa — bot orqali asli)
    return {"id": m.id, "kind": m.kind, "name": m.name, "mime": m.mime, "size": m.size, "width": m.width, "height": m.height,
            "label": m.label_id, "label_title": m.label.title if m.label_id else "", "label_auto": m.label_auto,
            "ocr": (m.ocr_text or "")[:300], "source": m.source, "created_at": m.created_at, "available": bool(m.path),
            "slim": m.slim, "link": slim.link(m) if lean and m.message_id else ""}


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
    from django.http import FileResponse, Http404, HttpResponse
    m = Media.objects.filter(pk=pk).select_related("message__bot").first()
    if m and m.slim and request.query_params.get("full") == "1":
        # asl rasm serverda saqlanmaydi — bot orqali Telegram'dan (saqlamasdan) beriladi
        from . import slim
        data = slim.full_bytes(m)
        if data:
            resp = HttpResponse(data, content_type="image/jpeg")
            resp["Cache-Control"] = "private, max-age=3600"
            return resp
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
    """Rasm turlari: o'rgatilgan namunalar (yozuv bo'yicha) va yorliqsiz rasmlar guruhlari.
    Guruhlash og'ir — natija keshlanadi; rasmlar qo'shilsa/belgilansa/e'tiborsiz qilinsa kalit o'zgaradi (darhol yangilanadi)."""
    from django.core.cache import cache
    from django.db.models import Count, Max, Sum
    photos = Media.objects.filter(kind=Media.PHOTO)
    agg = photos.aggregate(n=Count("id"), last=Max("id"), lab=Count("label"), labsum=Sum("label_id"),
                           ign=Count("id", filter=Q(ignored=True)))
    s = Settings.load()
    # belgilash / e'tiborsiz qilish — kalit darhol o'zgaradi; yangi kelgan (belgilanmagan) rasmlar — har 25 tada yoki
    # 5 daqiqada (tarix o'rganilayotganda rasmlar har soniyada qo'shiladi — har so'rovda qayta guruhlamaslik uchun)
    from .models import ScreenType
    st = ScreenType.objects.aggregate(u=Max("updated_at"), n=Count("id"))
    scr = photos.filter(screen__isnull=False).count()
    key = (f"support:images2:{agg['n'] // 25}:{agg['lab']}:{agg['labsum']}:{agg['ign']}:{s.image_threshold}:{st['n']}:{st['u'].timestamp() if st['u'] else 0:.0f}:"
           f"{scr // 25}")
    hit = cache.get(key)
    if hit is not None:
        return Response(hit)
    data = _image_types(s)
    cache.set(key, data, 300)
    return Response(data)


def _image_types(s):
    from collections import Counter

    from django.db.models import Sum

    from . import screens, vision
    labeled = {}
    for lid, title, status, auto, sid in (Media.objects.filter(kind=Media.PHOTO, label__isnull=False)
                                          .values_list("label_id", "label__title", "label__status", "label_auto", "screen__title")):
        row = labeled.setdefault(lid, {"entry": lid, "title": title, "status": status, "count": 0, "auto": 0, "screens": Counter()})
        row["count"] += 1
        row["auto"] += int(auto)
        if sid:
            row["screens"][sid] += 1
    for row in labeled.values():
        row["screens"] = [t for t, _n in row["screens"].most_common(2)]
    # turga kirmagan (yangi ekranlar) — guruhlab ko'rsatiladi: yangi tur ochish, mavjud turga qo'shish yoki rad etish
    unl = (Media.objects.filter(kind=Media.PHOTO, screen__isnull=True, label__isnull=True, ignored=False).exclude(dhash="")
           .exclude(path="").select_related("message__group").order_by("-created_at")[:600])
    ign = Media.objects.filter(kind=Media.PHOTO, ignored=True).exclude(path="").order_by("-created_at")[:300]
    disk = Media.objects.exclude(path="").aggregate(n=Sum("size"))["n"] or 0
    saved = {"full": Media.objects.filter(slim=True).aggregate(n=Sum("full_size"))["n"],
             "now": Media.objects.filter(slim=True).exclude(path="").aggregate(n=Sum("size"))["n"]}
    ignored = [{"count": len(g), "ids": [m.id for m in g], "samples": [media_dict(m) for m in g[:4]]}
               for g in vision.clusters(list(ign), s.image_threshold)[:40]]
    groups = []
    for g in vision.clusters(list(unl), s.image_threshold)[:60]:
        guess, dist, _ = vision.match(g[0], s.image_threshold * 2, include_unapproved=True)
        groups.append({"count": len(g), "ids": [m.id for m in g], "samples": [media_dict(m) for m in g[:4]],
                       "ocr": next((m.ocr_text[:300] for m in g if m.ocr_text), ""),
                       "guess": guess.id if guess else None, "guess_title": guess.title if guess else ""})
    return {"labeled": sorted(labeled.values(), key=lambda r: -r["count"]), "unlabeled": groups, "ignored": ignored,
            "screens": screens.listing(media_dict), "threshold": s.image_threshold,
            "total": Media.objects.filter(kind=Media.PHOTO).count(),
            "storage": {"disk_mb": round(disk / 1e6, 1),
                        "saved_mb": round(max(0, (saved["full"] or 0) - (saved["now"] or 0)) / 1e6, 1),
                        "slim": Media.objects.filter(slim=True).count()}}


@zona_api(["POST"], [ReadOrEdit])
def screen_assign(request):
    """Rasmlarni ekran turiga qo'shish: mavjud turga (screen) yoki yangi tur (title) ochib."""
    from . import screens
    from .models import ScreenType
    ids = [int(x) for x in request.data.get("ids") or []][:1000]
    sid, title = request.data.get("screen"), (request.data.get("title") or "").strip()[:200]
    if sid:
        t = ScreenType.objects.filter(pk=sid).first()
        if not t:
            return Response({"detail": "Tur topilmadi"}, status=400)
    elif title:
        t = ScreenType.objects.create(title=title, title_locked=True, tag=(request.data.get("tag") or "")[:40])
    else:
        return Response({"detail": "Tur tanlang yoki nom yozing"}, status=400)
    if t.hidden:
        ScreenType.objects.filter(pk=t.pk).update(hidden=False)
    return Response({"done": screens.add_to(ids, t), "screen": t.id})


@zona_api(["PATCH", "DELETE"], [ReadOrEdit])
def screen_detail(request, pk):
    """Turni tahrirlash: nomi (qulflanadi), tegi, standart javobi; yashirish (rasmlari turga kirmagan bo'lib qoladi)."""
    from . import screens
    from .models import ScreenType
    t = ScreenType.objects.filter(pk=pk).first()
    if not t:
        return Response({"detail": "Tur topilmadi"}, status=404)
    if request.method == "DELETE":
        Media.objects.filter(screen=t).update(screen=None)
        ScreenType.objects.filter(pk=pk).update(hidden=True, count=0, hashes=[])
        screens._CACHE["key"] = None
        return Response({"done": True})
    d = request.data
    if "title" in d and (d.get("title") or "").strip():
        t.title, t.title_locked = d["title"].strip()[:200], True
    if "tag" in d:
        t.tag = (d.get("tag") or "")[:40]
        t.title_locked = True
    if "entry" in d:
        t.entry = Entry.objects.filter(pk=d.get("entry")).first() if d.get("entry") else None
    t.save()
    return Response({"done": True})


@zona_api(["POST"], [ReadOrEdit])
def screens_rebuild(request):
    """Rasmlarni qayta guruhlash (fonda, ~10–20 s)."""
    from . import screens
    screens.rebuild_async()
    return Response({"started": True})


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
    n = (qs.update(ignored=True, label=None, label_auto=False, label_by=_actor(request), screen=None) if flag
         else qs.update(ignored=False))
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
        "counts": {k: SupportTask.objects.filter(status=k).count() for k in ("queued", "sent", "failed", "skipped", "done")},
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
            "questions": u.n_questions if hasattr(u, "n_questions") else u.messages.filter(kind=Message.QUESTION).count(),
            "last_seen": u.last_seen, "msg_count": u.msg_count, "tg_id": u.tg_id,
            "real_name": u.real_name, "position": u.position, "department": u.department, "phone": u.phone}


@zona_api(["GET"], [CanView])
def tg_users(request):
    qs = TgUser.objects.select_related("staff_person__project", "staff_person__manager__manager", "member", "contact")
    if request.query_params.get("unlinked") == "1":
        qs = qs.filter(staff_person__isnull=True, member__isnull=True, contact__isnull=True)
    qs = qs.annotate(n_questions=Count("messages", filter=Q(messages__kind=Message.QUESTION)))  # bitta so'rovda
    return Response([_tg_user(u) for u in qs.order_by("-last_seen")[:5000]])


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
        if kind not in (AIJob.REVIEW_ENTRIES, AIJob.REVIEW_UNANSWERED, AIJob.DEDUPE, AIJob.VARIANTS, AIJob.LABELS):
            return Response({"detail": "Tahlil turini tanlang."}, status=400)
        if AIJob.objects.filter(status__in=[AIJob.QUEUED, AIJob.RUNNING]).exists():
            return Response({"detail": "AI tahlili allaqachon bajarilmoqda."}, status=400)
        AIJob.objects.create(kind=kind, created_by=_actor(request),
                             params={k: request.data[k] for k in ("scope", "limit", "days", "threshold", "auto", "ids", "relabel") if k in request.data})
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


@zona_api(["POST"], [IsZonaAdmin])
def groups_redirect(request):
    """Eski guruhlarni yangi guruhga yo'naltirish (bir nechtasini birdan): ids yoki not_admin=true (bot admin bo'lmagan
    barcha guruhlar); target=null — yo'naltirishni bekor qilish."""
    target = request.data.get("target")
    t = Group.objects.filter(pk=target).first() if target else None
    if target and t is None:
        return Response({"detail": "Guruh topilmadi"}, status=400)
    qs = Group.objects.filter(is_active=True)
    if request.data.get("not_admin"):
        qs = qs.filter(is_admin=False)
    else:
        qs = qs.filter(pk__in=[int(x) for x in request.data.get("ids") or []])
    if t is not None:
        qs = qs.exclude(pk=t.pk)
    return Response({"done": qs.update(redirect_to=t)})

