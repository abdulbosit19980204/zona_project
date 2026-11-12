"""Tasdiqlash jarayoni (Approval Workflows).

Har qanday foydalanuvchi mas'uliyat o'zgarishini taklif qiladi; muharrir yoki administrator tasdiqlaydi
yoki rad etadi. Tasdiqlangan o'zgarish shu zahoti qo'llanadi va tarixga yoziladi.
"""
from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from .auth import AUTHENTICATION
from .models import ChangeRequest, Event, Member, ProcessRole, Task
from .permissions import CanView, has_role
from .serializers import ChangeRequestSerializer
from .views import UNASSIGNED, log


def apply_change(req, request):
    """So'rovdagi o'zgarishni bazaga qo'llaydi. Holat o'zgargan bo'lsa (masalan, rol allaqachon olingan) — xato."""
    p = req.payload
    if req.kind == ChangeRequest.TASK_OWNER:
        task = Task.objects.select_related("owner").get(pk=p["task"])
        owner = Member.objects.get(pk=p["owner"]) if p.get("owner") else None
        old = task.owner
        task.owner = owner
        task.save(update_fields=["owner", "updated_at"])
        if owner:
            task.fallbacks.filter(member=owner).delete()
        log(request, Event.MOVED, subject=task.title, from_name=old.name if old else UNASSIGNED,
            to_name=owner.name if owner else UNASSIGNED)
    elif req.kind == ChangeRequest.ROLE_ADD:
        role, created = ProcessRole.objects.get_or_create(process_id=p["process"], member_id=p["member"], role=p["role"])
        if created:
            log(request, Event.ROLE, subject=role.process.name, to_name=role.member.name,
                text=f"{role.get_role_display()} etib belgilandi")
    else:
        role = ProcessRole.objects.select_related("process", "member").filter(pk=p["role_id"]).first()
        if role:
            log(request, Event.ROLE, subject=role.process.name, from_name=role.member.name,
                text=f"{role.get_role_display()} rolidan olindi")
            role.delete()


class ChangeRequestViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                           viewsets.GenericViewSet):
    serializer_class = ChangeRequestSerializer
    authentication_classes = AUTHENTICATION
    permission_classes = [CanView]
    renderer_classes = [JSONRenderer]
    parser_classes = [JSONParser]
    pagination_class = None

    def get_queryset(self):
        qs = ChangeRequest.objects.select_related("requested_by", "decided_by")
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        if self.request.query_params.get("mine") == "1":
            qs = qs.filter(requested_by=self.request.user)
        return qs

    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_queryset()[:300], many=True).data)

    def perform_create(self, serializer):
        if not self.request.user.is_authenticated:
            raise PermissionDenied("Taklif berish uchun tizimga kiring.")
        req = serializer.save(requested_by=self.request.user)
        log(self.request, Event.APPROVAL, subject=req.title, text="Tasdiqlash uchun yuborildi")

    def _decide(self, request, new_status):
        req = self.get_object()
        if req.status != ChangeRequest.PENDING:
            raise ValidationError("So'rov allaqachon ko'rib chiqilgan.")
        if new_status == ChangeRequest.CANCELLED:
            if req.requested_by != request.user:
                raise PermissionDenied("Faqat taklif muallifi bekor qila oladi.")
        elif not has_role(request, "editor"):
            raise PermissionDenied("Tasdiqlash uchun muharrir yoki administrator bo'lish kerak.")
        with transaction.atomic():
            if new_status == ChangeRequest.APPROVED:
                try:
                    apply_change(req, request)
                except (Task.DoesNotExist, Member.DoesNotExist, KeyError):
                    raise ValidationError("O'zgarishni qo'llab bo'lmadi: ma'lumot o'chirilgan yoki o'zgargan.") from None
            req.status = new_status
            req.decided_by = request.user
            req.decided_at = timezone.now()
            req.decision_note = str(request.data.get("note", ""))[:300]
            req.save()
            log(request, Event.APPROVAL, subject=req.title, text=req.get_status_display())
        return Response(ChangeRequestSerializer(req).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._decide(request, ChangeRequest.APPROVED)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._decide(request, ChangeRequest.REJECTED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._decide(request, ChangeRequest.CANCELLED)
