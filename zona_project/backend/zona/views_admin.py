"""Administrator: foydalanuvchilar, AI provayderlar, AI vazifa sozlamalari, AI sarf jurnali."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from . import translation
from .ai import providers
from .ai import service as ai_service
from .ai.providers import AIError
from .api import ZonaViewSet, zona_api
from .auth import AUTHENTICATION, revoke_all
from .models import AIProvider, AITaskConfig, AIUsage, Member, Profile
from .permissions import IsZonaAdmin, role_of
from .serializers import AIProviderSerializer, AITaskConfigSerializer, AIUsageSerializer, UserAdminSerializer

User = get_user_model()


class AdminMixin:
    authentication_classes = AUTHENTICATION
    permission_classes = [IsZonaAdmin]
    pagination_class = None
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]


class UserViewSet(AdminMixin, ZonaViewSet):
    serializer_class = UserAdminSerializer

    def get_queryset(self):
        return User.objects.select_related("zona_profile").order_by("username")

    def _admins_left(self, excluding):
        users = User.objects.filter(is_active=True).exclude(pk=excluding.pk).select_related("zona_profile")
        return any(role_of(u) == Profile.ADMIN for u in users)

    def perform_update(self, serializer):
        user = serializer.instance
        new_role = serializer.validated_data.get("role")
        deactivating = serializer.validated_data.get("is_active") is False
        if role_of(user) == Profile.ADMIN and ((new_role and new_role != Profile.ADMIN and not user.is_superuser)
                                               or deactivating) and not self._admins_left(user):
            raise ValidationError("Oxirgi administratorni o'chirib yoki pasaytirib bo'lmaydi.")
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            return Response({"detail": "O'zingizni o'chira olmaysiz."}, status=status.HTTP_400_BAD_REQUEST)
        if role_of(user) == Profile.ADMIN and not self._admins_left(user):
            return Response({"detail": "Oxirgi administratorni o'chirib bo'lmaydi."}, status=status.HTTP_400_BAD_REQUEST)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="revoke-tokens")
    def revoke_tokens(self, request, pk=None):
        return Response({"revoked": revoke_all(self.get_object())})


class AIProviderViewSet(AdminMixin, ZonaViewSet):
    queryset = AIProvider.objects.all()
    serializer_class = AIProviderSerializer

    @action(detail=False, methods=["get"])
    def kinds(self, request):
        return Response([{"kind": k, "label": label, **providers.PRESETS.get(k, {})} for k, label in AIProvider.KINDS])

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Ulanishni tekshirish va modellar ro'yxatini yangilash."""
        p = self.get_object()
        p.last_check_at = timezone.now()
        try:
            res = providers.check(p)
        except AIError as e:
            p.last_check_ok, p.last_error = False, str(e)[:500]
            p.save(update_fields=["last_check_at", "last_check_ok", "last_error"])
            return Response({"ok": False, "error": p.last_error}, status=status.HTTP_200_OK)
        p.last_check_ok, p.last_error, p.models_cache = True, "", res["models"][:500]
        p.save(update_fields=["last_check_at", "last_check_ok", "last_error", "models_cache"])
        return Response({"ok": True, "models": p.models_cache, "latency_ms": res["latency_ms"]})


class AITaskViewSet(AdminMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                    viewsets.GenericViewSet):
    serializer_class = AITaskConfigSerializer
    lookup_field = "task"

    def get_queryset(self):
        ai_service.ensure_tasks()
        return AITaskConfig.objects.all()

    @action(detail=True, methods=["post"])
    def test(self, request, task=None):
        """Sozlamani haqiqiy so'rov bilan sinash (tokenlar sarflanadi)."""
        cfg = self.get_object()
        try:
            if cfg.task == AITaskConfig.ROUTE:
                q = str(request.data.get("question") or "Parolimni unutdim, ProTargetga kira olmayapman")
                data, meta = ai_service.route(q, request.user)
            elif cfg.task == AITaskConfig.PERSON:
                m = Member.objects.first()
                if not m:
                    return Response({"ok": False, "error": "Xodim yo'q"})
                data, meta = ai_service.person(m.id, request.user)
            elif cfg.task == AITaskConfig.TRANSLATE:
                text = str(request.data.get("text") or "Klientni boshqa agentga o'tkazish")
                translated, error = translation.translate_texts([text], request.user)
                if text not in translated:
                    return Response({"ok": False, "error": error or "AI tarjima qaytarmadi"})
                tr = translated[text]
                return Response({"ok": True, "result": {"text": f"RU: {tr['ru']} · EN: {tr['en']}", **tr},
                                 "meta": {"model": cfg.model, "latency_ms": 0}})
            else:
                data, meta = ai_service.audit(request.user)
        except AIError as e:
            return Response({"ok": False, "error": str(e)})
        return Response({"ok": True, "result": data, "meta": meta})


class AIUsageViewSet(AdminMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AIUsageSerializer

    def get_queryset(self):
        return AIUsage.objects.all()[:200]

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """AI sarfi: modellar, vazifalar, kunlar bo'yicha; xatolar turi; hozir band modellar; support kunlik limiti."""
        from collections import defaultdict

        from django.db.models import Avg
        days = max(1, min(int(request.query_params.get("days") or 30), 365))
        since = timezone.now() - timedelta(days=days)
        qs = AIUsage.objects.filter(at__gte=since)
        rows = (qs.values("provider", "model")
                .annotate(calls=Count("id"), errors=Count("id", filter=Q(ok=False)),
                          input_tokens=Sum("input_tokens"), output_tokens=Sum("output_tokens"), latency=Avg("latency_ms"))
                .order_by("-calls"))
        by_task = (qs.values("task").annotate(calls=Count("id"), errors=Count("id", filter=Q(ok=False)),
                                              tokens=Sum("input_tokens") + Sum("output_tokens")).order_by("-calls"))
        daily = defaultdict(lambda: {"calls": 0, "errors": 0, "tokens": 0})
        kinds = defaultdict(int)
        for at, ok, err, tin, tout in qs.values_list("at", "ok", "error", "input_tokens", "output_tokens"):
            d = daily[timezone.localtime(at).date().isoformat()]
            d["calls"] += 1
            d["tokens"] += (tin or 0) + (tout or 0)
            if not ok:
                d["errors"] += 1
                e = (err or "").lower()
                kinds["limit" if ("429" in e or "rate" in e or "quota" in e) else "busy" if ("503" in e or "demand" in e or "overload" in e)
                      else "key" if ("401" in e or "403" in e or "kalit" in e or "api key" in e) else "other"] += 1
        recent = timezone.now() - timedelta(minutes=10)
        busy = list(AIUsage.objects.filter(at__gte=recent, ok=False).values("provider", "model").annotate(n=Count("id")).order_by("-n")[:10])
        today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        support_limit = None
        try:
            from support.engine import ai_quota_left
            from support.models import Settings as SupportSettings
            ss = SupportSettings.load()
            support_limit = {"limit": ss.ai_daily_limit, "left": ai_quota_left(ss), "enabled": ss.ai_enabled}
        except Exception:  # noqa: BLE001 — support ilovasi bo'lmasa ham ishlasin
            pass
        return Response({
            "since": since, "days": days, "models": list(rows), "tasks": list(by_task),
            "daily": [{"date": k, **v} for k, v in sorted(daily.items())],
            "error_kinds": dict(kinds), "busy_now": busy,
            "today": qs.filter(at__gte=today).aggregate(calls=Count("id"), errors=Count("id", filter=Q(ok=False)),
                                                        tokens=Sum("input_tokens") + Sum("output_tokens")),
            "totals": qs.aggregate(calls=Count("id"), errors=Count("id", filter=Q(ok=False)), input_tokens=Sum("input_tokens"),
                                   output_tokens=Sum("output_tokens"), latency=Avg("latency_ms")),
            "support_limit": support_limit,
        })


@zona_api(["GET", "POST"], [IsZonaAdmin])
def translate(request):
    """Tarjima holati (GET) yoki tarjimasi yo'q barcha matnlarni fonda tarjima qilishni boshlash (POST)."""
    if request.method == "POST":
        # avval tarjima xotirasidan (AI'siz, darhol); AI yoqilgan bo'lsa — qolganini fonda
        filled = translation.translate_pending(request.user, use_ai=False)
        if translation.enabled():
            translation.start()
        return Response({**translation.status(), "filled": filled})
    return Response(translation.status())
