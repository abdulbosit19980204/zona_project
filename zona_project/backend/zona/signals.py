"""Har bir yangi tarix yozuvi va tasdiqlash so'rovi WebSocket orqali tarqatiladi; yangi matnlar tarjimaga yuboriladi."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from . import translation
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


def on_translatable_saved(sender, instance, **kwargs):
    """Matn qo'shildi yoki o'zgardi: AI fonda boshqa tillarga tarjima qiladi."""
    if translation.pending_fields(instance):
        translation.schedule()


for _model in translation.FIELDS:
    post_save.connect(on_translatable_saved, sender=_model, dispatch_uid=f"zona-translate-{_model.__name__}")
