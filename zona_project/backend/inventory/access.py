"""Modulga kirish huquqlari.

- manager (IT, boshqaruvchi): hamma filial, katalog, foydalanuvchilar, import/eksport. Zona administratori — avtomatik.
- director (rahbar): ko'radi (analitika, ro'yxatlar), o'zgartira olmaydi. Filial biriktirilmagan — hamma filial;
  biriktirilgan (filial direktori) — faqat o'z filiali.
- collector (filial xodimi): faqat o'ziga biriktirilgan filial(lar)ni ko'radi va to'ldiradi.

Zona'da "inventory" rolidagi foydalanuvchilar platformaning boshqa sahifalari va API'lariga kira olmaydi
(zona.permissions.RANK da 0 daraja) — faqat shu modul.
"""
from rest_framework.permissions import BasePermission

from .models import Access

MANAGER, DIRECTOR, COLLECTOR = Access.MANAGER, Access.DIRECTOR, Access.COLLECTOR


def _zona_admin(user):
    from zona.models import Profile
    from zona.permissions import role_of
    return role_of(user) == Profile.ADMIN


def access_of(user):
    if not user or not user.is_authenticated:
        return None
    cached = getattr(user, "_inv_access_cache", False)
    if cached is not False:
        return cached
    acc = Access.objects.filter(user=user).prefetch_related("branches").first()
    user._inv_access_cache = acc
    return acc


def level_of(user):
    if not user or not user.is_authenticated or not user.is_active:
        return None
    if _zona_admin(user):
        return MANAGER
    acc = access_of(user)
    return acc.level if acc else None


def branch_scope(user):
    """None — hamma filial; aks holda ko'rinadigan filial id'lari to'plami.
    Rahbar: filial biriktirilmagan — hamma filial; biriktirilgan (filial direktori) — faqat o'sha filial(lar)."""
    level = level_of(user)
    if level == MANAGER:
        return None
    acc = access_of(user)
    if level == DIRECTOR:
        ids = {b.id for b in acc.branches.all()} if acc else set()
        return ids or None
    return {b.id for b in acc.branches.all()} if acc else set()


def scoped(qs, user, field="branch_id"):
    ids = branch_scope(user)
    return qs if ids is None else qs.filter(**{f"{field}__in": ids})


def can_write_branch(user, branch_id):
    level = level_of(user)
    if level == MANAGER:
        return True
    if level == COLLECTOR:
        return branch_id in (branch_scope(user) or set())
    return False


class HasInventory(BasePermission):
    message = "Inventarizatsiya moduliga ruxsatingiz yo'q."

    def has_permission(self, request, view):
        return level_of(request.user) is not None


class CanWrite(BasePermission):
    """O'qish — hamma ruxsat egasi; yozish — boshqaruvchi va filial xodimi (filial tekshiruvi view ichida)."""
    message = "Sizda faqat ko'rish huquqi bor."

    def has_permission(self, request, view):
        level = level_of(request.user)
        if level is None:
            return False
        return request.method in ("GET", "HEAD", "OPTIONS") or level in (MANAGER, COLLECTOR)


class IsManager(BasePermission):
    message = "Bu amal faqat boshqaruvchi (IT) uchun."

    def has_permission(self, request, view):
        return level_of(request.user) == MANAGER


class IsManagerOrDirector(BasePermission):
    message = "Bu bo'lim faqat boshqaruvchi va rahbarlar uchun."

    def has_permission(self, request, view):
        return level_of(request.user) in (MANAGER, DIRECTOR)
