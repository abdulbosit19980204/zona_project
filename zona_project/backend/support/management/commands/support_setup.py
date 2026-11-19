"""Boshlang'ich sozlash (idempotent, qayta ishga tushirish xavfsiz).

- Uchta namunaviy standart holatni "ko'rib chiqilmoqda" holatida qo'shadi (bor bo'lsa tegmaydi).
- --token-env NOMI: bot tokenini muhit o'zgaruvchisidan olib, bot qo'shadi (token faylga yozilmaydi,
  bazada shifrlangan holda saqlanadi). Shu token bilan bot bor bo'lsa — tegmaydi.
"""
import os

from django.core.management.base import BaseCommand, CommandError

from support.models import MODE_SHADOW, Bot, Entry
from zona.crypto import decrypt, encrypt

SEED = [
    {
        "title": "PRBC: yangi klient qo'shish bo'limi ko'rinmaydi (rol Employee)",
        "triggers": ["your access && employee", "yangi klient && qo'sh", "новый клиент", "добавить клиент",
                     "klient qo'shish", "klient qoshish"],
        "extract": [],
        "answer": ("Yangi klient (savdo nuqtasi) qo'shish bo'limi faqat agent yoki supervayzer rolida ko'rinadi.\n"
                   "Rasmdagi akkauntda rol: **Employee** — shuning uchun bo'lim yo'q.\n\n"
                   "Nima qilish kerak:\n"
                   "1. Supervayzeringizga yozing — u sizga agent rolini berishni so'raydi.\n"
                   "2. Telegram akkauntingizni PRBC'ga bog'lang (profilda Telegram «—» bo'lsa bog'lanmagan).\n"
                   "3. Rol berilgach PRBC'ni qayta oching — «Yangi klient» bo'limi chiqadi."),
        "answer_ru": ("Раздел добавления нового клиента (торговой точки) виден только с ролью агента или супервайзера.\n"
                      "На скриншоте роль: **Employee** — поэтому раздела нет.\n\n"
                      "Что сделать:\n"
                      "1. Напишите своему супервайзеру — он запросит для вас роль агента.\n"
                      "2. Привяжите Telegram к PRBC (если в профиле Telegram «—», он не привязан).\n"
                      "3. После выдачи роли откройте PRBC заново — появится раздел «Новый клиент»."),
    },
    {
        "title": "PRBC → 1C: klient 1C'da allaqachon bor",
        "triggers": ["1c da allaqachon bor", "allaqachon bor edi", "mavjudini qaytardi", "уже существует в 1с",
                     "yangisi yaratilmadi"],
        "extract": [r"(?:nuqta kodi|код точки)\D{0,20}(?P<kod>UZ-\d{5,})", r"(?P<kod>UZ-\d{6,})"],
        "answer": ("Bu klient 1C'da avvaldan bor — yangisi ochilmadi, mavjud nuqta qaytarildi.\n"
                   "1C'dagi nuqta kodi: **{kod}**\n\n"
                   "Agar marshrutda «Kunlarsiz» yoki «Boshqa bo'linma» deb chiqqan bo'lsa — nuqta boshqa agent/bo'linma "
                   "marshrutida yoki tashrif kunlari qo'yilmagan. Supervayzeringiz uni sizning marshrutingizga o'tkazib, "
                   "tashrif kunlarini belgilashi kerak."),
        "answer_ru": ("Этот клиент уже есть в 1С — новый не создан, вернулась существующая точка.\n"
                      "Код точки в 1С: **{kod}**\n\n"
                      "Если в маршруте указано «Без дней» или «Другое подразделение» — точка в маршруте другого "
                      "агента/подразделения или не заданы дни визита. Супервайзер должен перевести её в ваш маршрут и "
                      "назначить дни визита."),
    },
    {
        "title": "ProTarget: yangi nuqta moderatsiyaga yuborilgan",
        "triggers": ["на модерацию", "отправлена на модерацию", "moderatsiyaga", "moderatsiya"],
        "extract": [r"Торговая точка\s*[\"«“](?P<nom>[^\"»”\n]{3,80})"],
        "answer": ("Nuqta ProTarget'da moderatsiyaga yuborilgan — bu normal holat.\n"
                   "Nuqta: **{nom}**\n\n"
                   "Moderatsiyadan o'tgach, shu nuqtaga buyurtma qilish mumkin bo'ladi. Uzoq vaqt tasdiqlanmasa — "
                   "Pro-target jamoasiga yozing."),
        "answer_ru": ("Точка отправлена на модерацию в ProTarget — это нормально.\n"
                      "Точка: **{nom}**\n\n"
                      "После модерации по точке можно будет делать заказы. Если долго не подтверждают — "
                      "напишите команде Pro-target."),
    },
]


class Command(BaseCommand):
    help = "Support bot: namunaviy shablonlar va (ixtiyoriy) muhit o'zgaruvchisidagi token bilan bot qo'shish."

    def add_arguments(self, parser):
        parser.add_argument("--token-env", default="", help="Bot tokeni turgan muhit o'zgaruvchisi nomi")
        parser.add_argument("--name", default="Support bot")

    def handle(self, *args, **opts):
        for row in SEED:
            e, created = Entry.objects.get_or_create(
                title=row["title"], kind=Entry.TEMPLATE,
                defaults={**{k: v for k, v in row.items() if k != "title"}, "status": Entry.REVIEW, "source": "seed",
                          "author": "seed", "questions": []})
            if opts["verbosity"]:
                self.stdout.write(f"shablon: {e.title} — {'qoʻshildi' if created else 'bor, tegilmadi'}")

        env = opts["token_env"]
        if env:
            token = os.environ.get(env, "").strip()
            if not token or ":" not in token:
                raise CommandError(f"{env} muhit o'zgaruvchisida token yo'q")
            for b in Bot.objects.all():
                if decrypt(b.token_enc) == token:
                    self.stdout.write(f"bot: {b} — bor, tegilmadi")
                    return
            b = Bot.objects.create(name=opts["name"], token_enc=encrypt(token), enabled=True, mode=MODE_SHADOW)
            self.stdout.write(f"bot qoʻshildi: #{b.id} {b.name} (soya rejimi)")
