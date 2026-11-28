"""Jonli yangilanishlar (WebSocket, Django Channels).

Ulanish:  ws://<server>/ws/events/?token=<JWT access>
Xabarlar: {"type": "event", "data": {...Event}}      — tuzilmada o'zgarish bo'ldi
          {"type": "approval", "data": {...}}         — tasdiqlash so'rovi yaratildi yoki hal qilindi
Frontend xabarni olgach tegishli ma'lumotni qayta yuklaydi.
"""
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from . import conf

GROUP = "zona"


@database_sync_to_async
def _inventory_only(user):
    from .permissions import role_of
    return role_of(user) == "inventory"


@database_sync_to_async
def _user_from_token(raw):
    auth = JWTAuthentication()
    try:
        return auth.get_user(auth.get_validated_token(raw))
    except (InvalidToken, TokenError, Exception):  # noqa: BLE001 — har qanday xato: anonim
        return AnonymousUser()


class JWTAuthMiddleware:
    """?token=<access> dan foydalanuvchini aniqlaydi (brauzer WebSocket'ga sarlavha qo'sha olmaydi)."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        token = parse_qs(scope.get("query_string", b"").decode()).get("token", [""])[0]
        user = scope.get("user")
        if token:
            user = await _user_from_token(token)
        scope["user"] = user or AnonymousUser()
        return await self.inner(scope, receive, send)


class EventsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not (user and user.is_authenticated) and not conf.get("PUBLIC_READ"):
            await self.close(code=4401)
            return
        if user and user.is_authenticated and await _inventory_only(user):
            await self.close(code=4403)  # faqat inventarizatsiya logini: tuzilma yangilanishlari unga yuborilmaydi
            return
        await self.channel_layer.group_add(GROUP, self.channel_name)
        await self.accept()
        await self.send_json({"type": "hello", "data": {"user": user.get_username() if user and user.is_authenticated else ""}})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(GROUP, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "ping":
            try:  # Redis'da guruh a'zoligi muddatli — har ping'da yangilanadi (uzoq ochiq turgan panel ham xabar oladi)
                await self.channel_layer.group_add(GROUP, self.channel_name)
            except Exception:  # noqa: BLE001 — jonli yangilanish ixtiyoriy
                pass
            await self.send_json({"type": "pong"})

    async def zona_message(self, message):
        await self.send_json(message["payload"])


def broadcast(kind, data):
    """Barcha ulangan mijozlarga xabar. Tranzaksiya yakunlangach yuboriladi; xato saytni to'xtatmaydi."""
    layer = get_channel_layer()
    if layer is None:
        return

    def send():
        try:
            async_to_sync(layer.group_send)(GROUP, {"type": "zona.message", "payload": {"type": kind, "data": data}})
        except Exception:  # noqa: BLE001 — jonli yangilanish ixtiyoriy
            pass

    transaction.on_commit(send)
