"""Xodimning tasdiqnomasi: unga biriktirilgan qurilmalar ro'yxati havola orqali ochiladi, xodim imzo bilan tasdiqlaydi.

Havola maxfiy (taxmin qilib bo'lmaydigan token) va login talab qilmaydi — xodim uni Telegram orqali oladi.
Ro'yxat havola yaratilgan paytdagi holatda saqlanadi; keyin qurilmalar o'zgarsa tasdiqnoma "eskirgan" bo'ladi.
"""
import base64
import io
import secrets
import uuid

from django.core.signing import Signer
from django.db.models import Q
from django.http import FileResponse, Http404
from django.utils import timezone
from openpyxl import Workbook
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import photos as photo_store
from .access import CanWrite, HasInventory, branch_scope, can_write_branch, scoped
from .models import Ack, Employee, Item, Log
from .views import COND_LABEL, _int, _s, bad, inv_api, log, user_name

_sig = Signer(salt="inventory-signature")
MAX_SIGNATURE = 600 * 1024


def _items_of(emp):
    return list(Item.objects.filter(employee=emp, is_deleted=False).select_related("device_type", "branch")
                .prefetch_related("photos").order_by("device_type__order", "inv_number"))


def snapshot(items):
    return [{"id": it.id, "inv_number": it.inv_number, "type": it.device_type.name, "type_ru": it.device_type.name_ru,
             "group": it.device_type.group, "brand": it.brand, "model": it.model, "serial": it.serial,
             "quantity": it.quantity, "condition": it.condition, "condition_label": COND_LABEL.get(it.condition, ""),
             "location": it.location, "branch": it.branch.name, "photos": [p.id for p in it.photos.all()][:6]}
            for it in items]


def fingerprint(rows):
    return sorted((r["id"], r["quantity"], r["serial"]) for r in rows)


def is_outdated(ack, current=None):
    if ack.status == Ack.REVOKED:
        return False
    current = current if current is not None else snapshot(_items_of(ack.employee))
    return fingerprint(current) != fingerprint(ack.items or [])


def _photo_urls(ids):
    return [{"thumb": f"/api/inventory/photos/{pid}/file/?k={photo_store.sign(pid)}&t=1",
             "url": f"/api/inventory/photos/{pid}/file/?k={photo_store.sign(pid)}"} for pid in ids]


def signature_url(ack):
    return f"/api/inventory/acks/{ack.pk}/signature/?k={_sig.signature(str(ack.pk))[:24]}" if ack.signature else ""


def ack_payload(ack, full=False, current=None):
    emp = ack.employee
    issues = [r for r in ack.result or [] if not r.get("ok", True)]
    data = {
        "id": ack.id, "token": ack.token, "path": f"/ack/{ack.token}", "status": ack.status,
        "employee": emp.id, "employee_name": emp.full_name, "position": emp.position, "phone": emp.phone,
        "telegram": emp.telegram, "branch": ack.branch.name if ack.branch_id else "", "branch_id": ack.branch_id,
        "items_count": len(ack.items or []), "issues": len(issues), "created_at": ack.created_at,
        "created_by": user_name(ack.created_by), "opened_at": ack.opened_at, "signed_at": ack.signed_at,
        "signer_name": ack.signer_name, "outdated": is_outdated(ack, current),
    }
    if full:
        result = {r.get("id"): r for r in ack.result or []}
        data.update({
            "items": [{**row, "photos": _photo_urls(row.get("photos") or []), "result": result.get(row["id"])}
                      for row in ack.items or []],
            "comment": ack.comment, "signature_url": signature_url(ack), "ip": ack.ip, "user_agent": ack.user_agent,
            "lang": ack.lang,
        })
    return data


def create_ack(request, emp):
    items = _items_of(emp)
    if not items:
        return None
    Ack.objects.filter(employee=emp, status=Ack.PENDING).update(status=Ack.REVOKED)
    ack = Ack.objects.create(employee=emp, branch=emp.branch, token=secrets.token_urlsafe(24), items=snapshot(items),
                             created_by=request.user if request.user.is_authenticated else None)
    log(request, Log.CREATE, branch=emp.branch, entity="ack",
        summary=f"Tasdiqlash havolasi: {emp.full_name} ({len(items)} ta qurilma)")
    return ack


def _employees_scope(request):
    qs = Employee.objects.select_related("branch")
    ids = branch_scope(request.user)
    return qs if ids is None else qs.filter(branch_id__in=ids)


# ====================================================================== panel (login bilan)
@inv_api(["POST"], [CanWrite])
def employee_ack(request, pk):
    emp = _employees_scope(request).filter(pk=pk).first()
    if not emp:
        raise Http404
    if not can_write_branch(request.user, emp.branch_id):
        return bad("Bu xodimni o'zgartirish huquqingiz yo'q.", status.HTTP_403_FORBIDDEN)
    ack = create_ack(request, emp)
    if not ack:
        return bad("Bu xodimga qurilma biriktirilmagan.")
    return Response(ack_payload(ack), status=status.HTTP_201_CREATED)


@inv_api(["POST"], [CanWrite])
def acks_bulk(request):
    """Qurilmasi bor xodimlarga havola: amaldagi (eskirmagan) havolasi yoki imzosi borlar o'tkazib yuboriladi."""
    qs = _employees_scope(request).filter(is_active=True, items__is_deleted=False).distinct()
    bid = _int(request.data.get("branch"))
    if bid:
        qs = qs.filter(branch_id=bid)
    created = skipped = 0
    for emp in qs:
        if not can_write_branch(request.user, emp.branch_id):
            continue
        last = Ack.objects.filter(employee=emp).exclude(status=Ack.REVOKED).order_by("-created_at").first()
        if last and not is_outdated(last):
            skipped += 1
            continue
        if create_ack(request, emp):
            created += 1
    return Response({"created": created, "skipped": skipped})


def _filtered(request):
    p = request.query_params
    qs = Ack.objects.select_related("employee", "branch", "created_by").exclude(status=Ack.REVOKED)
    ids = branch_scope(request.user)
    if ids is not None:
        qs = qs.filter(branch_id__in=ids)
    if p.get("branch"):
        qs = qs.filter(branch_id=_int(p["branch"]))
    if p.get("status") in (Ack.PENDING, Ack.SIGNED):
        qs = qs.filter(status=p["status"])
    if p.get("q"):
        q = p["q"].strip().lstrip("@")
        qs = qs.filter(Q(employee__full_name__icontains=q) | Q(employee__phone__icontains=q)
                       | Q(employee__telegram__icontains=q))
    # har bir xodim uchun faqat oxirgisi
    latest = {}
    for a in qs.order_by("created_at"):
        latest[a.employee_id] = a
    rows = sorted(latest.values(), key=lambda a: a.created_at, reverse=True)
    current = {}
    for it in Item.objects.filter(employee_id__in=latest.keys(), is_deleted=False).select_related("device_type", "branch") \
            .prefetch_related("photos"):
        current.setdefault(it.employee_id, []).append(it)
    out = []
    for a in rows:
        payload = ack_payload(a, current=snapshot(current.get(a.employee_id, [])))
        if p.get("issues") == "1" and not payload["issues"]:
            continue
        if p.get("outdated") == "1" and not payload["outdated"]:
            continue
        out.append(payload)
    return out


@inv_api(["GET"], [HasInventory])
def acks(request):
    rows = _filtered(request)
    return Response({"count": len(rows), "results": rows[:3000]})


@inv_api(["GET"], [HasInventory])
def ack_detail(request, pk):
    ack = scoped(Ack.objects.select_related("employee", "branch", "created_by"), request.user).filter(pk=pk).first()
    if not ack:
        raise Http404
    return Response(ack_payload(ack, full=True))


@inv_api(["POST"], [CanWrite])
def ack_revoke(request, pk):
    ack = scoped(Ack.objects.select_related("employee"), request.user).filter(pk=pk).first()
    if not ack or not can_write_branch(request.user, ack.branch_id):
        raise Http404
    if ack.status == Ack.PENDING:
        ack.status = Ack.REVOKED
        ack.save(update_fields=["status"])
        log(request, Log.DELETE, branch=ack.branch, entity="ack", summary=f"Havola bekor qilindi: {ack.employee.full_name}")
    return Response(ack_payload(ack))


@inv_api(["GET"], [HasInventory])
def acks_export(request):
    from zona import conf

    from .io import XLSX, _file, _local, _now_tag, _save, style_table
    site = (conf.get("FRONTEND_URL") or "").rstrip("/")
    if not site.startswith("http"):
        site = request.build_absolute_uri("/").rstrip("/")
    status_label = {Ack.PENDING: "Kutilmoqda", Ack.SIGNED: "Imzolangan"}
    wb = Workbook()
    ws = wb.active
    ws.title = "Tasdiqnomalar"
    cols = [("Filial", 14), ("Xodim", 28), ("Lavozimi", 18), ("Telefon", 18), ("Telegram", 18), ("Holat", 13),
            ("Qurilmalar", 10), ("E'tirozlar", 10), ("Eskirgan", 9), ("Havola", 50), ("Yaratildi", 17),
            ("Ochildi", 17), ("Imzolandi", 17), ("Imzolagan (F.I.Sh.)", 24)]
    ws.append([c[0] for c in cols])
    for r in _filtered(request):
        ws.append([r["branch"], r["employee_name"], r["position"], r["phone"], f"@{r['telegram']}" if r["telegram"] else "",
                   status_label.get(r["status"], r["status"]), r["items_count"], r["issues"], "ha" if r["outdated"] else "",
                   site + r["path"], _local(r["created_at"]), _local(r["opened_at"]), _local(r["signed_at"]), r["signer_name"]])
    style_table(ws, [c[1] for c in cols])
    return _file(_save(wb), f"tasdiqnomalar_{_now_tag()}.xlsx", XLSX)


@inv_api(["GET"], [AllowAny], auth=False)
def ack_signature(request, pk):
    if _sig.signature(str(pk))[:24] != request.query_params.get("k"):
        raise Http404
    ack = Ack.objects.filter(pk=pk).first()
    if not ack or not ack.signature:
        raise Http404
    try:
        fh = open(ack.signature, "rb")
    except OSError as e:
        raise Http404 from e
    resp = FileResponse(fh, content_type="image/png")
    resp["Cache-Control"] = "private, max-age=86400"
    return resp


# ====================================================================== xodim uchun ochiq sahifa (loginsiz)
def _public(ack):
    data = ack_payload(ack, full=True)
    for key in ("ip", "user_agent", "created_by", "token"):
        data.pop(key, None)
    data["company"] = "StarGroup"
    return data


@inv_api(["GET"], [AllowAny], auth=False)
def public_ack(request, token):
    ack = Ack.objects.select_related("employee", "branch").filter(token=str(token)[:64]).exclude(status=Ack.REVOKED).first()
    if not ack:
        return bad("Havola topilmadi yoki bekor qilingan.", status.HTTP_404_NOT_FOUND)
    if not ack.opened_at:
        ack.opened_at = timezone.now()
        ack.save(update_fields=["opened_at"])
    return Response(_public(ack))


@inv_api(["POST"], [AllowAny], auth=False)
def public_sign(request, token):
    from PIL import Image, UnidentifiedImageError
    ack = Ack.objects.select_related("employee", "branch").filter(token=str(token)[:64]).exclude(status=Ack.REVOKED).first()
    if not ack:
        return bad("Havola topilmadi yoki bekor qilingan.", status.HTTP_404_NOT_FOUND)
    if ack.status == Ack.SIGNED:
        return bad("Bu tasdiqnoma allaqachon imzolangan.")
    name = _s(request.data.get("name"), 150)
    if len(name) < 5 or " " not in name:
        return bad("Ism-familiyangizni to'liq yozing.")
    raw = str(request.data.get("signature") or "")
    if not raw.startswith("data:image/png;base64,"):
        return bad("Imzo qo'ying (barmoq bilan chizing).")
    try:
        png = base64.b64decode(raw.split(",", 1)[1], validate=True)
        if len(png) > MAX_SIGNATURE:
            raise ValueError
        img = Image.open(io.BytesIO(png))
        img.verify()
    except (ValueError, UnidentifiedImageError, OSError):
        return bad("Imzo rasmi noto'g'ri.")
    known = {row["id"] for row in ack.items or []}
    result = []
    for r in request.data.get("items") or []:
        rid = _int(r.get("id")) if isinstance(r, dict) else None
        if rid in known:
            result.append({"id": rid, "ok": bool(r.get("ok", True)), "comment": _s(r.get("comment"), 300)})
    seen = {r["id"] for r in result}
    result += [{"id": rid, "ok": True, "comment": ""} for rid in known - seen]
    folder = photo_store.media_dir() / "signatures" / f"{timezone.now():%Y}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}.png"
    path.write_bytes(png)
    ack.signature, ack.signer_name, ack.result = str(path), name, result
    ack.comment = _s(request.data.get("comment"), 1000)
    ack.lang = _s(request.data.get("lang"), 4)
    ack.ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", ""))[:64]
    ack.user_agent = _s(request.META.get("HTTP_USER_AGENT"), 300)
    ack.status, ack.signed_at = Ack.SIGNED, timezone.now()
    ack.save()
    issues = sum(1 for r in result if not r["ok"])
    Log.objects.create(branch=ack.branch, entity="ack", action=Log.SIGN,
                       summary=f"Imzoladi: {ack.employee.full_name} ({len(result)} ta qurilma"
                               + (f", {issues} ta e'tiroz)" if issues else ")"),
                       changes={"signer": name, "issues": issues})
    return Response(_public(ack))
