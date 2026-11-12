"""Autentifikatsiya: JWT (access + refresh) — frontend (Next.js) shu bilan ishlaydi.
Django sessiyasi ham qabul qilinadi (masalan, /admin/ ga kirgan foydalanuvchi uchun)."""
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

AUTHENTICATION = [JWTAuthentication, SessionAuthentication]


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def revoke_all(user, keep_jti=None):
    """Foydalanuvchining barcha refresh tokenlarini bekor qiladi (parol o'zgarganda, administrator talabi bilan)."""
    count = 0
    for token in OutstandingToken.objects.filter(user=user):
        if token.jti == keep_jti:
            continue
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        count += created
    return count
