from datetime import datetime

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from . import conf
from .ai import service as ai_service
from .api import ZonaViewSet, zona_api
from .exporter import workbook_bytes
from .models import (Authority, ChangeRequest, Department, EdgeCase, Event, Member, Process, ProcessRole, Synonym,
                     System, Task, Team)
from .permissions import CanView, ReadOrEdit, role_of
from .search import debug as search_debug
from .search import search as run_search
from .serializers import (AuthoritySerializer, DepartmentSerializer, EdgeCaseSerializer, EventSerializer,
                          MemberSerializer, ProcessRoleSerializer, ProcessSerializer, SynonymSerializer,
                          SystemSerializer, TaskSerializer, TeamSerializer, user_payload)

UNASSIGNED = "Biriktirilmagan"


def _name(member):
    return member.name if member else UNASSIGNED


def log(request, kind, **fields):
    user = getattr(request, "user", None)
    Event.objects.create(kind=kind, actor=user.get_username() if user and user.is_authenticated else "", **fields)


def index(request):
    """API haqida qisqa ma'lumot. Interfeys — alohida Next.js ilova (frontend/)."""
    return JsonResponse({"name": conf.get("TITLE"), "api": reverse("zona:index") + "api/",
                         "websocket": "/ws/events/", "frontend": conf.get("FRONTEND_URL") or None})


@zona_api(["GET"], [CanView])
def state(request):
    """Frontend bir so'rov bilan butun tuzilmani oladi."""
    user = request.user if request.user.is_authenticated else None
    return Response({
        "meta": {
            "company": conf.get("COMPANY_NAME"),
            "title": conf.get("TITLE"),
            "ai": ai_service.status(),
            "pending_approvals": ChangeRequest.objects.filter(status=ChangeRequest.PENDING).count(),
        },
        "me": user_payload(user) if user else {"role": role_of(None) or "viewer", "can": {"edit": False, "admin": False},
                                                "anonymous": True},
        "departments": DepartmentSerializer(Department.objects.all(), many=True).data,
        "teams": TeamSerializer(Team.objects.all(), many=True).data,
        "members": MemberSerializer(Member.objects.all(), many=True).data,
        "authorities": AuthoritySerializer(Authority.objects.all(), many=True).data,
        "systems": SystemSerializer(System.objects.all(), many=True).data,
        "processes": ProcessSerializer(Process.objects.all(), many=True).data,
        "roles": ProcessRoleSerializer(ProcessRole.objects.all(), many=True).data,
        "tasks": TaskSerializer(Task.objects.prefetch_related("fallbacks"), many=True).data,
        "edge_cases": EdgeCaseSerializer(EdgeCase.objects.all(), many=True).data,
    })


@zona_api(["GET"], [CanView])
def events(request):
    try:
        limit = max(1, min(int(request.query_params.get("limit", 50)), 300))
    except ValueError:
        limit = 50
    return Response(EventSerializer(Event.objects.all()[:limit], many=True).data)


@zona_api(["GET"], [CanView])
def search(request):
    """Ko'p tilli qidiruv: odamlar (kimga), vazifalar, jarayonlar, xodimlar, aralash holatlar."""
    q = request.query_params.get("q", "")[:500]
    try:
        limit = max(1, min(int(request.query_params.get("limit", 12)), 50))
    except ValueError:
        limit = 12
    return Response(run_search(q, limit))


@zona_api(["GET"], [ReadOrEdit])
def search_explain(request):
    """Lug'atni sinash: so'rov qanday o'zaklarga ajraldi, nimalar qo'shildi."""
    return Response(search_debug(request.query_params.get("q", "")[:300]))


class DepartmentViewSet(ZonaViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer

    def perform_create(self, serializer):
        dep = serializer.save(order=self.next_order())
        log(self.request, Event.MEMBER, to_name=dep.name, text="Yangi bo'lim qo'shildi")

    def perform_destroy(self, instance):
        log(self.request, Event.MEMBER, from_name=instance.name,
            text=f"Bo'lim o'chirildi, {instance.members.count()} xodim bo'limsiz qoldi")
        instance.delete()


class TeamViewSet(ZonaViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer

    def perform_create(self, serializer):
        team = serializer.save(order=self.next_order())
        log(self.request, Event.MEMBER, to_name=team.name, text=f"Yangi jamoa: {team.department.name}")

    def perform_destroy(self, instance):
        log(self.request, Event.MEMBER, from_name=instance.name,
            text=f"Jamoa o'chirildi, {instance.members.count()} xodim jamoasiz qoldi")
        instance.delete()


class SystemViewSet(ZonaViewSet):
    queryset = System.objects.all()
    serializer_class = SystemSerializer

    def perform_create(self, serializer):
        serializer.save(order=self.next_order())


class MemberViewSet(ZonaViewSet):
    queryset = Member.objects.all()
    serializer_class = MemberSerializer

    def perform_create(self, serializer):
        member = serializer.save(order=self.next_order())
        log(self.request, Event.MEMBER, to_name=member.name, text=f"Yangi xodim: {member.role}")

    def perform_update(self, serializer):
        member = serializer.save()
        log(self.request, Event.EDITED, subject=member.name, text="Xodim kartasi yangilandi")

    def perform_destroy(self, instance):
        count = instance.tasks.count()
        log(self.request, Event.MEMBER, from_name=instance.name,
            text=f"Xodim o'chirildi, {count} ta vazifa \"{UNASSIGNED}\" bo'limiga tushdi")
        instance.delete()


class AuthorityViewSet(ZonaViewSet):
    queryset = Authority.objects.select_related("member")
    serializer_class = AuthoritySerializer

    def perform_create(self, serializer):
        a = serializer.save(order=self.next_order())
        log(self.request, Event.ROLE, subject=a.title, to_name=a.member.name, text="Vakolat berildi")

    def perform_destroy(self, instance):
        log(self.request, Event.ROLE, subject=instance.title, from_name=instance.member.name, text="Vakolat olindi")
        instance.delete()


class ProcessViewSet(ZonaViewSet):
    queryset = Process.objects.all()
    serializer_class = ProcessSerializer

    def perform_create(self, serializer):
        p = serializer.save(order=self.next_order())
        log(self.request, Event.CREATED, subject=p.name, text="Yangi jarayon")

    def perform_destroy(self, instance):
        log(self.request, Event.DELETED, subject=instance.name,
            text=f"Jarayon o'chirildi, {instance.tasks.count()} ta vazifa jarayonsiz qoldi")
        instance.delete()


class ProcessRoleViewSet(ZonaViewSet):
    queryset = ProcessRole.objects.select_related("process", "member")
    serializer_class = ProcessRoleSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    def perform_create(self, serializer):
        r = serializer.save()
        log(self.request, Event.ROLE, subject=r.process.name, to_name=r.member.name,
            text=f"{r.get_role_display()} etib belgilandi")

    def perform_destroy(self, instance):
        log(self.request, Event.ROLE, subject=instance.process.name, from_name=instance.member.name,
            text=f"{instance.get_role_display()} rolidan olindi")
        instance.delete()


class EdgeCaseViewSet(ZonaViewSet):
    queryset = EdgeCase.objects.all()
    serializer_class = EdgeCaseSerializer

    def perform_create(self, serializer):
        serializer.save(order=self.next_order())


class SynonymViewSet(ZonaViewSet):
    queryset = Synonym.objects.all()
    serializer_class = SynonymSerializer


class TaskViewSet(ZonaViewSet):
    queryset = Task.objects.prefetch_related("fallbacks")
    serializer_class = TaskSerializer

    def perform_create(self, serializer):
        task = serializer.save(is_custom=True, order=self.next_order())
        log(self.request, Event.CREATED, subject=task.title, to_name=_name(task.owner))

    def perform_update(self, serializer):
        old_owner = serializer.instance.owner
        task = serializer.save()
        if old_owner != task.owner:
            log(self.request, Event.MOVED, subject=task.title, from_name=_name(old_owner), to_name=_name(task.owner))
        else:
            log(self.request, Event.EDITED, subject=task.title, to_name=_name(task.owner))

    def perform_destroy(self, instance):
        log(self.request, Event.DELETED, subject=instance.title, from_name=_name(instance.owner))
        instance.delete()

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        """Vazifani boshqa mas'ulga o'tkazish: {"owner": id | null}."""
        task = self.get_object()
        owner = self._owner_from(request.data)
        if owner is False:
            return Response({"owner": "Bunday xodim yo'q."}, status=status.HTTP_400_BAD_REQUEST)
        self._move(task, owner)
        return Response(TaskSerializer(task).data)

    @action(detail=False, methods=["post"], url_path="bulk-move")
    def bulk_move(self, request):
        """Bir nechta vazifani birdan o'tkazish: {"ids": [..], "owner": id | null}."""
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            return Response({"ids": "Vazifalar ro'yxati kerak."}, status=status.HTTP_400_BAD_REQUEST)
        owner = self._owner_from(request.data)
        if owner is False:
            return Response({"owner": "Bunday xodim yo'q."}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            moved = sum(self._move(t, owner) for t in Task.objects.filter(pk__in=ids).select_related("owner"))
        return Response({"moved": moved})

    def _move(self, task, owner):
        if task.owner == owner:
            return 0
        old = task.owner
        task.owner = owner
        task.save(update_fields=["owner", "updated_at"])
        if owner:
            task.fallbacks.filter(member=owner).delete()
        log(self.request, Event.MOVED, subject=task.title, from_name=_name(old), to_name=_name(owner))
        return 1

    @staticmethod
    def _owner_from(data):
        raw = data.get("owner")
        if raw in (None, "", 0):
            return None
        try:
            return Member.objects.get(pk=int(raw))
        except (Member.DoesNotExist, ValueError, TypeError):
            return False


@zona_api(["GET"], [CanView])
def export_xlsx(request):
    members = list(Member.objects.select_related("department"))
    processes = list(Process.objects.select_related("system"))
    tasks = list(Task.objects.select_related("owner", "process__system").prefetch_related("fallbacks"))
    roles = list(ProcessRole.objects.all())
    auths = list(Authority.objects.all())
    edges = [(e.situation, _name(e.first_owner), e.then_text) for e in EdgeCase.objects.select_related("first_owner")]
    content = workbook_bytes(conf.get("COMPANY_NAME"), members, processes, tasks, roles, edges, auths)
    stamp = datetime.now(timezone.get_current_timezone()).strftime("%Y-%m-%d")
    resp = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="masuliyat_{stamp}.xlsx"'
    return resp
