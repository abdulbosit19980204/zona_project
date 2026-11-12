from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from .crypto import decrypt, encrypt, mask
from .models import (AIProvider, AITaskConfig, AIUsage, Authority, ChangeRequest, Department, EdgeCase, Event, Member,
                     Process, ProcessRole, Profile, Synonym, System, Task, TaskFallback, Team)
from .permissions import role_of

User = get_user_model()


def _not_blank(value, msg):
    value = (value or "").strip()
    if not value:
        raise serializers.ValidationError(msg)
    return value


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "description", "order"]
        read_only_fields = ["order"]

    def validate_name(self, value):
        return _not_blank(value, "Nomi bo'sh bo'lmasin.")


class SystemSerializer(serializers.ModelSerializer):
    class Meta:
        model = System
        fields = ["id", "name", "order"]
        read_only_fields = ["order"]


class TeamSerializer(serializers.ModelSerializer):
    lead = serializers.PrimaryKeyRelatedField(queryset=Member.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Team
        fields = ["id", "department", "name", "description", "lead", "order"]
        read_only_fields = ["order"]

    def validate_name(self, value):
        return _not_blank(value, "Jamoa nomi bo'sh bo'lmasin.")


class MemberSerializer(serializers.ModelSerializer):
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all(), allow_null=True, required=False)
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all(), allow_null=True, required=False)
    manager = serializers.PrimaryKeyRelatedField(queryset=Member.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Member
        fields = ["id", "name", "role", "department", "team", "manager", "is_team", "trigger", "does", "excludes",
                  "email", "phone", "telegram", "location", "order"]
        read_only_fields = ["order"]

    def validate_name(self, value):
        return _not_blank(value, "Ism bo'sh bo'lmasin.")

    def validate_telegram(self, value):
        return value.strip().lstrip("@")

    def validate(self, attrs):
        team = attrs.get("team")
        if team:
            # jamoa tanlansa, bo'lim jamoaning bo'limi bo'ladi
            dep = attrs.get("department", self.instance.department if self.instance else None)
            if dep and dep != team.department:
                raise serializers.ValidationError({"team": "Jamoa tanlangan bo'limga tegishli emas."})
            attrs["department"] = team.department
        manager = attrs.get("manager")
        if manager and self.instance:
            node, seen = manager, set()
            while node and node.pk not in seen:
                if node.pk == self.instance.pk:
                    raise serializers.ValidationError({"manager": "Xodim o'ziga yoki o'z qo'l ostidagiga bo'ysuna olmaydi."})
                seen.add(node.pk)
                node = node.manager
        return attrs


class AuthoritySerializer(serializers.ModelSerializer):
    class Meta:
        model = Authority
        fields = ["id", "member", "title", "scope", "order"]
        read_only_fields = ["order"]

    def validate_title(self, value):
        return _not_blank(value, "Vakolat matni bo'sh bo'lmasin.")


class ProcessSerializer(serializers.ModelSerializer):
    system = serializers.PrimaryKeyRelatedField(queryset=System.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Process
        fields = ["id", "name", "system", "description", "order"]
        read_only_fields = ["order"]

    def validate_name(self, value):
        return _not_blank(value, "Jarayon nomi bo'sh bo'lmasin.")


class ProcessRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessRole
        fields = ["id", "process", "member", "role"]
        validators = []

    def validate(self, attrs):
        if ProcessRole.objects.filter(process=attrs["process"], member=attrs["member"], role=attrs["role"]).exists():
            raise serializers.ValidationError("Bu xodimda shu rol allaqachon bor.")
        return attrs


class TaskFallbackSerializer(serializers.Serializer):
    member = serializers.PrimaryKeyRelatedField(queryset=Member.objects.all())
    condition = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")

    def to_representation(self, obj):
        return {"member": obj.member_id, "condition": obj.condition}


class TaskSerializer(serializers.ModelSerializer):
    process = serializers.PrimaryKeyRelatedField(queryset=Process.objects.all(), allow_null=True, required=False)
    owner = serializers.PrimaryKeyRelatedField(queryset=Member.objects.all(), allow_null=True, required=False)
    # 2-, 3-... navbatdagi mas'ullar, tartib bilan. Yuborilsa, ro'yxat to'liq almashtiriladi.
    fallbacks = TaskFallbackSerializer(many=True, required=False)

    class Meta:
        model = Task
        fields = ["id", "title", "process", "owner", "fallbacks", "note", "is_custom", "order"]
        read_only_fields = ["is_custom", "order"]

    def validate_title(self, value):
        return _not_blank(value, "Vazifa matni bo'sh bo'lmasin.")

    def validate(self, attrs):
        if "fallbacks" in attrs:
            owner = attrs.get("owner", self.instance.owner if self.instance else None)
            seen = {owner.pk} if owner else set()
            for item in attrs["fallbacks"]:
                if item["member"].pk in seen:
                    raise serializers.ValidationError(
                        {"fallbacks": "Bir xodim navbatda ikki marta yoki asosiy mas'ul bilan birga bo'lmasin."})
                seen.add(item["member"].pk)
                item["condition"] = (item.get("condition") or "").strip()
        return attrs

    @transaction.atomic
    def create(self, validated):
        fallbacks = validated.pop("fallbacks", None)
        task = super().create(validated)
        if fallbacks is not None:
            self._set_fallbacks(task, fallbacks)
        return task

    @transaction.atomic
    def update(self, instance, validated):
        fallbacks = validated.pop("fallbacks", None)
        task = super().update(instance, validated)
        if fallbacks is not None:
            self._set_fallbacks(task, fallbacks)
        elif "owner" in validated and task.owner_id:
            # yangi asosiy mas'ul navbatda ham turgan bo'lsa, navbatdan chiqadi
            task.fallbacks.filter(member_id=task.owner_id).delete()
        return task

    @staticmethod
    def _set_fallbacks(task, items):
        task.fallbacks.all().delete()
        TaskFallback.objects.bulk_create([
            TaskFallback(task=task, member=i["member"], condition=i["condition"], order=n)
            for n, i in enumerate(items, start=2)])
        if hasattr(task, "_prefetched_objects_cache"):
            task._prefetched_objects_cache.pop("fallbacks", None)


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ["id", "kind", "subject", "from_name", "to_name", "text", "actor", "at"]


class EdgeCaseSerializer(serializers.ModelSerializer):
    first_owner = serializers.PrimaryKeyRelatedField(queryset=Member.objects.all(), allow_null=True, required=False)

    class Meta:
        model = EdgeCase
        fields = ["id", "situation", "first_owner", "then_text", "order"]
        read_only_fields = ["order"]


class SynonymSerializer(serializers.ModelSerializer):
    class Meta:
        model = Synonym
        fields = ["id", "words"]

    def validate_words(self, value):
        words = [w.strip() for w in value.replace("\n", ",").split(",") if w.strip()]
        if len(words) < 2:
            raise serializers.ValidationError("Kamida ikkita so'z kiriting (vergul bilan).")
        return ", ".join(dict.fromkeys(words))


# ---------------------------------------------------------------- tasdiqlash jarayoni
def _user_name(user):
    return (user.get_full_name() or user.username) if user else ""


class ChangeRequestSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.SerializerMethodField()
    decided_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ChangeRequest
        fields = ["id", "kind", "payload", "title", "reason", "status", "requested_by", "requested_by_name",
                  "decided_by", "decided_by_name", "decision_note", "created_at", "decided_at"]
        read_only_fields = ["title", "status", "requested_by", "decided_by", "decision_note", "created_at", "decided_at"]

    def get_requested_by_name(self, obj):
        return _user_name(obj.requested_by)

    def get_decided_by_name(self, obj):
        return _user_name(obj.decided_by)

    def validate(self, attrs):
        """Taklif mazmunini tekshiradi va sarlavhasini tuzadi: tasdiqlanganda xatosiz qo'llanishi kerak."""
        kind, p = attrs["kind"], attrs.get("payload") or {}
        try:
            if kind == ChangeRequest.TASK_OWNER:
                task = Task.objects.get(pk=int(p["task"]))
                owner = Member.objects.get(pk=int(p["owner"])) if p.get("owner") else None
                if task.owner == owner:
                    raise serializers.ValidationError("Vazifa allaqachon shu xodimda.")
                attrs["payload"] = {"task": task.id, "owner": owner.id if owner else None}
                attrs["title"] = f"\"{task.title}\" → {owner.name if owner else 'Biriktirilmagan'}"
            elif kind == ChangeRequest.ROLE_ADD:
                process, member = Process.objects.get(pk=int(p["process"])), Member.objects.get(pk=int(p["member"]))
                role = str(p["role"])
                if role not in dict(ProcessRole.ROLES):
                    raise serializers.ValidationError("Noma'lum rol.")
                if ProcessRole.objects.filter(process=process, member=member, role=role).exists():
                    raise serializers.ValidationError("Bu xodimda shu rol allaqachon bor.")
                attrs["payload"] = {"process": process.id, "member": member.id, "role": role}
                attrs["title"] = f"{member.name}: {dict(ProcessRole.ROLES)[role]} — {process.name}"
            else:
                r = ProcessRole.objects.select_related("process", "member").get(pk=int(p["role_id"]))
                attrs["payload"] = {"role_id": r.id}
                attrs["title"] = f"{r.member.name}: {r.get_role_display()} rolidan olish — {r.process.name}"
        except (KeyError, ValueError, TypeError, Task.DoesNotExist, Member.DoesNotExist, Process.DoesNotExist,
                ProcessRole.DoesNotExist):
            raise serializers.ValidationError("Taklif ma'lumotlari noto'g'ri yoki eskirgan.") from None
        return attrs


# ---------------------------------------------------------------- foydalanuvchilar
PROFILE_FIELDS = ["position", "phone", "telegram", "address", "note"]


def user_payload(user):
    profile = getattr(user, "zona_profile", None) or Profile.objects.get_or_create(user=user)[0]
    role = role_of(user)
    return {
        "id": user.id, "username": user.username, "first_name": user.first_name, "last_name": user.last_name,
        "full_name": user.get_full_name() or user.username, "email": user.email, "is_active": user.is_active,
        "is_superuser": user.is_superuser, "role": role, "member": profile.member_id,
        **{f: getattr(profile, f) for f in PROFILE_FIELDS},
        "last_login": user.last_login, "date_joined": user.date_joined,
        "can": {"edit": role in (Profile.ADMIN, Profile.EDITOR), "admin": role == Profile.ADMIN},
    }


class UserAdminSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    role = serializers.ChoiceField(choices=Profile.ROLES, required=False)
    member = serializers.PrimaryKeyRelatedField(queryset=Member.objects.all(), allow_null=True, required=False)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, style={"input_type": "password"})
    position = serializers.CharField(max_length=120, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    telegram = serializers.CharField(max_length=64, required=False, allow_blank=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_username(self, value):
        value = value.strip()
        qs = User.objects.filter(username__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu login band.")
        return value

    def validate(self, attrs):
        pw = attrs.get("password")
        if not self.instance and not pw:
            raise serializers.ValidationError({"password": "Yangi foydalanuvchi uchun parol kerak."})
        if pw:
            validate_password(pw, self.instance)
        return attrs

    @transaction.atomic
    def save(self):
        data = dict(self.validated_data)
        user = self.instance or User(username=data["username"])
        for f in ("username", "first_name", "last_name", "email", "is_active"):
            if f in data:
                setattr(user, f, data[f])
        if data.get("password"):
            user.set_password(data["password"])
        user.save()
        profile, _ = Profile.objects.get_or_create(user=user)
        for f in PROFILE_FIELDS + ["role", "member"]:
            if f in data:
                setattr(profile, f, data[f])
        profile.save()
        user.zona_profile = profile
        self.instance = user
        return user

    def to_representation(self, user):
        return user_payload(user)


class MeSerializer(UserAdminSerializer):
    """O'z profilini tahrirlash: rol, faollik va xodim bog'lanishini o'zgartirib bo'lmaydi."""

    def validate(self, attrs):
        for f in ("role", "is_active", "member", "password", "username"):
            attrs.pop(f, None)
        return attrs


# ---------------------------------------------------------------- AI
class AIProviderSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    api_key_masked = serializers.SerializerMethodField()
    has_key = serializers.SerializerMethodField()

    class Meta:
        model = AIProvider
        fields = ["id", "name", "kind", "base_url", "api_version", "is_active", "api_key", "api_key_masked",
                  "has_key", "models_cache", "last_check_at", "last_check_ok", "last_error", "updated_at"]
        read_only_fields = ["models_cache", "last_check_at", "last_check_ok", "last_error", "updated_at"]

    def get_api_key_masked(self, obj):
        return mask(decrypt(obj.api_key_enc))

    def get_has_key(self, obj):
        return bool(obj.api_key_enc)

    def validate_base_url(self, value):
        value = value.strip()
        if value and not value.startswith(("http://", "https://")):
            raise serializers.ValidationError("Manzil http:// yoki https:// bilan boshlansin.")
        return value

    def _apply_key(self, validated):
        key = validated.pop("api_key", None)
        if key is not None and key.strip():
            validated["api_key_enc"] = encrypt(key.strip())
        return validated

    def create(self, validated):
        return super().create(self._apply_key(validated))

    def update(self, instance, validated):
        validated = self._apply_key(validated)
        if "kind" in validated and validated["kind"] != instance.kind:
            validated["models_cache"] = []
        return super().update(instance, validated)


class AITaskConfigSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_task_display", read_only=True)
    provider = serializers.PrimaryKeyRelatedField(queryset=AIProvider.objects.all(), allow_null=True, required=False)
    fallback_provider = serializers.PrimaryKeyRelatedField(queryset=AIProvider.objects.all(), allow_null=True, required=False)

    class Meta:
        model = AITaskConfig
        fields = ["task", "label", "enabled", "provider", "model", "effort", "temperature", "max_tokens",
                  "fallback_provider", "fallback_model", "instructions", "updated_at"]
        read_only_fields = ["task", "updated_at"]

    def validate_max_tokens(self, value):
        if not 256 <= value <= 128000:
            raise serializers.ValidationError("256 dan 128000 gacha.")
        return value

    def validate_temperature(self, value):
        if value is not None and not 0 <= value <= 2:
            raise serializers.ValidationError("0 dan 2 gacha.")
        return value

    def validate(self, attrs):
        enabled = attrs.get("enabled", self.instance.enabled if self.instance else False)
        provider = attrs.get("provider", self.instance.provider if self.instance else None)
        model = attrs.get("model", self.instance.model if self.instance else "")
        if enabled and (not provider or not model):
            raise serializers.ValidationError("Yoqish uchun provayder va model tanlang.")
        return attrs


class AIUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIUsage
        fields = ["id", "task", "provider", "model", "ok", "error", "input_tokens", "output_tokens", "latency_ms",
                  "user", "prompt", "at"]
