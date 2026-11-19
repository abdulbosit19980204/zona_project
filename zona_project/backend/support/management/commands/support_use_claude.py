"""Claude'ni support bot uchun asosiy model qilish (zaxira — mavjud Gemini).

  ANTHROPIC_API_KEY=... python manage.py support_use_claude --key-env ANTHROPIC_API_KEY [--model claude-opus-5-5]
Kalit bazada shifrlangan holda saqlanadi (faylga yozilmaydi). Keyin uni Sozlamalar → AI bo'limida ham o'zgartirish mumkin.
"""
import os

from django.core.management.base import BaseCommand, CommandError

from support.models import Settings
from zona.crypto import encrypt
from zona.models import AIProvider, AITaskConfig


class Command(BaseCommand):
    help = "Support bot javoblari uchun Anthropic Claude'ni ulash (asosiy), Gemini — zaxira."

    def add_arguments(self, parser):
        parser.add_argument("--key-env", default="ANTHROPIC_API_KEY")
        parser.add_argument("--model", default="claude-opus-5-5")
        parser.add_argument("--fallback-model", default="gemini-2.5-flash")

    def handle(self, *args, **opts):
        key = os.environ.get(opts["key_env"], "").strip()
        provider = AIProvider.objects.filter(kind="anthropic").first()
        if not provider:
            if not key:
                raise CommandError(f"{opts['key_env']} muhit o'zgaruvchisida Anthropic API kaliti yo'q")
            provider = AIProvider.objects.create(name="Anthropic Claude", kind="anthropic", is_active=True, api_key_enc=encrypt(key))
        elif key:
            provider.api_key_enc, provider.is_active = encrypt(key), True
            provider.save(update_fields=["api_key_enc", "is_active", "updated_at"])
        gemini = AIProvider.objects.filter(kind="gemini", is_active=True).first()
        cfg, _ = AITaskConfig.objects.get_or_create(task=AITaskConfig.SUPPORT)
        cfg.enabled, cfg.provider, cfg.model = True, provider, opts["model"]
        cfg.effort = cfg.effort or "low"
        if gemini:
            cfg.fallback_provider, cfg.fallback_model = gemini, opts["fallback_model"]
        cfg.save()
        s = Settings.load()
        s.ai_enabled = True
        s.save(update_fields=["ai_enabled", "updated_at"])
        self.stdout.write(f"support: {provider.name} / {cfg.model} (zaxira: {gemini.name + ' / ' + cfg.fallback_model if gemini else 'yoq'})")
