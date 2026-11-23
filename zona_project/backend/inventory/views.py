"""IT inventarizatsiya API (/api/inventory/...). Har bir javob filial doirasi bilan cheklanadi (access.scoped)."""
import secrets
import string
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import (api_view, authentication_classes, parser_classes, permission_classes,
                                       renderer_classes)
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from zona.auth import AUTHENTICATION

from . import photos as photo_store
from .access import (COLLECTOR, DIRECTOR, MANAGER, CanWrite, HasInventory, IsManager, IsManagerOrDirector,
                     access_of, branch_scope, can_write_branch, level_of, scoped)
from .models import Access, Branch, DeviceType, Employee, Item, Location, Log, Org, Photo

User = get_user_model()
COND_LABEL = dict(Item.CONDITIONS)
STATUS_LABEL = dict(Branch.STATUSES)


def inv_api(methods, permissions, multipart=False):
    def wrap(fn):
        fn = authentication_classes(AUTHENTICATION)(fn)
        fn = permission_classes(permissions)(fn)
        fn = renderer_classes([JSONRenderer])(fn)
        fn = parser_classes([JSONParser, MultiPartParser, FormParser] if multipart else [JSONParser])(fn)
        return api_view(methods)(fn)
    return wrap


def bad(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": message}, status=code)


def _s(value, limit=255):
    return str(value if value is not None else "").strip()[:limit]


def _int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def user_name(user):
    if not user:
        return ""
    return user.get_full_name() or user.username


def log(request, action, *, branch=None, item=None, entity="item", summary="", changes=None):
    Log.objects.create(user=request.user if request.user.is_authenticated else None, branch=branch, item=item,
                       entity=entity, action=action, summary=summary[:300], changes=changes or {})


# ====================================================================== bootstrap
def me_payload(user):
    level = level_of(user)
    scope = branch_scope(user)
    from zona.permissions import role_of
    return {"id": user.id, "username": user.username, "name": user_name(user), "level": level,
            "branches": sorted(scope) if scope is not None else None,
            "restricted": role_of(user) == "inventory",
            "can": {"write": level in (MANAGER, COLLECTOR), "manage": level == MANAGER,
                    "analytics": level in (MANAGER, DIRECTOR, COLLECTOR)}}


def branch_payload(b):
    return {"id": b.id, "code": b.code, "name": b.name, "region": b.region, "note": b.note, "status": b.status,
            "status_label": STATUS_LABEL.get(b.status, b.status), "conductor": b.conductor,
            "started_at": b.started_at, "finished_at": b.finished_at, "order": b.order}


def type_payload(d):
    return {"id": d.id, "name": d.name, "group": d.group, "description": d.description, "serial_hint": d.serial_hint,
            "extra_hint": d.extra_hint, "brands": d.brands or [], "is_active": d.is_active, "order": d.order}


@inv_api(["GET"], [HasInventory])
def bootstrap(request):
    """Ilova ochilganda bitta so'rov: foydalanuvchi, katalog va ko'rinadigan filiallar."""
    branches = scoped(Branch.objects.all(), request.user, "id")
    return Response({
        "me": me_payload(request.user),
        "orgs": [{"id": o.id, "name": o.name, "code": o.code} for o in Org.objects.all()],
        "branches": [branch_payload(b) for b in branches],
        "locations": [{"id": x.id, "name": x.name} for x in Location.objects.all()],
        "device_types": [type_payload(d) for d in DeviceType.objects.all()],
        "conditions": [{"value": v, "label": l} for v, l in Item.CONDITIONS],
        "branch_statuses": [{"value": v, "label": l} for v, l in Branch.STATUSES],
        "levels": [{"value": v, "label": l} for v, l in Access.LEVELS],
    })


# ====================================================================== qurilmalar
def item_payload(it, full=False):
    data = {
        "id": it.id, "inv_number": it.inv_number, "org": it.org_id, "org_name": it.org.name if it.org_id else "",
        "branch": it.branch_id, "branch_name": it.branch.name, "location": it.location,
        "device_type": it.device_type_id, "device_type_name": it.device_type.name, "group": it.device_type.group,
        "brand": it.brand, "model": it.model, "serial": it.serial, "quantity": it.quantity,
        "condition": it.condition, "condition_label": COND_LABEL.get(it.condition, it.condition),
        "employee": it.employee_id, "employee_name": it.employee.full_name if it.employee_id else "",
        "employee_position": it.employee.position if it.employee_id else "",
        "employee_phone": it.employee.phone if it.employee_id else "",
        "note": it.note, "is_deleted": it.is_deleted,
        "created_by": user_name(it.created_by), "updated_by": user_name(it.updated_by),
        "created_at": it.created_at, "updated_at": it.updated_at,
        "photos": [photo_store.payload(p) for p in it.photos.all()],
    }
    if full:
        data["history"] = [log_payload(x) for x in it.logs.select_related("user", "branch")[:30]]
    return data


ITEM_FIELDS = ("org", "branch", "location", "device_type", "brand", "model", "serial", "quantity", "condition",
               "employee", "note")


def item_qs():
    return Item.objects.select_related("org", "branch", "device_type", "employee", "created_by", "updated_by") \
        .prefetch_related("photos")


def filter_items(request, qs):
    p = request.query_params
    if p.get("deleted") == "1":
        qs = qs.filter(is_deleted=True)
    elif p.get("deleted") != "all":
        qs = qs.filter(is_deleted=False)
    for key, field in (("branch", "branch_id"), ("org", "org_id"), ("type", "device_type_id"),
                       ("employee", "employee_id")):
        ids = [i for i in (_int(x) for x in p.get(key, "").split(",")) if i]
        if ids:
            qs = qs.filter(**{f"{field}__in": ids})
    if p.get("condition"):
        qs = qs.filter(condition__in=p["condition"].split(","))
    if p.get("group"):
        qs = qs.filter(device_type__group=p["group"])
    if p.get("location"):
        qs = qs.filter(location=p["location"])
    if p.get("user"):
        qs = qs.filter(created_by_id=_int(p["user"]))
    if p.get("mine") == "1":
        qs = qs.filter(created_by=request.user)
    if p.get("no_serial") == "1":
        qs = qs.filter(serial="")
    if p.get("no_employee") == "1":
        qs = qs.filter(employee__isnull=True)
    if p.get("no_photo") == "1":
        qs = qs.annotate(_pc=Count("photos")).filter(_pc=0)
    if p.get("q"):
        q = p["q"].strip()
        qs = qs.filter(Q(inv_number__icontains=q) | Q(serial__icontains=q) | Q(model__icontains=q)
                       | Q(brand__icontains=q) | Q(device_type__name__icontains=q) | Q(employee__full_name__icontains=q)
                       | Q(note__icontains=q) | Q(location__icontains=q))
    return qs


def clean_item(request, data, instance=None):
    """Kiruvchi ma'lumotni tekshiradi: (maydonlar, xato matni)."""
    out = {}
    if "branch" in data or instance is None:
        branch = Branch.objects.filter(pk=_int(data.get("branch"))).first()
        if not branch:
            return None, "Filialni tanlang."
        if not can_write_branch(request.user, branch.id):
            return None, "Bu filialga yozish huquqingiz yo'q."
        out["branch"] = branch
    if "device_type" in data or instance is None:
        dt = DeviceType.objects.filter(pk=_int(data.get("device_type"))).first()
        if not dt:
            return None, "Qurilma turini tanlang."
        out["device_type"] = dt
    if "org" in data:
        out["org"] = Org.objects.filter(pk=_int(data.get("org"))).first()
    if "employee" in data:
        emp = Employee.objects.filter(pk=_int(data.get("employee"))).first() if data.get("employee") else None
        out["employee"] = emp
    if "condition" in data:
        cond = _s(data.get("condition"), 10) or Item.OK
        if cond not in COND_LABEL:
            return None, "Holat noto'g'ri."
        out["condition"] = cond
    if "quantity" in data:
        qty = _int(data.get("quantity"), 1) or 1
        if qty < 1 or qty > 100000:
            return None, "Soni 1 dan katta butun son bo'lsin."
        out["quantity"] = qty
    for f, limit in (("location", 120), ("brand", 80), ("model", 150), ("serial", 120)):
        if f in data:
            out[f] = _s(data.get(f), limit)
    if "note" in data:
        out["note"] = _s(data.get("note"), 2000)
    return out, None


def _display(field, value):
    if value is None:
        return ""
    if field == "condition":
        return COND_LABEL.get(value, value)
    if hasattr(value, "pk"):
        return str(value)
    return value


def duplicate_serial(serial, exclude_id=None):
    if not serial or len(serial) < 3:
        return None
    qs = Item.objects.filter(serial__iexact=serial, is_deleted=False).select_related("branch")
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    dup = qs.first()
    return {"id": dup.id, "inv_number": dup.inv_number, "branch": dup.branch.name} if dup else None


def next_inv_number(branch_id):
    """Filial bo'yicha ketma-ket raqam: SAM-00001. Tranzaksiya ichida chaqiriladi."""
    b = Branch.objects.select_for_update().get(pk=branch_id)
    while True:
        b.seq += 1
        number = f"{b.code}-{b.seq:05d}"
        if not Item.objects.filter(inv_number=number).exists():
            break
    Branch.objects.filter(pk=b.pk).update(seq=b.seq)
    return number


def attach_photos(request, item, ids):
    if ids is None:
        return
    ids = [i for i in (_int(x) for x in ids) if i]
    keep = Photo.objects.filter(pk__in=ids).filter(Q(item__isnull=True) | Q(item=item))
    keep.update(item=item)
    for p in item.photos.exclude(pk__in=ids):
        photo_store.remove_files(p)
        p.delete()


def mark_branch_active(branch, request):
    if branch.status == Branch.PLANNED:
        branch.status = Branch.ACTIVE
        branch.started_at = branch.started_at or timezone.localdate()
        if not branch.conductor and request.user.is_authenticated:
            branch.conductor = user_name(request.user)
        branch.save(update_fields=["status", "started_at", "conductor"])
        log(request, Log.STATUS, branch=branch, entity="branch", summary=f"{branch.name}: Jarayonda (birinchi qurilma)")


@inv_api(["GET", "POST"], [CanWrite])
def items(request):
    if request.method == "POST":
        fields, err = clean_item(request, request.data)
        if err:
            return bad(err)
        with transaction.atomic():
            item = Item(**fields, created_by=request.user, updated_by=request.user)
            item.inv_number = next_inv_number(fields["branch"].id)
            item.save()
            attach_photos(request, item, request.data.get("photos"))
        mark_branch_active(item.branch, request)
        log(request, Log.CREATE, branch=item.branch, item=item,
            summary=f"{item.inv_number} · {item.device_type.name} {item.brand} {item.model}".strip())
        item = item_qs().get(pk=item.pk)
        return Response({**item_payload(item), "duplicate": duplicate_serial(item.serial, item.id)},
                        status=status.HTTP_201_CREATED)

    qs = filter_items(request, scoped(item_qs(), request.user))
    order = request.query_params.get("ordering") or "-updated_at"
    if order.lstrip("-") in ("updated_at", "created_at", "inv_number", "serial", "quantity"):
        qs = qs.order_by(order, "-id")
    total = qs.count()
    page_size = min(_int(request.query_params.get("page_size"), 30) or 30, 200)
    page = max(_int(request.query_params.get("page"), 1) or 1, 1)
    rows = qs[(page - 1) * page_size: page * page_size]
    qty = qs.aggregate(s=Sum("quantity"))["s"] or 0
    return Response({"count": total, "quantity": qty, "page": page, "page_size": page_size,
                     "results": [item_payload(x) for x in rows]})


@inv_api(["GET", "PATCH", "DELETE"], [CanWrite])
def item_detail(request, pk):
    item = scoped(item_qs(), request.user).filter(pk=pk).first()
    if not item:
        raise Http404
    if request.method == "GET":
        return Response(item_payload(item, full=True))
    if not can_write_branch(request.user, item.branch_id):
        return bad("Bu filialga yozish huquqingiz yo'q.", status.HTTP_403_FORBIDDEN)
    if request.method == "DELETE":
        item.is_deleted, item.deleted_at, item.deleted_by = True, timezone.now(), request.user
        item.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])
        log(request, Log.DELETE, branch=item.branch, item=item, summary=f"{item.inv_number} · {item.device_type.name}")
        return Response(status=status.HTTP_204_NO_CONTENT)

    fields, err = clean_item(request, request.data, instance=item)
    if err:
        return bad(err)
    changes = {}
    for f, v in fields.items():
        old = getattr(item, f)
        if (old.pk if hasattr(old, "pk") else old) != (v.pk if hasattr(v, "pk") else v):
            changes[f] = [_display(f, old), _display(f, v)]
            setattr(item, f, v)
    before = set(item.photos.values_list("pk", flat=True))
    with transaction.atomic():
        item.updated_by = request.user
        item.save()
        attach_photos(request, item, request.data.get("photos"))
    after = set(item.photos.values_list("pk", flat=True))
    if before != after:
        changes["photos"] = [len(before), len(after)]
    if changes:
        log(request, Log.UPDATE, branch=item.branch, item=item, changes=changes,
            summary=f"{item.inv_number} · {', '.join(changes)}")
    item = item_qs().get(pk=item.pk)
    return Response({**item_payload(item), "duplicate": duplicate_serial(item.serial, item.id)})


@inv_api(["POST"], [CanWrite])
def item_restore(request, pk):
    item = scoped(item_qs(), request.user).filter(pk=pk, is_deleted=True).first()
    if not item:
        raise Http404
    if not can_write_branch(request.user, item.branch_id):
        return bad("Bu filialga yozish huquqingiz yo'q.", status.HTTP_403_FORBIDDEN)
    item.is_deleted, item.deleted_at, item.deleted_by = False, None, None
    item.updated_by = request.user
    item.save()
    log(request, Log.RESTORE, branch=item.branch, item=item, summary=f"{item.inv_number} · {item.device_type.name}")
    return Response(item_payload(item))


@inv_api(["GET"], [HasInventory])
def check_serial(request):
    return Response({"duplicate": duplicate_serial(_s(request.query_params.get("serial"), 120),
                                                   _int(request.query_params.get("exclude")))})


# ====================================================================== rasmlar
@inv_api(["POST"], [CanWrite], multipart=True)
def photo_upload(request):
    files = request.FILES.getlist("files") or request.FILES.getlist("file")
    if not files:
        return bad("Rasm tanlanmagan.")
    out = []
    for f in files[:12]:
        if f.size > photo_store.MAX_BYTES:
            return bad(f"{f.name}: rasm juda katta (≤15 MB).")
        try:
            out.append(photo_store.payload(photo_store.store(f.read(), request.user)))
        except ValueError as e:
            return bad(f"{f.name}: {e}")
    return Response(out, status=status.HTTP_201_CREATED)


@inv_api(["DELETE"], [CanWrite])
def photo_delete(request, pk):
    photo = Photo.objects.filter(pk=pk).select_related("item").first()
    if not photo:
        raise Http404
    if photo.item_id and not can_write_branch(request.user, photo.item.branch_id):
        return bad("Ruxsat yo'q.", status.HTTP_403_FORBIDDEN)
    if not photo.item_id and photo.uploaded_by_id != request.user.id and level_of(request.user) != MANAGER:
        return bad("Ruxsat yo'q.", status.HTTP_403_FORBIDDEN)
    photo_store.remove_files(photo)
    photo.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def photo_file(request, pk):
    """Imzolangan havola: /photos/<id>/file/?k=<imzo>[&t=1]. Brauzer keshlaydi (rasm o'zgarmaydi)."""
    if not photo_store.check(pk, request.query_params.get("k")):
        raise Http404
    photo = Photo.objects.filter(pk=pk).first()
    if not photo:
        raise Http404
    path = photo.thumb if request.query_params.get("t") and photo.thumb else photo.path
    try:
        fh = open(path, "rb")
    except OSError as e:
        raise Http404 from e
    resp = FileResponse(fh, content_type="image/jpeg")
    resp["Cache-Control"] = "private, max-age=31536000, immutable"
    return resp


# ====================================================================== xodimlar
def employee_payload(e, devices=None):
    return {"id": e.id, "full_name": e.full_name, "position": e.position, "phone": e.phone, "org": e.org_id,
            "org_name": e.org.name if e.org_id else "", "branch": e.branch_id,
            "branch_name": e.branch.name if e.branch_id else "", "project": e.project, "department": e.department,
            "note": e.note, "is_active": e.is_active, "source": e.source,
            "devices": devices if devices is not None else getattr(e, "devices", 0)}


def employee_scope(request):
    qs = Employee.objects.select_related("org", "branch")
    ids = branch_scope(request.user)
    return qs if ids is None else qs.filter(branch_id__in=ids)


def clean_employee(request, data, instance=None):
    out = {}
    if "full_name" in data or instance is None:
        name = _s(data.get("full_name"), 150)
        if len(name) < 3:
            return None, "F.I.Sh. ni yozing."
        out["full_name"] = name
    if "branch" in data or instance is None:
        branch = Branch.objects.filter(pk=_int(data.get("branch"))).first() if data.get("branch") else None
        if level_of(request.user) != MANAGER:
            if not branch or not can_write_branch(request.user, branch.id):
                return None, "Filialni tanlang (faqat o'z filialingiz)."
        out["branch"] = branch
    if "org" in data:
        out["org"] = Org.objects.filter(pk=_int(data.get("org"))).first() if data.get("org") else None
    for f, limit in (("position", 120), ("phone", 40), ("project", 120), ("department", 120), ("note", 255)):
        if f in data:
            out[f] = _s(data.get(f), limit)
    if "is_active" in data:
        out["is_active"] = bool(data.get("is_active"))
    return out, None


@inv_api(["GET", "POST"], [CanWrite])
def employees(request):
    if request.method == "POST":
        fields, err = clean_employee(request, request.data)
        if err:
            return bad(err)
        dup = Employee.objects.filter(full_name__iexact=fields["full_name"], branch=fields.get("branch")).first()
        if dup:
            return Response(employee_payload(dup, 0), status=status.HTTP_200_OK)
        emp = Employee.objects.create(**fields, created_by=request.user, source=Employee.MANUAL)
        log(request, Log.CREATE, branch=emp.branch, entity="employee", summary=f"Xodim: {emp.full_name}")
        return Response(employee_payload(emp, 0), status=status.HTTP_201_CREATED)

    p = request.query_params
    qs = employee_scope(request).annotate(devices=Count("items", filter=Q(items__is_deleted=False)))
    if p.get("active", "1") == "1":
        qs = qs.filter(is_active=True)
    for key, field in (("branch", "branch_id"), ("org", "org_id")):
        ids = [i for i in (_int(x) for x in p.get(key, "").split(",")) if i]
        if ids:
            qs = qs.filter(**{f"{field}__in": ids})
    if p.get("no_branch") == "1":
        qs = qs.filter(branch__isnull=True)
    if p.get("project"):
        qs = qs.filter(project=p["project"])
    if p.get("department"):
        qs = qs.filter(department=p["department"])
    if p.get("devices") == "0":
        qs = qs.filter(devices=0)
    elif p.get("devices") == "1":
        qs = qs.filter(devices__gt=0)
    if p.get("q"):
        q = p["q"].strip()
        qs = qs.filter(Q(full_name__icontains=q) | Q(phone__icontains=q) | Q(position__icontains=q)
                       | Q(project__icontains=q))
    total = qs.count()
    limit = min(_int(p.get("limit"), 3000) or 3000, 5000)
    offset = max(_int(p.get("offset"), 0) or 0, 0)
    facets = employee_scope(request).filter(is_active=True)
    return Response({
        "count": total,
        "results": [employee_payload(e) for e in qs[offset: offset + limit]],
        "projects": sorted(x for x in facets.values_list("project", flat=True).distinct() if x),
        "departments": sorted(x for x in facets.values_list("department", flat=True).distinct() if x),
    })


@inv_api(["PATCH", "DELETE"], [CanWrite])
def employee_detail(request, pk):
    emp = employee_scope(request).filter(pk=pk).first()
    if not emp:
        raise Http404
    if level_of(request.user) != MANAGER and not can_write_branch(request.user, emp.branch_id):
        return bad("Bu xodimni o'zgartirish huquqingiz yo'q.", status.HTTP_403_FORBIDDEN)
    if request.method == "DELETE":
        used = emp.items.filter(is_deleted=False).count()
        if used:
            emp.is_active = False
            emp.save(update_fields=["is_active", "updated_at"])
            log(request, Log.DELETE, branch=emp.branch, entity="employee",
                summary=f"Xodim nofaol qilindi: {emp.full_name} ({used} ta qurilma biriktirilgan)")
            return Response({"deactivated": True, "devices": used})
        log(request, Log.DELETE, branch=emp.branch, entity="employee", summary=f"Xodim o'chirildi: {emp.full_name}")
        emp.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    fields, err = clean_employee(request, request.data, instance=emp)
    if err:
        return bad(err)
    changes = {}
    for f, v in fields.items():
        old = getattr(emp, f)
        if (old.pk if hasattr(old, "pk") else old) != (v.pk if hasattr(v, "pk") else v):
            changes[f] = [_display(f, old), _display(f, v)]
            setattr(emp, f, v)
    emp.save()
    if changes:
        log(request, Log.UPDATE, branch=emp.branch, entity="employee", changes=changes,
            summary=f"Xodim: {emp.full_name} · {', '.join(changes)}")
    return Response(employee_payload(emp, emp.items.filter(is_deleted=False).count()))


# ====================================================================== filiallar
@inv_api(["GET", "POST"], [CanWrite])
def branches(request):
    if request.method == "POST":
        if level_of(request.user) != MANAGER:
            return bad("Faqat boshqaruvchi filial qo'sha oladi.", status.HTTP_403_FORBIDDEN)
        code, name = _s(request.data.get("code"), 12).upper(), _s(request.data.get("name"), 120)
        if not code or not name:
            return bad("Kod va nomni yozing.")
        if Branch.objects.filter(Q(code__iexact=code) | Q(name__iexact=name)).exists():
            return bad("Bunday kod yoki nomli filial bor.")
        b = Branch.objects.create(code=code, name=name, region=_s(request.data.get("region"), 120),
                                  note=_s(request.data.get("note")), order=Branch.objects.count())
        log(request, Log.CREATE, branch=b, entity="branch", summary=f"Filial qo'shildi: {b.name}")
        return Response(branch_payload(b), status=status.HTTP_201_CREATED)
    return Response([branch_payload(b) for b in scoped(Branch.objects.all(), request.user, "id")])


@inv_api(["PATCH", "DELETE"], [CanWrite])
def branch_detail(request, pk):
    b = scoped(Branch.objects.all(), request.user, "id").filter(pk=pk).first()
    if not b:
        raise Http404
    manager = level_of(request.user) == MANAGER
    if not can_write_branch(request.user, b.id):
        return bad("Ruxsat yo'q.", status.HTTP_403_FORBIDDEN)
    if request.method == "DELETE":
        if not manager:
            return bad("Ruxsat yo'q.", status.HTTP_403_FORBIDDEN)
        if b.items.exists():
            return bad("Filialda qurilmalar bor — avval ularni o'chiring yoki boshqa filialga o'tkazing.")
        log(request, Log.DELETE, entity="branch", summary=f"Filial o'chirildi: {b.name}")
        b.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    data = request.data
    allowed = ("status", "conductor") if not manager else ("status", "conductor", "code", "name", "region", "note",
                                                          "started_at", "finished_at", "order")
    changes = {}
    for f in allowed:
        if f not in data:
            continue
        v = data.get(f)
        if f == "status":
            if v not in STATUS_LABEL:
                return bad("Holat noto'g'ri.")
            if v == Branch.DONE:
                b.finished_at = timezone.localdate()
            elif b.status == Branch.DONE:
                b.finished_at = None
            if v != Branch.PLANNED and not b.started_at:
                b.started_at = timezone.localdate()
        elif f in ("started_at", "finished_at"):
            v = v or None
        elif f == "order":
            v = _int(v, 0)
        else:
            v = _s(v, 120 if f != "note" else 255)
            if f == "code":
                v = v.upper()
            if f in ("code", "name") and not v:
                return bad("Kod va nom bo'sh bo'lmasin.")
        old = getattr(b, f)
        if str(old or "") != str(v or ""):
            changes[f] = [STATUS_LABEL.get(old, old) if f == "status" else str(old or ""),
                          STATUS_LABEL.get(v, v) if f == "status" else str(v or "")]
            setattr(b, f, v)
    b.save()
    if changes:
        log(request, Log.STATUS if "status" in changes else Log.UPDATE, branch=b, entity="branch", changes=changes,
            summary=f"{b.name}: " + (f"holat → {STATUS_LABEL[b.status]}" if "status" in changes else ", ".join(changes)))
    return Response(branch_payload(b))


# ====================================================================== katalog (boshqaruvchi)
@inv_api(["POST"], [IsManager])
def catalog_save(request):
    """{kind: org|location|device_type, id?, ...maydonlar, delete?: true}."""
    kind, data = request.data.get("kind"), request.data
    pk = _int(data.get("id"))
    if kind == "org":
        model, fields = Org, {"name": _s(data.get("name"), 120), "code": _s(data.get("code"), 60)}
    elif kind == "location":
        model, fields = Location, {"name": _s(data.get("name"), 120)}
    elif kind == "device_type":
        brands = data.get("brands") or []
        if isinstance(brands, str):
            brands = [b.strip() for b in brands.split(",")]
        model, fields = DeviceType, {
            "name": _s(data.get("name"), 120), "group": _s(data.get("group"), 60),
            "description": _s(data.get("description")), "serial_hint": _s(data.get("serial_hint")),
            "extra_hint": _s(data.get("extra_hint")), "brands": [_s(b, 80) for b in brands if _s(b, 80)][:30],
            "is_active": bool(data.get("is_active", True))}
    else:
        return bad("Noma'lum katalog turi.")
    obj = model.objects.filter(pk=pk).first() if pk else None
    if data.get("delete"):
        if not obj:
            raise Http404
        used = (obj.items.exists() or obj.employees.exists()) if kind == "org" else \
            obj.items.exists() if kind == "device_type" else False
        if used and kind == "device_type":
            obj.is_active = False
            obj.save(update_fields=["is_active"])
            return Response({"deactivated": True})
        if used:
            return bad("Bu qiymat ishlatilmoqda — o'chirib bo'lmaydi.")
        obj.delete()
        log(request, Log.DELETE, entity="catalog", summary=f"Katalog: {kind} {fields.get('name') or ''}")
        return Response(status=status.HTTP_204_NO_CONTENT)
    if not fields["name"]:
        return bad("Nomini yozing.")
    clash = model.objects.filter(name__iexact=fields["name"])
    if obj:
        clash = clash.exclude(pk=obj.pk)
    if clash.exists():
        return bad("Bunday nom bor.")
    if obj:
        for f, v in fields.items():
            setattr(obj, f, v)
        obj.save()
    else:
        obj = model.objects.create(**fields, order=model.objects.count())
    log(request, Log.UPDATE if pk else Log.CREATE, entity="catalog", summary=f"Katalog: {kind} {obj.name}")
    if kind == "device_type":
        return Response(type_payload(obj))
    return Response({"id": obj.id, "name": obj.name, **({"code": obj.code} if kind == "org" else {})})


# ====================================================================== foydalanuvchilar (boshqaruvchi)
def gen_password(n=8):
    """Telefonda oson yoziladigan parol: chalkash belgilar (0/O, 1/l/I) yo'q."""
    alphabet = "".join(c for c in string.ascii_lowercase + string.digits if c not in "0o1li")
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(n))
        if any(c.isdigit() for c in pw) and any(c.isalpha() for c in pw):
            return pw


def access_payload(acc):
    from zona.crypto import decrypt
    u = acc.user
    initial = decrypt(acc.password_enc) if acc.password_enc else ""
    return {"id": acc.id, "user_id": u.id, "username": u.username, "name": user_name(u),
            "first_name": u.first_name, "last_name": u.last_name, "level": acc.level,
            "level_label": dict(Access.LEVELS).get(acc.level, acc.level), "is_active": u.is_active,
            "branches": [b.id for b in acc.branches.all()], "branch_names": [b.name for b in acc.branches.all()],
            "note": acc.note, "has_password": bool(initial), "last_login": u.last_login,
            "created_at": acc.created_at,
            "items": Item.objects.filter(created_by=u, is_deleted=False).count()}


def _restricted_profile(user):
    """Faqat inventarizatsiya foydalanuvchisi: Zona'dagi boshqa sahifalarga kira olmaydi."""
    from zona.models import Profile
    profile, _ = Profile.objects.get_or_create(user=user, defaults={"role": "inventory"})
    if profile.role != "inventory":
        profile.role = "inventory"
        profile.save(update_fields=["role"])


def create_access_user(username, first_name="", last_name="", level=COLLECTOR, branch_ids=(), note="", password=None):
    from zona.crypto import encrypt
    password = password or gen_password()
    user = User.objects.create_user(username=username, password=password, first_name=first_name[:150],
                                    last_name=last_name[:150])
    _restricted_profile(user)
    acc = Access.objects.create(user=user, level=level, note=note, password_enc=encrypt(password))
    if branch_ids:
        acc.branches.set(Branch.objects.filter(pk__in=branch_ids))
    return acc, password


@inv_api(["GET", "POST"], [IsManager])
def users(request):
    if request.method == "POST":
        data = request.data
        level = data.get("level") or COLLECTOR
        if level not in dict(Access.LEVELS):
            return bad("Daraja noto'g'ri.")
        existing = _s(data.get("existing_username"), 150)
        if existing:  # mavjud Zona foydalanuvchisiga modul huquqini berish (roli o'zgarmaydi)
            user = User.objects.filter(username__iexact=existing).first()
            if not user:
                return bad("Bunday foydalanuvchi topilmadi.")
            acc, _ = Access.objects.get_or_create(user=user, defaults={"level": level})
            acc.level = level
            acc.save(update_fields=["level"])
            acc.branches.set(Branch.objects.filter(pk__in=[_int(x) for x in data.get("branches") or []]))
            log(request, Log.CREATE, entity="user", summary=f"Huquq berildi: {user.username} ({level})")
            return Response(access_payload(acc), status=status.HTTP_201_CREATED)
        username = _s(data.get("username"), 150).lower().replace(" ", ".")
        if len(username) < 3:
            return bad("Login kamida 3 belgi bo'lsin.")
        if User.objects.filter(username__iexact=username).exists():
            return bad("Bunday login bor.")
        acc, password = create_access_user(username, _s(data.get("first_name"), 150), _s(data.get("last_name"), 150),
                                           level, [_int(x) for x in data.get("branches") or []],
                                           _s(data.get("note")), _s(data.get("password"), 64) or None)
        log(request, Log.CREATE, entity="user", summary=f"Foydalanuvchi yaratildi: {username} ({level})")
        return Response({**access_payload(acc), "password": password}, status=status.HTTP_201_CREATED)
    rows = Access.objects.select_related("user").prefetch_related("branches").order_by("level", "user__username")
    return Response([access_payload(a) for a in rows])


@inv_api(["PATCH", "DELETE"], [IsManager])
def user_detail(request, pk):
    acc = Access.objects.select_related("user").filter(pk=pk).first()
    if not acc:
        raise Http404
    u = acc.user
    if request.method == "DELETE":
        from zona.permissions import role_of
        restricted = role_of(u) == "inventory"
        log(request, Log.DELETE, entity="user", summary=f"Huquq olindi: {u.username}")
        acc.delete()
        if restricted:  # faqat modul uchun yaratilgan login — o'chirilmaydi (tarix saqlanadi), faqat bloklanadi
            u.is_active = False
            u.save(update_fields=["is_active"])
            from zona.auth import revoke_all
            revoke_all(u)
        return Response(status=status.HTTP_204_NO_CONTENT)
    data = request.data
    if "level" in data:
        if data["level"] not in dict(Access.LEVELS):
            return bad("Daraja noto'g'ri.")
        acc.level = data["level"]
    if "note" in data:
        acc.note = _s(data.get("note"))
    acc.save()
    if "branches" in data:
        acc.branches.set(Branch.objects.filter(pk__in=[_int(x) for x in data.get("branches") or []]))
    for f in ("first_name", "last_name"):
        if f in data:
            setattr(u, f, _s(data.get(f), 150))
    if "is_active" in data:
        u.is_active = bool(data.get("is_active"))
        if not u.is_active:
            from zona.auth import revoke_all
            revoke_all(u)
    u.save()
    log(request, Log.UPDATE, entity="user", summary=f"Foydalanuvchi o'zgartirildi: {u.username}")
    return Response(access_payload(acc))


@inv_api(["POST"], [IsManager])
def user_reset_password(request, pk):
    from zona.auth import revoke_all
    from zona.crypto import encrypt
    acc = Access.objects.select_related("user").filter(pk=pk).first()
    if not acc:
        raise Http404
    password = _s(request.data.get("password"), 64) or gen_password()
    acc.user.set_password(password)
    acc.user.save(update_fields=["password"])
    acc.password_enc = encrypt(password)
    acc.save(update_fields=["password_enc"])
    revoke_all(acc.user)
    log(request, Log.UPDATE, entity="user", summary=f"Parol yangilandi: {acc.user.username}")
    return Response({"password": password, "username": acc.user.username})


def branch_login(branch):
    base = "inv." + "".join(c for c in branch.code.lower() if c.isalnum())
    return base


@inv_api(["POST"], [IsManager])
def users_generate(request):
    """Har bir filial uchun (login hali yo'q bo'lsa) bitta filial xodimi logini: inv.sam, inv.and..."""
    created = []
    ids = [_int(x) for x in request.data.get("branches") or []]
    qs = Branch.objects.all() if not ids else Branch.objects.filter(pk__in=ids)
    for b in qs:
        if Access.objects.filter(level=COLLECTOR, branches=b).exists() and not request.data.get("extra"):
            continue
        base, n = branch_login(b), 1
        username = base
        while User.objects.filter(username__iexact=username).exists():
            n += 1
            username = f"{base}{n}"
        acc, password = create_access_user(username, first_name=b.name, last_name="filiali", level=COLLECTOR,
                                           branch_ids=[b.id], note=f"{b.name} filiali uchun")
        created.append({"username": username, "password": password, "branch": b.name})
    if created:
        log(request, Log.CREATE, entity="user", summary=f"Filial loginlari yaratildi: {len(created)} ta")
    return Response({"created": created})


# ====================================================================== tarix
def log_payload(x):
    return {"id": x.id, "at": x.at, "user": user_name(x.user), "user_id": x.user_id,
            "branch": x.branch.name if x.branch_id else "", "branch_id": x.branch_id, "item": x.item_id,
            "entity": x.entity, "action": x.action, "action_label": dict(Log.ACTIONS).get(x.action, x.action),
            "summary": x.summary, "changes": x.changes}


@inv_api(["GET"], [HasInventory])
def logs(request):
    p = request.query_params
    qs = Log.objects.select_related("user", "branch")
    ids = branch_scope(request.user)
    if ids is not None:
        qs = qs.filter(branch_id__in=ids)
    if p.get("branch"):
        qs = qs.filter(branch_id=_int(p["branch"]))
    if p.get("user"):
        qs = qs.filter(user_id=_int(p["user"]))
    if p.get("action"):
        qs = qs.filter(action__in=p["action"].split(","))
    if p.get("entity"):
        qs = qs.filter(entity=p["entity"])
    if p.get("item"):
        qs = qs.filter(item_id=_int(p["item"]))
    if p.get("date_from"):
        qs = qs.filter(at__date__gte=p["date_from"])
    if p.get("date_to"):
        qs = qs.filter(at__date__lte=p["date_to"])
    if p.get("q"):
        qs = qs.filter(summary__icontains=p["q"])
    total = qs.count()
    page_size = min(_int(p.get("page_size"), 50) or 50, 200)
    page = max(_int(p.get("page"), 1) or 1, 1)
    users_qs = Log.objects.filter(user__isnull=False)
    if ids is not None:
        users_qs = users_qs.filter(branch_id__in=ids)
    people = set(users_qs.values_list("user_id", flat=True).distinct())
    return Response({"count": total, "page": page, "page_size": page_size,
                     "results": [log_payload(x) for x in qs[(page - 1) * page_size: page * page_size]],
                     "users": [{"id": u.id, "name": user_name(u)} for u in User.objects.filter(pk__in=people)]})


# ====================================================================== statistika va analitika
SLOW_HOURS, IDLE_DAYS = 48, 3


def activity_flag(b, rows, last_at, now):
    if b.status == Branch.DONE:
        return "done"
    if not rows and not last_at:
        return "idle"
    if last_at and now - last_at <= timedelta(hours=24):
        return "active"
    if last_at and now - last_at <= timedelta(hours=SLOW_HOURS):
        return "slowing"
    return "slow"


@inv_api(["GET"], [HasInventory])
def stats(request):
    return Response(compute_stats(request))


def compute_stats(request):
    now = timezone.now()
    today = timezone.localdate()
    days = min(max(_int(request.query_params.get("days"), 30) or 30, 7), 180)
    since = now - timedelta(days=days)
    ids = branch_scope(request.user)
    branches_qs = Branch.objects.all() if ids is None else Branch.objects.filter(pk__in=ids)
    items_qs = Item.objects.filter(is_deleted=False)
    logs_qs = Log.objects.all()
    emp_qs = Employee.objects.filter(is_active=True)
    if ids is not None:
        items_qs, logs_qs, emp_qs = items_qs.filter(branch_id__in=ids), logs_qs.filter(branch_id__in=ids), \
            emp_qs.filter(branch_id__in=ids)
    if request.query_params.get("org"):
        items_qs = items_qs.filter(org_id=_int(request.query_params["org"]))

    start_today = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    week_ago = now - timedelta(days=7)
    agg = {r["branch_id"]: r for r in items_qs.values("branch_id").annotate(
        rows=Count("id"), qty=Sum("quantity"),
        broken=Sum("quantity", filter=Q(condition__in=[Item.BROKEN, Item.REPAIR])),
        missing=Sum("quantity", filter=Q(condition=Item.MISSING)),
        no_serial=Count("id", filter=Q(serial="")), no_employee=Count("id", filter=Q(employee__isnull=True)),
        today=Count("id", filter=Q(created_at__gte=start_today)), week=Count("id", filter=Q(created_at__gte=week_ago)))}
    photo_rows = {r["branch_id"]: r["n"] for r in items_qs.filter(photos__isnull=False).values("branch_id")
                  .annotate(n=Count("id", distinct=True))}
    last = {r["branch_id"]: r["m"] for r in logs_qs.values("branch_id").annotate(m=Max("at"))}
    emp = {r["branch_id"]: r for r in emp_qs.values("branch_id").annotate(
        n=Count("id", distinct=True),
        with_dev=Count("id", distinct=True, filter=Q(items__is_deleted=False, items__isnull=False)))}
    collectors = {}
    for acc in Access.objects.filter(level=COLLECTOR, user__is_active=True).prefetch_related("branches"):
        for b in acc.branches.all():
            collectors[b.id] = collectors.get(b.id, 0) + 1

    branch_rows = []
    for b in branches_qs:
        a = agg.get(b.id, {})
        rows, qty = a.get("rows", 0), a.get("qty") or 0
        e = emp.get(b.id, {})
        last_at = last.get(b.id)
        branch_rows.append({
            **branch_payload(b), "rows": rows, "qty": qty, "broken": a.get("broken") or 0,
            "missing": a.get("missing") or 0, "no_serial": a.get("no_serial", 0),
            "no_employee": a.get("no_employee", 0), "with_photo": photo_rows.get(b.id, 0),
            "today": a.get("today", 0), "week": a.get("week", 0), "last_at": last_at,
            "employees": e.get("n", 0), "employees_with_devices": e.get("with_dev", 0),
            "coverage": round(100 * e.get("with_dev", 0) / e["n"]) if e.get("n") else None,
            "photo_pct": round(100 * photo_rows.get(b.id, 0) / rows) if rows else None,
            "collectors": collectors.get(b.id, 0), "flag": activity_flag(b, rows, last_at, now),
        })

    # Kunlik faollik (tarixdan)
    daily = {}
    for r in logs_qs.filter(at__gte=since, entity="item").values("at", "action"):
        d = timezone.localtime(r["at"]).date().isoformat()
        slot = daily.setdefault(d, {"date": d, "create": 0, "update": 0, "delete": 0})
        if r["action"] in slot:
            slot[r["action"]] += 1
        elif r["action"] == Log.IMPORT:
            slot["create"] += 1
    series = []
    for i in range(days, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        series.append(daily.get(d, {"date": d, "create": 0, "update": 0, "delete": 0}))

    by_cond = {r["condition"]: r["q"] or 0 for r in items_qs.values("condition").annotate(q=Sum("quantity"))}
    by_type = list(items_qs.values("device_type__name", "device_type__group").annotate(rows=Count("id"), qty=Sum("quantity"))
                   .order_by("-qty"))
    by_group = {}
    for r in by_type:
        g = r["device_type__group"] or "Boshqa"
        by_group[g] = by_group.get(g, 0) + (r["qty"] or 0)
    by_org = list(items_qs.values("org__name").annotate(qty=Sum("quantity"), rows=Count("id")).order_by("-qty"))
    by_location = list(items_qs.values("location").annotate(qty=Sum("quantity")).order_by("-qty")[:12])

    people = {}
    for r in logs_qs.filter(user__isnull=False, entity="item").values("user_id", "action").annotate(n=Count("id"), m=Max("at")):
        p = people.setdefault(r["user_id"], {"create": 0, "update": 0, "delete": 0, "last_at": None})
        if r["action"] in ("create", "update", "delete"):
            p[r["action"]] += r["n"]
        if not p["last_at"] or r["m"] > p["last_at"]:
            p["last_at"] = r["m"]
    week_by_user = {r["user_id"]: r["n"] for r in logs_qs.filter(at__gte=week_ago, action=Log.CREATE, entity="item")
                    .values("user_id").annotate(n=Count("id"))}
    users_map = {u.id: u for u in User.objects.filter(pk__in=people).prefetch_related("inv_access__branches")}
    leaderboard = []
    for uid, p in people.items():
        u = users_map.get(uid)
        if not u:
            continue
        acc = getattr(u, "inv_access", None)
        leaderboard.append({"user_id": uid, "name": user_name(u), "username": u.username, **p,
                            "week": week_by_user.get(uid, 0),
                            "branches": [b.name for b in acc.branches.all()] if acc else []})
    leaderboard.sort(key=lambda x: (-x["create"], -x["update"]))

    total_rows = sum(r["rows"] for r in branch_rows)
    totals = {
        "rows": total_rows, "qty": sum(r["qty"] for r in branch_rows), "branches": len(branch_rows),
        "done": sum(1 for r in branch_rows if r["status"] == Branch.DONE),
        "active": sum(1 for r in branch_rows if r["status"] == Branch.ACTIVE),
        "planned": sum(1 for r in branch_rows if r["status"] == Branch.PLANNED),
        "slow": sum(1 for r in branch_rows if r["flag"] in ("slow", "idle")),
        "employees": sum(r["employees"] for r in branch_rows), "employees_total": emp_qs.count(),
        "employees_with_devices": sum(r["employees_with_devices"] for r in branch_rows),
        "today": sum(r["today"] for r in branch_rows), "week": sum(r["week"] for r in branch_rows),
        "no_serial": sum(r["no_serial"] for r in branch_rows), "no_employee": sum(r["no_employee"] for r in branch_rows),
        "with_photo": sum(r["with_photo"] for r in branch_rows),
        "broken": sum(r["broken"] for r in branch_rows), "missing": sum(r["missing"] for r in branch_rows),
        "deleted": Item.objects.filter(is_deleted=True, **({} if ids is None else {"branch_id__in": ids})).count(),
        "collectors": Access.objects.filter(level=COLLECTOR, user__is_active=True).count(),
        "collectors_logged_in": Access.objects.filter(level=COLLECTOR, user__is_active=True,
                                                      user__last_login__isnull=False).count(),
    }
    return {
        "generated_at": now, "days": days, "totals": totals, "branches": branch_rows, "daily": series,
        "by_condition": [{"value": v, "label": l, "qty": by_cond.get(v, 0)} for v, l in Item.CONDITIONS],
        "by_type": [{"name": r["device_type__name"], "group": r["device_type__group"], "rows": r["rows"],
                     "qty": r["qty"] or 0} for r in by_type],
        "by_group": [{"name": k, "qty": v} for k, v in sorted(by_group.items(), key=lambda kv: -kv[1])],
        "by_org": [{"name": r["org__name"] or "(tanlanmagan)", "qty": r["qty"] or 0, "rows": r["rows"]} for r in by_org],
        "by_location": [{"name": r["location"] or "(yozilmagan)", "qty": r["qty"] or 0} for r in by_location],
        "leaderboard": leaderboard[:50],
    }


# ====================================================================== Xodimlar tuzilmasidan import
@inv_api(["POST"], [IsManager])
def employees_from_staff(request):
    """Zona'dagi "Xodimlar tuzilmasi" (dala xodimlari) dan: loyiha = brend jamoasi, filial = shahar bo'yicha."""
    from zona.models import StaffPerson

    from .seed import CITY_ALIASES, norm
    by_code = {b.code: b for b in Branch.objects.all()}
    by_name = {norm(b.name): b for b in Branch.objects.all()}
    created = updated = unmapped = 0
    dry = bool(request.data.get("dry_run"))
    for sp in StaffPerson.objects.filter(is_vacancy=False).select_related("project", "unit"):
        if not sp.name.strip():
            continue
        city = norm(sp.city)
        branch = by_code.get(CITY_ALIASES.get(city, "")) or by_name.get(city)
        if not branch:
            unmapped += 1
        emp = Employee.objects.filter(source=Employee.STAFF, external_id=str(sp.pk)).first()
        fields = {"full_name": sp.name.strip()[:150], "position": (sp.get_role_display() or sp.position)[:120],
                  "phone": sp.phone[:40], "project": sp.project.name[:120],
                  "department": (sp.unit.title if sp.unit_id else "")[:120]}
        if emp:
            if not dry:
                for f, v in fields.items():
                    if v and getattr(emp, f) != v:
                        setattr(emp, f, v)
                if branch and not emp.branch_id:
                    emp.branch = branch
                emp.save()
            updated += 1
        else:
            if not dry:
                Employee.objects.create(**fields, branch=branch, source=Employee.STAFF, external_id=str(sp.pk),
                                        created_by=request.user)
            created += 1
    if not dry and (created or updated):
        log(request, Log.IMPORT, entity="employee",
            summary=f"Xodimlar tuzilmasidan: {created} yangi, {updated} yangilandi, {unmapped} filialsiz")
    return Response({"created": created, "updated": updated, "unmapped": unmapped, "dry_run": dry})


# yordamchi: boshqa modullar (io) uchun
__all__ = ["inv_api", "bad", "log", "item_payload", "employee_payload", "access_of", "DIRECTOR", "IsManagerOrDirector"]
