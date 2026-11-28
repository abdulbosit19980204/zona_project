"""PRBC orqali yangi nuqta qo'shish — alohida toifa (prbc_outlet, IT support); ProTarget podklyucheniyesi — client/visit."""
from django.test import SimpleTestCase

from . import systems


class PrbcOutletCategoryTests(SimpleTestCase):
    def test_prbc_new_outlet_phrases(self):
        # guruhlardagi haqiqiy savollar (eval 28.11): ularga IT support / Xusniddin javob bergan
        for text in ["Salom aleykum\nSamarqand SR 4 magazin dabavit qilolmayapmiz",
                     "Tochka kushilmayabdi kurib bering",
                     "PRBC ichida yangi torgoviy tochka koshaolmayabman",
                     "Не могу открыть новую точку ее нет в базе 1с",
                     "новая точка не добавляется",
                     "E-Navoi SR1 не получается добавить точку"]:
            self.assertEqual(systems.detect(text)["category"], "prbc_outlet", text)

    def test_prbc_screens(self):
        for ocr in ["PRBC  Заявки на точки  + Новая заявка  ИНН/ПИНФЛ",
                    "мини-приложение ПИНФЛ Этот ИНН/ПИНФЛ уже есть в 1C как контрагент"]:
            self.assertEqual(systems.detect("", ocr)["category"], "prbc_outlet", ocr)

    def test_protarget_stays_with_protarget(self):
        for text, cat in [("Ассалому алайкум. Хозир шу дуконни добавить килдим подключенияда чикмаябди", "client"),
                          ("Подключение сделала можете подтвердить", "client"),
                          ("Patkluchenya bomayapti", "client"),
                          ("Не могу сделать визит. Локация в программе указана неправильно", "visit"),
                          ("aksiya ishlamayapti", "promo")]:
            self.assertEqual(systems.detect(text)["category"], cat, text)

    def test_success_screen_is_not_new_outlet(self):
        # «✅ Торговая точка создана в 1С … Код: UZ-00069329» + «Qoshvorila» — nuqta 1C/PRBC'da bor: Xusniddin emas,
        # jonli PRBC holati va ProTarget (client) yo'li (28.11, xabar 28545)
        for text, ocr in [("Qoshvorila", "PRBC ✅ Торговая точка создана в 1С Код: UZ-00069329 Маршрут"),
                          ("", "PRBC Созданав1С G'ULOMJONOV NIZOMIDDIN")]:
            r = systems.detect(text, ocr)
            self.assertNotEqual(r["category"], "prbc_outlet", ocr)
        self.assertEqual(systems.detect("Qoshvorila", "✅ Торговая точка создана в 1С Код: UZ-00069329")["category"],
                         "client")

    def test_prbc_request_status_is_moderation(self):
        # zayavka "Ожидает проверки / Черновик / Отклонена" — ProTarget moderatsiyasi (Eldar javob bergan)
        r = systems.detect("Buyam qo'shilmadimi", "PRBC Заявки на точки 47 Черновик Ожидает проверки Отклонена 1")
        self.assertNotEqual(r["category"], "prbc_outlet")

    def test_app_slow_is_sync(self):
        for text in ["Sr.1 bukhara программа секин ишлаяпти куриб беринг", "приложение долго грузит",
                     "Protarget ishlamayapti"]:
            self.assertEqual(systems.detect(text)["category"], "sync", text)

    def test_company_name_is_not_payment(self):
        # «MAS'ULIYATI CHEKLANGAN JAMIYAT» — korxona shakli, «chek» emas (28.11: savol Saidabror'ga ketgan)
        ocr = ("Торговая точка уже есть в 1C: 67\"ASSORTI DISCOUNT MARKET\" MAS'ULIYATI CHEKLANGAN JAMIYAT "
               "DMS вернула существующую точку. Новая точка не создана.")
        self.assertNotEqual(systems.detect("1C bosa nega Protargetda korinmayapti", ocr)["category"], "payment")
        self.assertEqual(systems.detect("chek chiqmayapti")["category"], "payment")
        self.assertEqual(systems.detect("Не выходит безнал")["category"], "payment")

    def test_category_listed(self):
        self.assertIn("prbc_outlet", systems.CATEGORIES)
        self.assertLessEqual(len("prbc_outlet"), 12)  # Message.category max_length
