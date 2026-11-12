"""Har bir yangi tarix yozuvi va tasdiqlash so'rovi WebSocket orqali tarqatiladi."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ChangeRequest, Event
from .realtime import broadcast


@receiver(post_save, sender=Event)
def on_event(sender, instance, created, **kwargs):
    if created:
        broadcast("event", {"id": instance.id, "kind": instance.kind, "subject": instance.subject,
                            "from_name": instance.from_name, "to_name": instance.to_name, "text": instance.text,
                            "actor": instance.actor, "at": instance.at.isoformat()})


@receiver(post_save, sender=ChangeRequest)
def on_change_request(sender, instance, **kwargs):
    broadcast("approval", {"id": instance.id, "status": instance.status, "title": instance.title})
