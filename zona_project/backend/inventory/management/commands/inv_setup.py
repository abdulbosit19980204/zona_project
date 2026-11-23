"""IT inventarizatsiyasini ishga tushirish: katalog (bo'sh bo'lsa) + har bir filial uchun login + loginlar fayli.

    python manage.py inv_setup --logins --out /root/inventarizatsiya_loginlar.xlsx

Mavjud loginlarga tegilmaydi (paroli o'zgarmaydi); faqat logini yo'q filiallarga yangi login yaratiladi.
Fayl veb ildizdan tashqarida yozilsin — unda parollar bor.
"""
from django.core.management.base import BaseCommand
from django.test import RequestFactory

from inventory.models import Access, Branch
from inventory.seed import seed_catalog


class Command(BaseCommand):
    help = "Inventarizatsiya katalogi, filial loginlari va loginlar fayli"

    def add_arguments(self, parser):
        parser.add_argument("--logins", action="store_true", help="logini yo'q har bir filialga login yaratish")
        parser.add_argument("--out", default="", help="loginlar faylini (xlsx) shu yo'lga yozish")

    def handle(self, *args, logins=False, out="", **opts):
        added = seed_catalog()
        self.stdout.write(f"Katalog: {added} ta yangi yozuv")
        if logins:
            from inventory.views import branch_login, create_access_user
            from django.contrib.auth import get_user_model
            User = get_user_model()
            for b in Branch.objects.all():
                if Access.objects.filter(level=Access.COLLECTOR, branches=b).exists():
                    continue
                base = username = branch_login(b)
                n = 1
                while User.objects.filter(username__iexact=username).exists():
                    n += 1
                    username = f"{base}{n}"
                _, password = create_access_user(username, first_name=b.name, last_name="filiali",
                                                 level=Access.COLLECTOR, branch_ids=[b.id], note=f"{b.name} filiali uchun")
                self.stdout.write(f"  {b.name}: {username}")
        if out:
            from django.contrib.auth import get_user_model

            from inventory.io import credentials
            admin = get_user_model().objects.filter(is_superuser=True, is_active=True).first()
            if not admin:
                self.stderr.write("Faol superuser yo'q — fayl yozilmadi")
                return
            request = RequestFactory().get("/api/inventory/users/credentials/")
            from rest_framework.test import force_authenticate
            force_authenticate(request, user=admin)
            response = credentials(request)
            with open(out, "wb") as fh:
                fh.write(response.content)
            self.stdout.write(self.style.SUCCESS(f"Loginlar fayli: {out}"))
