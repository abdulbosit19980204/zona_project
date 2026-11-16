"""Dala jamoalari (brendlar bo'yicha savdo tuzilmasi): ko'rish, tahrirlash, import/eksport, manbadan yangilash."""
import base64
import binascii
from datetime import datetime

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response

from . import staff_io
from .api import ZonaViewSet, zona_api
from .models import Event, StaffPerson, StaffProject, StaffUnit
from .permissions import CanView, ReadOrEdit
from .views import log


class StaffPersonSerializer(serializers.ModelSerializer):
    unit = serializers.PrimaryKeyRelatedField(queryset=StaffUnit.objects.all(), allow_null=True, required=False)
    manager = serializers.PrimaryKeyRelatedField(queryset=StaffPerson.objects.all(), allow_null=True, required=False)

    class Meta:
        model = StaffPerson
        fields = ["id", "project", "unit", "manager", "name", "role", "position", "territory", "region", "city",
                  "phone", "email", "telegram", "since", "note", "is_vacancy", "history", "order"]
        read_only_fields = ["order", "history"]

    def validate_phone(self, value):
        return staff_io.phone(value)

    def validate_telegram(self, value):
        return staff_io.telegram(value)

    def validate(self, attrs):
        project = attrs.get("project", self.instance.project if self.instance else None)
        for f in ("unit", "manager"):
            obj = attrs.get(f)
            if obj is not None and obj.project_id != project.id:
                raise serializers.ValidationError({f: "Boshqa loyihaga tegishli."})
        manager = attrs.get("manager")
        if manager and self.instance:
            node, seen = manager, set()
            while node and node.pk not in seen:
                if node.pk == self.instance.pk:
                    raise serializers.ValidationError({"manager": "Xodim o'ziga yoki qo'l ostidagiga bo'ysuna olmaydi."})
                seen.add(node.pk)
                node = node.manager
        name = (attrs.get("name", self.instance.name if self.instance else "") or "").strip()
        vacancy = attrs.get("is_vacancy", self.instance.is_vacancy if self.instance else False)
        if not name and not vacancy:
            raise serializers.ValidationError({"name": "F.I.Sh. kiriting yoki o'rinni vakansiya deb belgilang."})
        if vacancy:
            attrs["name"] = ""
        return attrs


class AssignSerializer(serializers.Serializer):
    """Bo'sh o'ringa xodim tayinlash yoki o'rindagi xodimni almashtirish."""
    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    telegram = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    since = serializers.DateField(required=False, allow_null=True, default=None)
    reason = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("F.I.Sh. kiriting.")
        return value.strip()


class VacateSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    date = serializers.DateField(required=False, allow_null=True, default=None)


class StaffUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffUnit
        fields = ["id", "key", "title", "order"]


class StaffProjectSerializer(serializers.ModelSerializer):
    units = StaffUnitSerializer(many=True, read_only=True)

    class Meta:
        model = StaffProject
        fields = ["id", "name", "description", "source_url", "synced_at", "order", "units"]
        read_only_fields = ["synced_at", "order"]


def _projects():
    return StaffProject.objects.prefetch_related("units", "people")


@zona_api(["GET"], [CanView])
def staff(request):
    """Barcha brend jamoalari va xodimlari — bitta so'rovda (sahifa qidiruvni o'zi bajaradi)."""
    projects = list(_projects())
    return Response({
        "projects": StaffProjectSerializer(projects, many=True).data,
        "people": StaffPersonSerializer([p for pr in projects for p in pr.people.all()], many=True).data,
    })


class StaffProjectViewSet(ZonaViewSet):
    queryset = StaffProject.objects.all()
    serializer_class = StaffProjectSerializer

    def perform_create(self, serializer):
        p = serializer.save(order=self.next_order())
        log(self.request, Event.MEMBER, to_name=p.name, text="Yangi brend jamoasi")

    def perform_destroy(self, instance):
        log(self.request, Event.MEMBER, from_name=instance.name,
            text=f"Brend jamoasi o'chirildi ({instance.people.count()} xodim)")
        instance.delete()

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        """Saqlangan manba linkidan qayta o'qish: {"apply": false} — faqat farqlarni ko'rsatadi."""
        project = self.get_object()
        if not project.source_url:
            return Response({"detail": "Bu jamoa uchun manba linki saqlanmagan."}, status=status.HTTP_400_BAD_REQUEST)
        return _run_import(request, {"url": project.source_url, "text": request.data.get("text") or "",
                                     "apply": request.data.get("apply")}, project)


class StaffPersonViewSet(ZonaViewSet):
    queryset = StaffPerson.objects.select_related("project")
    serializer_class = StaffPersonSerializer

    def perform_create(self, serializer):
        p = serializer.save(order=(StaffPerson.objects.filter(project=serializer.validated_data["project"])
                                   .order_by("-order").values_list("order", flat=True).first() or 0) + 1)
        log(self.request, Event.MEMBER, subject=p.project.name, to_name=p.name or f"Vakansiya {p.territory}",
            text=f"Dala jamoasiga qo'shildi: {p.territory}")

    def perform_update(self, serializer):
        inst = serializer.instance
        old = inst.name
        new_name = serializer.validated_data.get("name", old)
        new_vac = serializer.validated_data.get("is_vacancy", inst.is_vacancy)
        if old and (new_vac or new_name.strip() != old.strip()):  # odam ketdi/almashdi — tarixga
            inst.remember_holder("edit")
            if new_vac:
                serializer.validated_data.update(phone="", email="", telegram="", since=None)
            elif "since" not in serializer.validated_data:
                serializer.validated_data["since"] = timezone.localdate()
        elif inst.is_vacancy and not new_vac and not serializer.validated_data.get("since"):
            serializer.validated_data["since"] = timezone.localdate()  # vakansiya to'ldirildi
        p = serializer.save()
        if old != p.name:
            log(self.request, Event.MOVED, subject=f"{p.project.name}: {p.territory}", from_name=old or "Vakansiya",
                to_name=p.name or "Vakansiya", text="Lavozimda xodim almashdi")
        else:
            log(self.request, Event.EDITED, subject=p.project.name, to_name=p.name or p.territory, text="Xodim ma'lumoti yangilandi")

    @action(detail=True, methods=["post"])
    def vacate(self, request, pk=None):
        """Xodim ishdan bo'shadi: o'rin (hudud, rahbar, qo'l ostidagilar) qoladi, vakansiya bo'ladi."""
        p = self.get_object()
        if p.is_vacancy:
            return Response({"detail": "O'rin allaqachon bo'sh."}, status=status.HTTP_400_BAD_REQUEST)
        s = VacateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        old = p.name
        p.remember_holder(s.validated_data["reason"], s.validated_data["date"])
        p.name = p.phone = p.email = p.telegram = ""
        p.since, p.is_vacancy = None, True
        p.save()
        log(request, Event.MOVED, subject=f"{p.project.name}: {p.territory}", from_name=old, to_name="Vakansiya",
            text=f"Ishdan bo'shadi{': ' + s.validated_data['reason'] if s.validated_data['reason'] else ''}")
        return Response(StaffPersonSerializer(p).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """O'ringa xodim tayinlash (vakansiyaga yoki almashtirish — avvalgisi tarixga yoziladi)."""
        p = self.get_object()
        s = AssignSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        old = p.name if not p.is_vacancy else ""
        p.remember_holder(v["reason"] or "almashtirildi")
        p.name, p.phone, p.email = v["name"], staff_io.phone(v["phone"]), v["email"]
        p.telegram, p.since, p.is_vacancy = staff_io.telegram(v["telegram"]), v["since"] or timezone.localdate(), False
        p.save()
        log(request, Event.MOVED, subject=f"{p.project.name}: {p.territory}", from_name=old or "Vakansiya", to_name=p.name,
            text="Lavozimga tayinlandi" if not old else "Lavozimda xodim almashdi")
        return Response(StaffPersonSerializer(p).data)

    def perform_destroy(self, instance):
        StaffPerson.objects.filter(manager=instance).update(manager=instance.manager)  # qo'l ostidagilar yuqoriga
        log(self.request, Event.MEMBER, subject=instance.project.name, from_name=instance.name or instance.territory,
            text="Dala jamoasidan o'chirildi")
        instance.delete()


def _load(data):
    """So'rov tanasidan manbani o'qish: url | text | file_b64 (+filename)."""
    if data.get("text") and data.get("url"):
        # brauzerda ochilib nusxa olingan sahifa matni (Claude artifact kabi) — link manba sifatida saqlanadi
        return str(data["text"]), "", str(data["url"]).strip()
    if data.get("url"):
        content, fname = staff_io.fetch(str(data["url"]))
        return content, fname or str(data.get("filename") or ""), str(data["url"]).strip()
    if data.get("file_b64"):
        try:
            content = base64.b64decode(str(data["file_b64"]), validate=False)
        except (binascii.Error, ValueError):
            raise staff_io.StaffImportError("Fayl o'qilmadi.") from None
        if len(content) > staff_io.MAX_BYTES:
            raise staff_io.StaffImportError("Fayl juda katta (5 MB dan oshiq).")
        return content, str(data.get("filename") or ""), ""
    if data.get("text"):
        return str(data["text"]), "", ""
    raise staff_io.StaffImportError("Link, fayl yoki matn kiriting.")


def _run_import(request, data, project=None):
    try:
        content, fname, url = _load(data)
        docs = staff_io.parse(content, fname, name=str(data.get("name") or (project.name if project else "")).strip(),
                              source_url=url)
    except staff_io.StaffImportError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    if project is None and data.get("project"):
        project = StaffProject.objects.filter(pk=data.get("project")).first()
    if project is None and url and len(docs) == 1:
        # shu link qaysi jamoaning manbasi bo'lsa — o'sha jamoa yangilanadi (nomi matnda boshqacha bo'lsa ham)
        base = url.split("#")[0].rstrip("/")
        project = next((p for p in StaffProject.objects.exclude(source_url="")
                        if p.source_url.split("#")[0].rstrip("/") == base), None)
    if project is not None:
        if len(docs) > 1:
            names = ", ".join(docs)
            return Response({"detail": f"Faylda bir nechta jamoa bor ({names}): \"Yangi / avtomatik\" ni tanlang."},
                            status=status.HTTP_400_BAD_REQUEST)
        doc = next(iter(docs.values()))
        doc["project"]["name"] = project.name
        if url:
            doc["project"]["source_url"] = url
        docs = {project.name: doc}
    targets = {name: project or StaffProject.objects.filter(name__iexact=name).first() for name in docs}
    if not data.get("apply"):
        return Response({"projects": [staff_io.diff(targets[n], d) for n, d in docs.items()]})
    out = []
    for name, doc in docs.items():
        obj, result = staff_io.apply(doc, targets[name])
        s = result["summary"]
        log(request, Event.MEMBER, subject=obj.name,
            text=f"Tuzilma import qilindi: {s['total']} o'rin, +{s['added']} −{s['removed']}, almashdi {s['replaced']}, o'zgardi {s['changed']}")
        out.append(result)
    return Response({"projects": out, "applied": True})


@zona_api(["POST"], [ReadOrEdit])
def staff_import(request):
    """{"url"|"text"|"file_b64"+"filename", "name"?, "project"?: id, "apply": false}

    apply=false — faqat farqlar (nima qo'shiladi, o'chiriladi, kim almashdi); apply=true — bazaga yoziladi.
    """
    return _run_import(request, request.data)


@zona_api(["GET"], [CanView])
def staff_export(request, fmt):
    ids = request.query_params.get("project")
    projects = _projects()
    if ids:
        projects = projects.filter(pk__in=[int(i) for i in ids.split(",") if i.isdigit()])
    projects = list(projects)
    stamp = datetime.now(timezone.get_current_timezone()).strftime("%Y-%m-%d")
    base = projects[0].name if len(projects) == 1 else "stargroup"
    base = "".join(c if c.isalnum() else "_" for c in base).strip("_") or "jamoa"
    if fmt == "xlsx":
        resp = HttpResponse(staff_io.export_xlsx(projects),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = f'attachment; filename="tuzilma_{base}_{stamp}.xlsx"'
        return resp
    resp = Response(staff_io.export_json(projects))
    resp["Content-Disposition"] = f'attachment; filename="tuzilma_{base}_{stamp}.json"'
    return resp
