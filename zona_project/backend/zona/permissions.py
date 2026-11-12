"""Rollar: admin (hammasi) > editor (tuzilmani tahrirlash) > viewer (ko'rish, savol berish)."""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from . import conf
from .models import Profile

RANK = {Profile.VIEWER: 1, Profile.EDITOR: 2, Profile.ADMIN: 3}


def role_of(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return Profile.ADMIN
    profile = getattr(user, "zona_profile", None)
    if profile is None:
        profile, _ = Profile.objects.get_or_create(user=user, defaults={"role": Profile.VIEWER})
    return profile.role


def has_role(request, role):
    current = role_of(getattr(request, "user", None))
    if current is None:
        return role == Profile.VIEWER and conf.get("PUBLIC_READ") and request.method in SAFE_METHODS
    return RANK[current] >= RANK[role]


class CanView(BasePermission):
    """O'qish va savol berish (qidiruv, AI yo'naltirish)."""

    def has_permission(self, request, view):
        return has_role(request, Profile.VIEWER)


class ReadOrEdit(BasePermission):
    """O'qish: viewer; yozish: editor."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return has_role(request, Profile.VIEWER)
        return has_role(request, Profile.EDITOR)


class IsZonaAdmin(BasePermission):
    def has_permission(self, request, view):
        return has_role(request, Profile.ADMIN)


class IsAuthenticatedUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
