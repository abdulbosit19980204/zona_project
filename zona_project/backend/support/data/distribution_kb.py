"""Distributsiya to'plami: agent va supervayzerlarning savdo bo'yicha kundalik savollari (StarGroup distributsiyasi).

Javoblarda kompaniyaga xos raqam (minimal summa, muddat, KPI formulasi) o'ylab topilmagan — ular supervayzer
yoki mas'ulga yo'naltiriladi. Hammasi "ko'rib chiqilmoqda" holatida qo'shiladi: xodimlar aniqlashtirib tasdiqlaydi.
Har bir yozuv: title, questions (uz/ru, agentlar so'zlashuvi bilan), answer, answer_ru, who (Member nomi), zone.
"""

SUP, OP, PT, IT, DEV = "Supervayzerlar", "Saidabror", "Pro-target", "Xusniddin", "Dasturchilar jamoasi"
DIST, PTZ, REP = "Distributsiya", "ProTarget va mobil ilova", "Hisobot va tahlil"

PACK = [
    # ------------------------------------------------------------ savdo va plan (agent)
    dict(title="Planni qanday bajarsam bo'ladi — savdoni oshirish yo'llari",
         questions=["plan bajarilmayapti nima qilay", "savdoni qanday oshiraman", "prodajani ko'paytirish kerak",
                    "plan qolib ketyapti", "как выполнить план", "как увеличить продажи", "продажи упали что делать"],
         answer=("Savdoni oshirishning asosiy yo'llari:\n"
                 "1. **AKB** — marshrutdagi har bir nuqtadan har oy kamida bitta zakaz oling (zakaz bermayotganlarini ro'yxatdan toping).\n"
                 "2. **SKU** — har nuqtada assortimentni kengaytiring: nuqtada yo'q, lekin sotiladigan tovarlarni taklif qiling.\n"
                 "3. **Aksiyalar** — amaldagi aksiyalarni har tashrifda eslating, klientga foydasini hisoblab ko'rsating.\n"
                 "4. **Tashrif sifati** — polka va qoldiqni tekshiring, tugayotgan tovarni oldindan zakaz qiling.\n"
                 "5. **Yangi nuqtalar** — hududdagi bizda yo'q do'konlarni yangi klient sifatida oching.\n"
                 "Qaysi ko'rsatkich bo'yicha orqada qolayotganingizni supervayzeringiz bilan haftalik ko'rib chiqing."),
         answer_ru=("Основные способы увеличить продажи:\n"
                    "1. **АКБ** — берите заказ с каждой точки маршрута хотя бы раз в месяц (найдите точки без заказов).\n"
                    "2. **SKU** — расширяйте ассортимент в каждой точке: предлагайте товары, которых там нет, но они продаются.\n"
                    "3. **Акции** — напоминайте о действующих акциях на каждом визите, считайте выгоду клиента.\n"
                    "4. **Качество визита** — проверяйте полку и остатки, заказывайте заканчивающийся товар заранее.\n"
                    "5. **Новые точки** — открывайте магазины района, где нас ещё нет.\n"
                    "Отставание по показателям разбирайте с супервайзером еженедельно."),
         who=SUP, zone=DIST),
    dict(title="Plan bajarilishini qayerdan ko'raman",
         questions=["planim qancha bajarildi", "plan foizini qayerdan ko'raman", "bugungi savdom qancha",
                    "plan bajarilishi ko'rinmayapti", "где посмотреть выполнение плана", "сколько я выполнил плана"],
         answer=("Plan va bajarilish ProTarget ilovasida ko'rinadi (plan/hisobot bo'limi). Ma'lumot sinxronlashdan keyin yangilanadi — "
                 "avval sinxronlashni bosing.\nRaqam noto'g'ri ko'rinsa yoki plan umuman chiqmasa — supervayzeringizga yozing: "
                 "plan supervayzer tomonidan kiritiladi."),
         answer_ru=("План и выполнение видны в приложении ProTarget (раздел плана/отчётов). Данные обновляются после синхронизации — "
                    "сначала нажмите синхронизацию.\nЕсли цифры неверные или плана нет — напишите супервайзеру: план вносит он."),
         who=SUP, zone=DIST),
    dict(title="AKB nima va uni qanday oshirish mumkin",
         questions=["akb nima", "akb qanday hisoblanadi", "akb past", "aktiv klient bazasi", "что такое акб",
                    "как поднять акб", "акб низкий"],
         answer=("**AKB (aktiv klient bazasi)** — tanlangan davrda (odatda bir oyda) kamida bitta zakaz bergan nuqtalar soni.\n"
                 "Oshirish uchun:\n1. Marshrutingizdagi shu oy zakaz bermagan nuqtalar ro'yxatini oling.\n"
                 "2. Har biriga tashrifda kichik bo'lsa ham zakaz taklif qiling (aksiyadagi yoki tez sotiladigan tovar).\n"
                 "3. Yopilgan yoki ishlamayotgan nuqtalarni supervayzerga ayting — ular marshrutdan olib tashlanadi.\n"
                 "AKB rejasi va hisoblash qoidasini supervayzeringiz aytadi."),
         answer_ru=("**АКБ (активная клиентская база)** — число точек, сделавших хотя бы один заказ за период (обычно месяц).\n"
                    "Как поднять:\n1. Возьмите список точек маршрута без заказа в этом месяце.\n"
                    "2. На визите предложите хотя бы небольшой заказ (акционный или ходовой товар).\n"
                    "3. О закрытых/неработающих точках сообщите супервайзеру — их уберут из маршрута.\n"
                    "План по АКБ и правило расчёта уточняйте у супервайзера."),
         who=SUP, zone=DIST),
    dict(title="SKU (assortiment) bo'yicha planni bajarish",
         questions=["sku plan", "assortiment kam", "har nuqtada nechta sku bo'lishi kerak", "tovar turini ko'paytirish",
                    "план по sku", "как увеличить ассортимент в точке", "дистрибуция sku"],
         answer=("SKU planini bajarish uchun har nuqtada qaysi tovarlar yo'qligini aniqlang va ularni taklif qiling:\n"
                 "1. Nuqtadagi polka va zakaz tarixini solishtiring.\n2. Kompaniyaning majburiy (asosiy) assortimentidan "
                 "yetishmayotganini birinchi taklif qiling.\n3. Yangi tovarni kichik miqdorda sinab ko'rishni taklif qiling.\n"
                 "Majburiy assortiment ro'yxati va SKU rejasi — supervayzeringizda."),
         answer_ru=("Чтобы выполнить план по SKU, определите, каких товаров нет в точке, и предложите их:\n"
                    "1. Сравните полку и историю заказов точки.\n2. Сначала предлагайте недостающее из обязательного ассортимента.\n"
                    "3. Новый товар предложите взять на пробу небольшим количеством.\n"
                    "Список обязательного ассортимента и план по SKU — у супервайзера."),
         who=SUP, zone=DIST),
    dict(title="Klient zakaz bermayapti yoki savdo kamaydi",
         questions=["klient zakaz bermay qo'ydi", "magazin olmayapti", "klient boshqa firmadan olyapti", "klient yo'qolib qoldi",
                    "клиент перестал брать", "клиент не заказывает", "клиент ушёл к конкурентам"],
         answer=("Avval sababini aniqlang: narx, aksiya, qarz/limit, yetkazishdagi muammo, sifat yoki raqobatchi.\n"
                 "1. Narx/aksiya bo'lsa — amaldagi aksiyalarni ko'rsating, kerak bo'lsa supervayzer orqali maxsus shart so'rang.\n"
                 "2. Qarz yoki limit bo'lsa — to'lov masalasini hal qiling (supervayzer bilan).\n"
                 "3. Yetkazish yoki sifat muammosi bo'lsa — aniq misol bilan supervayzerga yozing.\n"
                 "4. Raqobatchi faol bo'lsa — narxi va aksiyasini yozib, supervayzerga xabar bering."),
         answer_ru=("Сначала выясните причину: цена, акция, долг/лимит, проблема с доставкой, качество или конкурент.\n"
                    "1. Цена/акция — покажите действующие акции, при необходимости запросите спецусловия через супервайзера.\n"
                    "2. Долг или лимит — решите вопрос оплаты (с супервайзером).\n"
                    "3. Доставка или качество — напишите супервайзеру с конкретным примером.\n"
                    "4. Активен конкурент — запишите его цены и акции и сообщите супервайзеру."),
         who=SUP, zone=DIST),
    dict(title="Raqobatchi faoliyati haqida xabar berish",
         questions=["raqobatchi aksiya qilyapti", "konkurent arzon beryapti", "boshqa firma narxi past",
                    "конкурент демпингует", "у конкурента акция", "конкуренты дешевле"],
         answer=("Raqobatchi ma'lumotini supervayzeringizga yuboring: firma/brend, tovar, narx, aksiya sharti, qaysi nuqtalarda, "
                 "iloji bo'lsa polka yoki narx yorlig'i rasmi. Bu ma'lumot narx va aksiya qarorlari uchun kerak."),
         answer_ru=("Отправьте супервайзеру данные о конкуренте: фирма/бренд, товар, цена, условия акции, в каких точках, "
                    "по возможности фото полки или ценника. Это нужно для решений по ценам и акциям."),
         who=SUP, zone=DIST),
    dict(title="Yangi tovar (novinka) ni qanday sotish kerak",
         questions=["yangi tovar keldi qanday sotaman", "novinka chiqdi", "yangi mahsulotni klientga qanday taklif qilaman",
                    "как продавать новинку", "новый товар как предложить"],
         answer=("Yangi tovarni sotish:\n1. Tovar haqida asosiy ma'lumotni biling: kimga mo'ljallangan, narxi, ustunligi.\n"
                 "2. Avval eng faol klientlaringizga sinov uchun kichik miqdorda taklif qiling.\n"
                 "3. Polkada ko'rinadigan joyga qo'yishni so'rang.\n4. Kirish aksiyasi bo'lsa — albatta ayting.\n"
                 "Taqdimot materiallari va kirish aksiyasi bo'yicha supervayzeringizdan so'rang."),
         answer_ru=("Как продавать новинку:\n1. Знайте главное о товаре: для кого, цена, преимущество.\n"
                    "2. Сначала предложите активным клиентам небольшую пробную партию.\n"
                    "3. Попросите выставить на видное место на полке.\n4. Если есть вводная акция — обязательно скажите.\n"
                    "Материалы и вводную акцию уточните у супервайзера."),
         who=SUP, zone=DIST),
    dict(title="Agent bonusi va KPI qanday hisoblanadi",
         questions=["bonusim qancha", "kpi qanday hisoblanadi", "oylik bonus", "premiya qachon", "zarplata bonus",
                    "как считается бонус", "kpi агента", "когда премия"],
         answer=("Bonus va KPI hisoblash qoidasi (qaysi ko'rsatkichlar, ulushlari, plan foizi) supervayzeringizda va oylik nizomda. "
                 "Hisobingiz bo'yicha savol bo'lsa — supervayzerga aniq oy va ko'rsatkichni yozing; tizimdagi raqam noto'g'ri bo'lsa, "
                 "u tekshirib beradi."),
         answer_ru=("Правила расчёта бонуса и KPI (показатели, веса, процент плана) — у супервайзера и в положении за месяц. "
                    "Вопросы по своему расчёту пишите супервайзеру с месяцем и показателем; если цифра в системе неверная — он проверит."),
         who=SUP, zone=DIST),

    # ------------------------------------------------------------ zakaz va yetkazish
    dict(title="Zakaz qachon yetkaziladi (otgruzka vaqti)",
         questions=["zakaz qachon keladi", "tovar qachon yetib boradi", "otgruzka qachon", "dostavka qachon",
                    "когда привезут заказ", "когда отгрузка", "когда доставка"],
         answer=("Zakaz odatda tasdiqlangandan keyin yetkazish jadvali bo'yicha olib boriladi. Aniq kun va vaqt hudud va "
                 "yetkazish grafikiga bog'liq — supervayzeringiz aytadi.\nZakaz kechikkan bo'lsa: zakaz raqami, klient va sanani "
                 "supervayzerga yozing."),
         answer_ru=("Заказ доставляется по графику доставки после подтверждения. Точный день и время зависят от района и графика — "
                    "уточните у супервайзера.\nЕсли заказ задерживается — напишите супервайзеру номер заказа, клиента и дату."),
         who=SUP, zone=DIST),
    dict(title="Zakaz yetkazilmadi yoki to'liq kelmadi (nedovoz)",
         questions=["zakaz kelmadi", "tovar to'liq kelmadi", "nedovoz", "kam tovar keldi", "boshqa tovar keldi", "nedovoz bo'ldi", "karobka kam keldi", "tovar kam keldi",
                    "заказ не привезли", "недовоз", "привезли не тот товар"],
         answer=("Zakaz raqami, klient, qaysi tovar va qancha yetmagani (yoki noto'g'ri kelgani) bilan supervayzeringizga yozing, "
                 "iloji bo'lsa yuk xati (nakladnoy) rasmini qo'shing. Supervayzer ombor va logistika bilan aniqlaydi; "
                 "hujjatni tuzatish kerak bo'lsa operator tuzatadi."),
         answer_ru=("Напишите супервайзеру номер заказа, клиента, какого товара и сколько не хватило (или что привезли не то), "
                    "по возможности фото накладной. Супервайзер выяснит со складом и логистикой; документ при необходимости исправит оператор."),
         who=SUP, zone=DIST),
    dict(title="Tovar omborda yo'q (qoldiq tugagan)",
         questions=["tovar yo'q omborda", "ostatka yo'q", "qoldiq nol", "tovar tugab qolgan qachon keladi",
                    "нет остатка", "товара нет на складе", "когда будет товар"],
         answer=("Ilovada qoldiq nol bo'lsa, tovarni zakaz qilib bo'lmaydi. Qachon kelishini supervayzeringizdan so'rang — "
                 "u ta'minot bo'limidan aniqlaydi. Klientga o'xshash tovar (muqobil) taklif qiling.\n"
                 "Tovar omborda bor, lekin ilovada ko'rinmasa — sinxronlang; baribir chiqmasa operatorga yozing."),
         answer_ru=("Если в приложении остаток ноль, товар заказать нельзя. Когда поступит — спросите у супервайзера, он уточнит у снабжения. "
                    "Предложите клиенту аналог.\nЕсли товар на складе есть, но в приложении не виден — синхронизируйтесь; если не помогло — "
                    "напишите оператору."),
         who=SUP, zone=DIST),
    dict(title="Minimal zakaz summasi",
         questions=["minimal zakaz qancha", "kam summaga zakaz o'tmayapti", "eng kam summa", "минимальная сумма заказа",
                    "маленький заказ не проходит"],
         answer=("Minimal zakaz summasi kanal va hududga qarab belgilanadi — aniq miqdorni supervayzeringiz aytadi. "
                 "Summa yetmasa, klientga aksiyadagi yoki tez sotiladigan tovar qo'shishni taklif qiling."),
         answer_ru=("Минимальная сумма заказа зависит от канала и района — точную сумму скажет супервайзер. "
                    "Если не хватает — предложите добавить акционный или ходовой товар."),
         who=SUP, zone=DIST),
    dict(title="Zakazga izoh yoki yetkazish vaqtini qo'shish",
         questions=["zakazga izoh yozish", "kuryerga izoh", "ertalab olib kelishsin", "kommentariy zakazga",
                    "комментарий к заказу", "привезти утром"],
         answer=("Zakazni yuborishdan oldin ilovada izoh (kommentariy) maydoniga yozing: yetkazish vaqti, mo'ljal, kontakt. "
                 "Zakaz allaqachon yuborilgan bo'lsa — supervayzerga zakaz raqami va izohni yozing."),
         answer_ru=("Перед отправкой заказа укажите комментарий в приложении: время доставки, ориентир, контакт. "
                    "Если заказ уже отправлен — напишите супервайзеру номер заказа и комментарий."),
         who=SUP, zone=DIST),

    # ------------------------------------------------------------ to'lov, qarz, limit
    dict(title="Klientning qarzi (debitorka) qancha",
         questions=["klient qarzi qancha", "dolg qancha", "debitorka", "klientning to'lanmagan summasi", "долг клиента",
                    "сколько должен клиент", "дебиторка"],
         answer=("Klient qarzini ProTarget ilovasida klient kartochkasidan ko'ring (sinxronlashdan keyin). "
                 "Batafsil ro'yxat yoki akt sverka kerak bo'lsa — operatorga klient nomi/STIR bilan yozing."),
         answer_ru=("Долг клиента смотрите в карточке клиента в ProTarget (после синхронизации). "
                    "Нужен подробный список или акт сверки — напишите оператору с названием/ИНН клиента."),
         who=OP, zone=DIST),
    dict(title="Qarz sababli zakaz o'tmayapti (kredit limiti)",
         questions=["limit tugagan zakaz o'tmayapti", "qarz bor deb zakaz qabul qilmayapti", "kredit limit",
                    "просрочка не даёт заказ", "лимит превышен", "заказ блокирован долгом"],
         answer=("Klientda muddati o'tgan qarz yoki limitdan oshish bo'lsa, zakaz bloklanadi.\n"
                 "1. Klientdan to'lovni oling (yoki to'lov sanasini aniqlang).\n"
                 "2. Limitni oshirish yoki muddatni uzaytirish kerak bo'lsa — supervayzer tasdiqlaydi.\n"
                 "To'lov qilingan, lekin qarz hali ko'rinsa — operatorga to'lov sanasi va summasini yozing."),
         answer_ru=("При просроченном долге или превышении лимита заказ блокируется.\n"
                    "1. Получите оплату от клиента (или уточните дату оплаты).\n"
                    "2. Увеличение лимита или отсрочку утверждает супервайзер.\n"
                    "Если оплата прошла, а долг ещё виден — напишите оператору дату и сумму оплаты."),
         who=SUP, zone=DIST),
    dict(title="Klient to'lov qildi, lekin qarz kamaymadi",
         questions=["pul to'ladi lekin qarz turibdi", "oplata tushmadi", "to'lov ko'rinmayapti", "оплата не отразилась",
                    "клиент оплатил а долг висит"],
         answer=("Operatorga yozing: klient, to'lov sanasi, summa, to'lov turi (naqd/perechisleniye), iloji bo'lsa kvitansiya rasmi. "
                 "Bank orqali to'lovlar kechikib tushishi mumkin; operator tekshirib, to'lovni to'g'ri klientga biriktiradi."),
         answer_ru=("Напишите оператору: клиент, дата оплаты, сумма, способ (наличные/перечисление), по возможности фото квитанции. "
                    "Банковские платежи могут приходить с задержкой; оператор проверит и привяжет оплату к нужному клиенту."),
         who=OP, zone=DIST),
    dict(title="Akt sverka (o'zaro hisob-kitob dalolatnomasi) kerak",
         questions=["akt sverka kerak", "sverka qilish", "klient bilan hisob solishtirish", "акт сверки нужен", "сверка с клиентом"],
         answer=("Operatorga yozing: klient nomi va STIR, davr (qaysi sanadan qaysi sanagacha). Operator 1C'dan akt sverkani "
                 "tayyorlab yuboradi."),
         answer_ru=("Напишите оператору: название клиента и ИНН, период (с какой по какую дату). Оператор подготовит акт сверки из 1С."),
         who=OP, zone=REP),
    dict(title="Elektron hisob-faktura (e-faktura) kelmadi yoki xato",
         questions=["faktura kelmadi", "e-faktura xato", "schet faktura", "didox faktura", "электронная фактура не пришла",
                    "счёт-фактура ошибка"],
         answer=("Klient nomi/STIR, yuk xati raqami va sanasini operatorga yozing. Faktura umuman yuborilmagan bo'lsa yoki "
                 "tizim xatosi bo'lsa, operator dasturchilarga uzatadi."),
         answer_ru=("Напишите оператору название/ИНН клиента, номер и дату накладной. Если фактура не отправилась из-за системной ошибки — "
                    "оператор передаст программистам."),
         who=OP, zone=DIST),

    # ------------------------------------------------------------ vozvrat, srok
    dict(title="Muddati o'tgan yoki yaroqsiz tovarni qaytarish",
         questions=["srok o'tgan tovar", "muddati o'tdi qaytarish", "brak tovar", "yaroqsiz tovar qaytarish", "просрочка возврат",
                    "брак вернуть", "истёк срок годности"],
         answer=("Qaytarish (vozvrat) supervayzer tasdig'i bilan qilinadi:\n1. Tovar nomi, miqdori, sababi (srok/brak) va rasmini "
                 "supervayzerga yuboring.\n2. Supervayzer tasdiqlaydi.\n3. Operator vozvrat hujjatini kiritadi.\n"
                 "Qaysi tovarlar qanday shartda qaytarilishi — supervayzerdan aniqlang."),
         answer_ru=("Возврат делается с подтверждения супервайзера:\n1. Отправьте супервайзеру товар, количество, причину (срок/брак) и фото.\n"
                    "2. Супервайзер подтверждает.\n3. Оператор вносит документ возврата.\n"
                    "Какие товары и на каких условиях возвращаются — уточните у супервайзера."),
         who=SUP, zone=DIST),
    dict(title="Srok yaqinlashayotgan tovarni sotish",
         questions=["srok tugayapti nima qilaman", "muddati yaqin tovar", "срок подходит", "товар с коротким сроком"],
         answer=("Muddati yaqin tovarni birinchi navbatda soting (polkada oldinga qo'ying — FIFO). Ko'p qolgan bo'lsa, "
                 "supervayzerga xabar bering: aksiya yoki boshqa nuqtaga o'tkazish bo'yicha qaror qabul qilinadi."),
         answer_ru=("Товар с подходящим сроком продавайте в первую очередь (ставьте вперёд на полке — FIFO). Если его много — "
                    "сообщите супервайзеру: решат по акции или перемещению в другие точки."),
         who=SUP, zone=DIST),

    # ------------------------------------------------------------ narx va aksiya
    dict(title="Joriy aksiyalar ro'yxati qayerda",
         questions=["qanaqa aksiyalar bor", "hozir qaysi aksiya", "aksiya ro'yxati", "skidkalar qanaqa",
                    "какие сейчас акции", "список акций", "действующие скидки"],
         answer=("Amaldagi aksiyalar ProTarget ilovasida zakaz berishda va aksiya bo'limida ko'rinadi (sinxronlashdan keyin). "
                 "Aksiya shartlari tushunarsiz bo'lsa — supervayzeringiz tushuntiradi; aksiya ilovada ko'rinmasa — supervayzer "
                 "tekshiradi, keyin operatorga yoki Pro-target'ga uzatadi."),
         answer_ru=("Действующие акции видны в ProTarget при оформлении заказа и в разделе акций (после синхронизации). "
                    "Условия непонятны — объяснит супервайзер; акция не видна — супервайзер проверит и передаст оператору или Pro-target."),
         who=SUP, zone=DIST),
    dict(title="Klient chegirma yoki maxsus narx so'rayapti",
         questions=["klient skidka so'rayapti", "arzonroq bering deyapti", "maxsus narx kerak", "клиент просит скидку",
                    "нужна спеццена"],
         answer=("Agent o'zi chegirma bera olmaydi. Klient, tovar, so'ralgan narx/chegirma va asosni (hajm, raqobatchi narxi) "
                 "supervayzerga yozing. Supervayzer tasdiqlasa, operator klientga biriktiradi."),
         answer_ru=("Агент сам скидку дать не может. Напишите супервайзеру клиента, товар, запрошенную цену/скидку и обоснование "
                    "(объём, цена конкурента). После подтверждения оператор привяжет условия к клиенту."),
         who=SUP, zone=DIST),
    dict(title="Narx o'zgardi — yangi narxlar qachon kuchga kiradi",
         questions=["narx oshdi", "yangi narx qachondan", "prays o'zgardi", "price list", "цены поменялись", "новый прайс"],
         answer=("Narx o'zgarishi haqida supervayzer xabar beradi; yangi narxlar ilovaga sinxronlashdan keyin tushadi. "
                 "Ilovadagi narx e'lon qilinganidan farq qilsa — supervayzerga tovar va ikkala narxni yozing."),
         answer_ru=("Об изменении цен сообщает супервайзер; новые цены появляются в приложении после синхронизации. "
                    "Если цена в приложении отличается от объявленной — напишите супервайзеру товар и обе цены."),
         who=SUP, zone=DIST),
    dict(title="Aksiya bonusi yoki sovg'a klientga berilmadi",
         questions=["bonus tovar kelmadi", "aksiya sovg'asi berilmadi", "bepul tovar qo'shilmadi", "бонус не пришёл",
                    "подарок по акции не дали"],
         answer=("Zakaz raqami, klient va aksiya nomini supervayzerga yozing. Aksiya zakazda qo'llanmagan bo'lsa — operator tekshiradi; "
                 "aksiya hisobi ProTarget tomonda bo'lsa — Pro-target jamoasi aniqlaydi."),
         answer_ru=("Напишите супервайзеру номер заказа, клиента и название акции. Если акция не применилась в заказе — проверит оператор; "
                    "если расчёт на стороне ProTarget — команда Pro-target."),
         who=SUP, zone=DIST),

    # ------------------------------------------------------------ merchandayzing va tashrif
    dict(title="Polka va merchandayzing standarti",
         questions=["polkani qanday terish kerak", "merchandayzing standarti", "planogramma", "выкладка товара",
                    "планограмма", "стандарт мерчандайзинга"],
         answer=("Asosiy qoidalar: tovar ko'z darajasida va guruh bo'yicha bir joyda, yorliqlar oldinga, narx yorlig'i bor, "
                 "muddati yaqin tovar oldinda (FIFO), bo'sh joy qoldirmang.\nBrend bo'yicha aniq planogramma va foto-hisobot "
                 "talabi — supervayzer yoki merchandayzerda."),
         answer_ru=("Основные правила: товар на уровне глаз и сгруппирован, этикетки лицом, есть ценник, товар с ближайшим сроком впереди (FIFO), "
                    "без пустот.\nТочная планограмма по бренду и требования к фотоотчёту — у супервайзера или мерчендайзера."),
         who=SUP, zone=DIST),
    dict(title="Foto-hisobot yoki check-in o'tmayapti",
         questions=["foto yuklanmayapti", "check in bo'lmayapti", "tashrif yopilmayapti", "rasm yubormayapti",
                    "фото не загружается", "не могу начать визит", "чек-ин не проходит"],
         answer=("1. Geolokatsiya yoqilganini va nuqtaga yaqin turganingizni tekshiring.\n2. Internetni tekshirib, sinxronlang.\n"
                 "3. Ilovaga kamera va joylashuv ruxsati berilganini tekshiring.\nBaribir o'tmasa — xato rasmini IT yordamga (Xusniddin) yuboring."),
         answer_ru=("1. Проверьте, что включена геолокация и вы рядом с точкой.\n2. Проверьте интернет и синхронизируйтесь.\n"
                    "3. Проверьте разрешения приложения на камеру и геолокацию.\nНе помогло — отправьте скрин ошибки в IT-поддержку (Хусниддин)."),
         who=IT, zone=PTZ),
    dict(title="Nuqta joylashuvidan uzoqda deb tashrif qabul qilinmayapti",
         questions=["nuqtadan uzoqdasiz deyapti", "gps noto'g'ri", "lokatsiya mos emas", "вы далеко от точки",
                    "координаты точки неверные"],
         answer=("Nuqtaning xaritadagi koordinatasi noto'g'ri kiritilgan bo'lishi mumkin. Nuqta ichida turib joylashuvingizni "
                 "(skrinshot) va nuqta nomini supervayzerga yuboring — koordinata operator orqali tuzatiladi."),
         answer_ru=("Возможно, координаты точки внесены неверно. Находясь в точке, отправьте супервайзеру скрин геолокации и название точки — "
                    "координаты исправят через оператора."),
         who=SUP, zone=DIST),
    dict(title="Nuqta yopilgan yoki egasi almashgan",
         questions=["magazin yopildi", "tochka yopilgan", "do'kon egasi almashdi", "magazin boshqaga o'tdi", "точка закрылась",
                    "сменился владелец магазина", "магазин закрылся", "точка не работает", "do'kon ishlamayapti"],
         answer=("Supervayzerga nuqta nomi va holatini yozing. Yopilgan bo'lsa — nuqta marshrutdan olinadi va kartochka yopiladi; "
                 "egasi almashgan bo'lsa — yangi egasining hujjatlari (STIR) bilan kartochka yangilanadi yoki yangi klient ochiladi. "
                 "Qarz bo'lsa — avval qarz masalasi hal qilinadi."),
         answer_ru=("Напишите супервайзеру название точки и что случилось. Закрыта — точку уберут из маршрута и закроют карточку; "
                    "сменился владелец — карточку обновят по документам (ИНН) нового владельца или откроют нового клиента. "
                    "Если есть долг — сначала решается вопрос долга."),
         who=SUP, zone=DIST),
    dict(title="Kunlik tashrif normasi va ish tartibi",
         questions=["kuniga nechta nuqtaga borish kerak", "tashrif normasi", "ish vaqti qachon", "skolko vizitov v den",
                    "сколько точек в день", "норма визитов"],
         answer=("Kunlik tashrif soni marshrut jadvalingizda belgilangan. Ish tartibi va norma bo'yicha supervayzeringiz aytadi. "
                 "Tashrifni o'tkazib yubormang: borolmasangiz, supervayzerga oldindan xabar bering."),
         answer_ru=("Количество визитов в день задано в вашем маршруте. Режим и норму уточните у супервайзера. "
                    "Не пропускайте визиты: если не успеваете — предупредите супервайзера заранее."),
         who=SUP, zone=DIST),

    # ------------------------------------------------------------ brendlar
    dict(title="Brend bo'yicha savol (Heinz, BIC, J&J, L'Oréal)",
         questions=["heinz aksiyasi", "bic bo'yicha plan", "l'oreal tovarlari", "jj brend", "johnson tovar", "loreal",
                    "по бренду heinz", "акция bic", "план по l'oreal"],
         answer=("Brend bo'yicha plan, aksiya va assortiment savollari o'sha brend jamoasining supervayzeri yoki "
                 "menejeriga (ASM/RSM) beriladi. O'z supervayzeringiz kim ekanini bilmasangiz — platformadagi «Kontaktlar» "
                 "bo'limidan brend jamoasini toping."),
         answer_ru=("Вопросы по плану, акциям и ассортименту бренда — к супервайзеру или менеджеру (ASM/RSM) команды этого бренда. "
                    "Если не знаете своего супервайзера — найдите команду бренда в разделе «Контакты» платформы."),
         who=SUP, zone=DIST),

    # ------------------------------------------------------------ supervayzer savollari
    dict(title="Supervayzer: jamoa savdosini va agentlar natijasini ko'rish",
         questions=["agentlarimning savdosini qayerdan ko'raman", "jamoa hisoboti", "agentlar bo'yicha plan",
                    "как посмотреть продажи моих агентов", "отчёт по команде", "выполнение плана по агентам"],
         answer=("Jamoa bo'yicha savdo va plan bajarilishi ProTarget hisobotlarida (supervayzer huquqi bilan) ko'rinadi. "
                 "Hisobotda agentlaringiz ko'rinmasa — huquq masalasi, IT yordamga (Xusniddin) yozing. Excel ko'rinishida kerak "
                 "bo'lsa — operator chiqarib beradi."),
         answer_ru=("Продажи и выполнение плана по команде видны в отчётах ProTarget (с правами супервайзера). "
                    "Если агенты не видны — это вопрос прав, напишите в IT-поддержку (Хусниддин). Нужен Excel — выгрузит оператор."),
         who=IT, zone=REP),
    dict(title="Supervayzer: orqada qolayotgan agent bilan ishlash",
         questions=["agent plan bajarmayapti nima qilay", "kuchsiz agent", "agentni qanday o'rgataman", "агент не выполняет план",
                    "как работать с отстающим агентом"],
         answer=("Tavsiya etiladigan tartib:\n1. Ko'rsatkichlarni ajrating: AKB, SKU, o'rtacha zakaz, tashrif bajarilishi — qaysi biri past.\n"
                 "2. Agent bilan birga marshrutga chiqing (tashrif sifati, taklif qilish, polka).\n"
                 "3. Haftalik aniq maqsad qo'ying (masalan, zakaz bermayotgan 10 nuqtani faollashtirish) va natijani tekshiring.\n"
                 "4. Muammo tizimda bo'lsa (narx, qoldiq, aksiya) — mas'ulga uzating."),
         answer_ru=("Рекомендуемый порядок:\n1. Разложите показатели: АКБ, SKU, средний заказ, выполнение визитов — что проседает.\n"
                    "2. Выйдите с агентом на маршрут (качество визита, предложение, полка).\n"
                    "3. Поставьте конкретную недельную цель (например, активировать 10 точек без заказов) и проверьте результат.\n"
                    "4. Если проблема в системе (цена, остаток, акция) — передайте ответственному."),
         who=SUP, zone=DIST),
    dict(title="Supervayzer: agentlar o'rtasida marshrut yoki klientlarni qayta taqsimlash",
         questions=["marshrutlarni qayta bo'lish", "agent ketdi klientlarini kimga beraman", "hududni bo'lish",
                    "перераспределить клиентов", "агент уволился кому отдать клиентов"],
         answer=("Klient va nuqtalarni boshqa agentga o'tkazish supervayzer tomonidan qilinadi (ProTarget'da marshrut). "
                 "Ko'p klientni birdan o'tkazish kerak bo'lsa — ro'yxatni (Excel: klient, eski agent, yangi agent) operatorga yuboring. "
                 "Ketgan agent profilini yopish uchun IT yordamga xabar bering."),
         answer_ru=("Передачу клиентов и точек другому агенту делает супервайзер (маршрут в ProTarget). "
                    "Если нужно перенести много клиентов — отправьте оператору список (Excel: клиент, старый агент, новый агент). "
                    "Чтобы закрыть профиль уволенного агента — сообщите в IT-поддержку."),
         who=SUP, zone=DIST),
    dict(title="Supervayzer: yangi agentni ishga tushirish",
         questions=["yangi agent keldi nima qilish kerak", "yangi agentga dostup", "новый агент что сделать", "доступ новому агенту"],
         answer=("Yangi agent uchun:\n1. IT yordamga (Xusniddin) ism, telefon, hudud va filialni yozing — ProTarget va kerakli dostuplar ochiladi.\n"
                 "2. Marshrut va klientlarni biriktiring.\n3. Planni kiriting.\n4. Birinchi kunlarda u bilan birga marshrutga chiqing.\n"
                 "Telefon sozlash bo'yicha — Jahongir."),
         answer_ru=("Для нового агента:\n1. Напишите в IT-поддержку (Хусниддин) ФИО, телефон, район и филиал — откроют ProTarget и доступы.\n"
                    "2. Назначьте маршрут и клиентов.\n3. Внесите план.\n4. В первые дни выйдите с ним на маршрут.\n"
                    "Настройка телефона — Жахонгир."),
         who=SUP, zone=DIST),
    dict(title="Supervayzer: zakaz bermayotgan (nofaol) klientlar ro'yxati",
         questions=["zakaz bermagan klientlar", "nofaol klientlar ro'yxati", "akbga kirmagan nuqtalar", "неактивные клиенты",
                    "точки без заказов"],
         answer=("Davr bo'yicha zakaz bermagan klientlar ro'yxatini operator chiqarib beradi: davr va agent/hududni yozing. "
                 "Ro'yxatni agentlarga bo'lib, haftalik faollashtirish maqsadi qo'ying."),
         answer_ru=("Список клиентов без заказов за период выгрузит оператор: укажите период и агента/район. "
                    "Распределите список по агентам и поставьте недельную цель по активации."),
         who=OP, zone=REP),
    dict(title="Supervayzer: tasdiqlash so'rovlari qayerda",
         questions=["tasdiqlashim kerak bo'lgan so'rovlar", "agent so'rovini qanday tasdiqlayman", "запросы на подтверждение",
                    "как подтвердить запрос агента"],
         answer=("Klient ochish, vozvrat, chegirma, zakazni o'chirish kabi so'rovlarni supervayzer tasdiqlaydi. Tasdiqlagach, "
                 "operatorga (Saidabror) aniq ma'lumot bilan yuboring: klient, hujjat raqami, nima qilish kerak."),
         answer_ru=("Открытие клиента, возврат, скидку, удаление заказа подтверждает супервайзер. После подтверждения отправьте "
                    "оператору (Саидаброр) точные данные: клиент, номер документа, что сделать."),
         who=SUP, zone=DIST),

    # ------------------------------------------------------------ klient va hujjatlar (savdo tomoni)
    dict(title="Yangi klient ochish uchun qanday hujjatlar kerak",
         questions=["klient ochish uchun nima kerak", "qanday hujjat kerak klientga", "stir kerakmi", "документы для нового клиента",
                    "что нужно для открытия клиента"],
         answer=("Odatda kerak bo'ladi: klient nomi, STIR (yoki pasport ma'lumoti — YaTT uchun), manzil, telefon, kontakt shaxs, "
                 "nuqta rasmi va joylashuvi. To'liq ro'yxat kanal turiga bog'liq — supervayzeringizdan aniqlang. "
                 "Ma'lumot to'liq bo'lmasa klient tasdiqlanmaydi."),
         answer_ru=("Обычно нужно: название, ИНН (или паспортные данные — для ИП), адрес, телефон, контактное лицо, фото и геолокация точки. "
                    "Полный список зависит от канала — уточните у супервайзера. Без полных данных клиента не подтвердят."),
         who=SUP, zone=DIST),
    dict(title="Klient kanali: do'kon, supermarket, HoReCa, ulgurji",
         questions=["kanal nima", "horeca nima", "klient kategoriyasi", "supermarket yoki do'kon", "канал клиента",
                    "что такое horeca"],
         answer=("Kanal — klient turi: oddiy do'kon (traditsion savdo), supermarket/tarmoq (zamonaviy savdo), HoReCa "
                 "(kafe, restoran, mehmonxona), ulgurji. Kanalga qarab narx turi, aksiya va plan farq qiladi. Kanal noto'g'ri "
                 "belgilangan bo'lsa — operatorga yozing."),
         answer_ru=("Канал — тип клиента: магазин у дома (традиционная торговля), супермаркет/сеть (современная торговля), HoReCa "
                    "(кафе, рестораны, отели), опт. От канала зависят тип цены, акции и план. Канал указан неверно — напишите оператору."),
         who=OP, zone=DIST),
]
