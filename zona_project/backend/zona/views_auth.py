"""Kirish (JWT), tokenni yangilash, chiqish, o'z profili va parolini o'zgartirish."""
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .api import zona_api
from .auth import issue_tokens, revoke_all
from .permissions import IsAuthenticatedUser
from .serializers import MeSerializer, user_payload

MAX_ATTEMPTS, LOCK_SECONDS = 8, 900


@zona_api(["POST"], [AllowAny])
def login(request):
    """{username, password} -> {access, refresh, user}. Ko'p noto'g'ri urinishda 15 daqiqa bloklanadi."""
    username = str(request.data.get("username", "")).strip()
    password = str(request.data.get("password", ""))
    key = f"zona:login:{request.META.get('REMOTE_ADDR', '')}:{username.lower()}"
    attempts = cache.get(key, 0)
    if attempts >= MAX_ATTEMPTS:
        return Response({"detail": "Juda ko'p urinish. 15 daqiqadan keyin qayta urinib ko'ring."},
                        status=status.HTTP_429_TOO_MANY_REQUESTS)
    user = authenticate(request, username=username, password=password)
    if not user or not user.is_active:
        cache.set(key, attempts + 1, LOCK_SECONDS)
        return Response({"detail": "Login yoki parol noto'g'ri."}, status=status.HTTP_400_BAD_REQUEST)
    cache.delete(key)
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    return Response({**issue_tokens(user), "user": user_payload(user)})


@zona_api(["POST"], [AllowAny])
def refresh(request):
    """{refresh} -> {access, refresh}. Eski refresh token bekor qilinadi (rotatsiya).
    Yangi tokenlar foydalanuvchining joriy roli bilan qayta chiqariladi (rol o'zgarsa, darhol kuchga kiradi)."""
    from django.contrib.auth import get_user_model
    try:
        old = RefreshToken(str(request.data.get("refresh", "")))
        user = get_user_model().objects.filter(pk=old.get("user_id"), is_active=True).first()
        if user is None:
            raise TokenError("user")
        old.blacklist()
    except (TokenError, InvalidToken):
        return Response({"detail": "Seans tugagan, qayta kiring."}, status=status.HTTP_401_UNAUTHORIZED)
    return Response(issue_tokens(user))


@zona_api(["POST"], [AllowAny])
def logout(request):
    """{refresh} — shu qurilmadagi seansni yopadi."""
    try:
        RefreshToken(str(request.data.get("refresh", ""))).blacklist()
    except TokenError:
        pass
    return Response(status=status.HTTP_204_NO_CONTENT)


@zona_api(["GET", "PATCH"], [IsAuthenticatedUser])
def me(request):
    if request.method == "PATCH":
        ser = MeSerializer(request.user, data={**request.data, "username": request.user.username}, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
    return Response(user_payload(request.user))


@zona_api(["POST"], [IsAuthenticatedUser])
def change_password(request):
    """Parolni o'zgartirish: boshqa qurilmalardagi seanslar yopiladi, yangi tokenlar qaytariladi."""
    old, new = str(request.data.get("old_password", "")), str(request.data.get("new_password", ""))
    if not request.user.check_password(old):
        return Response({"old_password": "Joriy parol noto'g'ri."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        validate_password(new, request.user)
    except ValidationError as e:
        return Response({"new_password": list(e.messages)}, status=status.HTTP_400_BAD_REQUEST)
    request.user.set_password(new)
    request.user.save()
    revoke_all(request.user)
    return Response({"ok": True, **issue_tokens(request.user)})
