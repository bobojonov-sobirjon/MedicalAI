# API guruhlari tavsifi (Swagger bo‘yicha) va MedicAI TZ mosligi

Hujjat loyihadagi **OpenAPI/Swagger matnlariga** asoslangan (`SPECTACULAR_SETTINGS['TAGS']`, `extend_schema`: `summary`, `description`). Har bir guruh uchun **nima uchun kerak**, **API chaqirilganda nima beradi** va tipik MedicAI TZ qaysi bandlari (ro‘yxatdan o‘tish, shaxsiy kabinet, ma’lumotnomalar, §7.8–§7.21, §5.1, §6.1, §8.2.2) **mantiqan qoplanishi** ko‘rsatilgan. To‘liq TZ PDF repozitoriyda saqlanmaydi; farq bo‘lsa, mijoz bilan imzolangan hujjatga tayaning.

**Umumiy:** aksariyat marshrutlar `/api/` prefiksi ostida. Autentifikatsiya — JWT (`Authorization: Bearer …`), operatsiya uchun boshqacha ko‘rsatilmagan bo‘lsa. WebSocket bildirishnomalari «Bildirishnomalar» guruhida.

---

## Avtorizatsiya

**Guruh ma’nosi (Swagger):** ro‘yxatdan o‘tish, kirish, token yangilash, ijtimoiy tarmoqlar, parolni almashtirish va tiklash.

**TZ:** §7.3 Ro‘yxatdan o‘tish, §7.4 Avtorizatsiya, §7.5 Parolni unutish; ijtimoiy kirish — ilovaga kirish ssenariylari doirasida.

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| POST | `/api/auth/register/` | Hisob yaratish | Foydalanuvchi yaratiladi; profil va JWT juftligi (`access`, `refresh`) qaytadi. |
| POST | `/api/auth/login/` | Login/email/telefon + parol bilan kirish | Hisob ma’lumotlari tekshiriladi; profil va JWT qaytadi. |
| POST | `/api/auth/refresh/` | Qayta kirishsiz sessiyani uzaytirish | `refresh` bo‘yicha yangi `access` beriladi. |
| POST | `/api/auth/social/` | VK / Google / Apple orqali kirish | Provayder tokeni tekshiriladi; kerak bo‘lsa foydalanuvchi va bog‘lanish yaratiladi; profil va JWT qaytadi. |
| POST | `/api/auth/password/change/` | ShKdan parolni almashtirish | Avtorizatsiya talab qilinadi; eski va yangi parol (TZ §7.7 / §7.5, sxema tavsifida). |
| POST | `/api/auth/password/forgot/request/` | Emailga kod so‘rash | Hisob bo‘lsa tiklash kodi yuboriladi (maxfiylik uchun bir xil javob). |
| POST | `/api/auth/password/forgot/verify/` | Pochta kodini tekshirish | Keyingi qadam uchun `reset_token` qaytadi. |
| POST | `/api/auth/password/forgot/reset/` | Yangi parol o‘rnatish | `reset_token` bo‘yicha parol yangilanadi va JWT qaytadi. |

---

## Profil

**Guruh ma’nosi (Swagger):** joriy foydalanuvchi: profilni o‘qish va yangilash (shaxsiy kabinet).

**TZ:** §7.7 Profil, §7.20 Shaxsiy kabinet; oilaviy profillar — ShK/yordamchi ssenariylarida «kim uchun» tanlovi.

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/auth/me/` | Profil ma’lumotlari | Foydalanuvchi maydonlari (FIO, jins, shahar, bo‘y, vazn va hokazo) qaytadi. |
| PATCH | `/api/auth/me/` | Profilni yangilash | Qisman yangilanish; avatar — `multipart/form-data`. Parol almashtirish — alohida endpoint. |
| GET | `/api/me/family/` | Bog‘langan oila a’zolari | Bog‘langan profillar va yorliqlar qaytadi. |
| POST | `/api/me/family/` | Mavjud foydalanuvchini bog‘lash | `member_id` bo‘yicha «egasi — oila a’zosi» bog‘lanishi yaratiladi. |
| DELETE | `/api/me/family/<member_id>/` | Profilni ajratish | Joriy egasi uchun bog‘lanish o‘chiriladi. |

---

## Kasalliklar

**Guruh ma’nosi (Swagger):** ochiq kasalliklar ma’lumotnomasi, qidiruv, tavsiya etilgan dori-darmonlar bilan kartochka.

**TZ:** §7.9 Kasalliklar ma’lumotnomasi; admin ma’lumotnomasi — §5.6.

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/catalog/diseases/` | Kasalliklar ro‘yxati | Ochiq; ixtiyoriy `q` — nom bo‘yicha qidiruv. |
| GET | `/api/catalog/diseases/<pk>/` | Kasallik kartochkasi | Ochiq; ma’lumotnomadagi bog‘langan dorilar kiradi. |

---

## Dori-darmonlar

**Guruh ma’nosi (Swagger):** ochiq ma’lumotnoma: ro‘yxat va dori kartochkasi (sharhlar va ijtimoiy funksiyalarsiz).

**TZ:** §7.10 Dori-darmonlar ma’lumotnomasi (asosiy ro‘yxat/kartochka).

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/catalog/drugs/` | Dorilar katalogi | Ochiq; ixtiyoriy `q` — nom bo‘yicha qidiruv. |
| GET | `/api/catalog/drugs/<pk>/` | Dori kartochkasi | Ochiq; shu tegdagi ma’lumotnoma ma’lumotlari, sharhlar bloki emas. |

---

## Dorilar bo‘yicha sharhlar

**Guruh ma’nosi (Swagger):** tasdiqlangan sharhlar va dori bo‘yicha moderatsiyaga sharh yuborish.

**TZ:** §7.10.1 Sharhlar sahifasi, §7.10.2 Sharh qo‘shish; moderatsiya — admin panel orqali (§5.7.1).

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/catalog/drugs/<drug_id>/reviews/` | Sharhlar lentasi | Ochiq; faqat «tasdiqlangan» statusdagi sharhlar. |
| POST | `/api/catalog/drugs/<drug_id>/reviews/` | Sharh qoldirish | Avtorizatsiya kerak; moderatsiya yozuvi yaratiladi; haqoratli leksika tekshiruvi. |

---

## Dorilar muhokamasi

**Guruh ma’nosi (Swagger):** dori bo‘yicha muhokama tredi: xabarlar ro‘yxati va xabar yuborish.

**TZ:** preparat kartochkasida jamoaviy muhokama (§7.10 ruhida, dorilar atrofida hamjamiyat).

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/catalog/drugs/<drug_id>/discussion/` | Muhokamani o‘qish | Avtorizatsiyali foydalanuvchi; tred xabarlari. |
| POST | `/api/catalog/drugs/<drug_id>/discussion/` | Tredga yozish | Tanlangan dori muhokamasida xabar yaratiladi. |

---

## Dorilarni baholash

**Guruh ma’nosi (Swagger):** yulduzcha bilan baholash (24 soatda bir marta o‘zgartirishdan ko‘p emas).

**TZ:** ma’lumotnoma interfeysida preparat reytingi (§7.10).

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| POST | `/api/catalog/drugs/<drug_id>/star-rating/` | Yulduzcha qo‘yish/yangilash | Baho saqlanadi; 24 soatdan tez-tez o‘zgartirib bo‘lmaydi; dolzarb dori ma’lumotlari qaytadi. |

---

## Dorilar analoglari

**Guruh ma’nosi (Swagger):** dori bo‘yicha analoglar ro‘yxati (MBdan; parser/admin to‘ldiradi).

**TZ:** kartochkadagi «analoglar» bloki (§7.10, admin §5.7).

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/catalog/drugs/<drug_id>/analogs/` | Analoglar ro‘yxati | Ochiq; analoglar jadvalidan chiqarish. |

---

## Dorilarni ko‘rishlar

**Guruh ma’nosi (Swagger):** kartochkani ochishni hisobga olish — «oldingi ko‘rilganlar» ro‘yxati uchun.

**TZ:** ko‘rishlar tarixi / ma’lumotnoma bo‘ylab navigatsiya qulayligi (§7.10 bilan bog‘liq).

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| POST | `/api/catalog/drugs/<pk>/view/` | Ko‘rishni qayd etish | **POST** (GET emas), chunki MB holatini o‘zgartiradi; ko‘rish yozuvi yaratiladi/yangilanadi. |

*«Oldingi ko‘rilganlar» ro‘yxati:* `GET /api/me/recent-drugs/` («Dori shkafi» guruhida).

---

## Sog‘liq tarixi

**Guruh ma’nosi (Swagger):** foydalanuvchining shaxsiy kasallik yozuvlari (TZ §7.8).

**TZ:** §7.8 Kasalliklar tarixi; §7.8.1 yozuv qo‘shish/tahrirlash.

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/me/disease-records/` | Yozuvlar ro‘yxati | Faqat joriy foydalanuvchining yozuvlari; ixtiyoriy `q` — qidiruv. |
| POST | `/api/me/disease-records/` | Yozuv yaratish | Ichki shifokor tashriflari/tahlillar/retseptlar ro‘yxatlari berilishi mumkin — yozuv ichida saqlanadi. |
| GET | `/api/me/disease-records/<pk>/` | Yozuv tafsilotlari | Ichki ob’ektlar bilan. |
| PATCH | `/api/me/disease-records/<pk>/` | Yozuvni yangilash | Qisman yangilanish; ichki ro‘yxatlarni almashtirish qoidalari — Swaggerda. |
| DELETE | `/api/me/disease-records/<pk>/` | Yozuvni o‘chirish | Joriy foydalanuvchi yozuvi o‘chiriladi. |

---

## Shifokor qabuliga tashriflar

**Guruh ma’nosi (Swagger):** kasallik tarixi yozuvi ichidagi shifokor qabullari.

**TZ:** §7.8.1 / tarix kartochkasi — shifokor tashriflari.

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/me/disease-records/<record_id>/doctor-visits/` | Tashriflar ro‘yxati | Bitta kasallik yozuvi uchun. |
| POST | `/api/me/disease-records/<record_id>/doctor-visits/` | Tashrif qo‘shish | Ko‘rsatilgan yozuvda qabul yaratiladi. |
| GET | `/api/me/doctor-visits/<pk>/` | Bitta tashrif | Tafsilot. |
| PATCH | `/api/me/doctor-visits/<pk>/` | Tashrifni o‘zgartirish | Qisman yangilanish. |
| DELETE | `/api/me/doctor-visits/<pk>/` | Tashrifni o‘chirish | Foydalanuvchiga tegishli bo‘lsa o‘chiriladi. |

---

## Tahlillar

**Guruh ma’nosi (Swagger):** tarix yozuvi ichidagi tahlillar; foto yuklash, OCR (TZ).

**TZ:** §7.8 — tekshiruv natijalari; OCR — 2-bosqich / AI (tahlil skaneri).

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/me/disease-records/<record_id>/analyses/` | Tahlillar ro‘yxati | Kasallik yozuvi doirasida. |
| POST | `/api/me/disease-records/<record_id>/analyses/` | Tahlil qo‘shish | Tahlil yozuvi yaratiladi. |
| GET | `/api/me/analyses/<pk>/` | Bitta tahlil | Tafsilot. |
| PATCH | `/api/me/analyses/<pk>/` | Tahlilni yangilash | Jumladan foto (`multipart`). |
| DELETE | `/api/me/analyses/<pk>/` | Tahlilni o‘chirish | Foydalanuvchiga tegishli bo‘lsa o‘chiriladi. |
| POST | `/api/me/analyses/<pk>/ocr/` | Tahlil suratidan OCR | Oldin yuklangan suratdan matn; natija maydoni uchun `mode=append|replace`. |

---

## Retseptlar

**Guruh ma’nosi (Swagger):** kasallik tarixi yozuvi ichidagi retsept suratlari.

**TZ:** §7.8 — tarix kartochkasida hujjatlar/retseptlarni saqlash.

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/me/disease-records/<record_id>/prescriptions/` | Retseptlar ro‘yxati | Bitta kasallik yozuvi uchun. |
| POST | `/api/me/disease-records/<record_id>/prescriptions/` | Retsept surati qo‘shish | Fayl yuklash imkoniyati bilan yozuv yaratiladi. |
| GET | `/api/me/prescriptions/<pk>/` | Bitta retsept | Tafsilot. |
| PATCH | `/api/me/prescriptions/<pk>/` | Yangilash | Jumladan multipart orqali foto. |
| DELETE | `/api/me/prescriptions/<pk>/` | O‘chirish | Foydalanuvchi retsepti o‘chiriladi. |

---

## Yordamchi

**Guruh ma’nosi (Swagger):** simptomlar va AI tanlash (Gemini), simptomlar/tana qismlari ma’lumotnomasi, FAQ.

**TZ:** §7.11 Yordamchi; §6.1 AI / ma’lumotnomaviy javoblar (FAQ MBda).

*Realizatsiya eslatmasi:* matnli JSON uchun kodda kalit bo‘lsa RuTronix, aks holda Gemini ishlatilishi mumkin; Swaggerda diagnostika tavsifida Gemini ko‘rsatilgan.

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/catalog/symptoms/` | Simptom qiyinchilari | `q` parametri — avtoto‘ldirish (yordamchi ekrani). |
| GET | `/api/catalog/body-parts/` | Tana qismlari ma’lumotnomasi | UI «figura» uchun; barqaror `code`, ko‘rinish `label`. |
| GET | `/api/faq/` | Savol-javob qidiruv | `q` parametri (minimal uzunlik — sxemada); javoblar MBdan (TZ §6.1). |
| POST | `/api/assistant/diagnose/` | AI + simptomlar bo‘yicha ma’lumotnoma | Simptom va tana qismi IDlari, matn, harorat, bosim qabul qilinadi; natija saqlanadi; `diagnosis_id`, ma’lumotnoma konteksti va `ai` bloki qaytadi. |
| GET | `/api/assistant/diagnoses/` | Yordamchiga murojaatlar tarixi | Faqat joriy foydalanuvchi; simptomlar/tana qismlari kengaytirilgan. |
| GET | `/api/assistant/diagnoses/<id>/` | Bitta saqlangan natija | Diagnostika tarixidagi bitta yozuv tafsiloti. |

---

## Dori shkafi

**Guruh ma’nosi (Swagger):** mening dori shkafim: ro‘yxat, qo‘shish, suratdan tanib olish.

**TZ:** §7.14 Mening dori shkafim.

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/me/cabinet/items/` | Shkaf ro‘yxati | Ixtiyoriy `q` — preparat nomi / maxsus nom bo‘yicha qidiruv. |
| POST | `/api/me/cabinet/items/` | Pozitsiya qo‘shish | Foydalanuvchi shkafida yozuv yaratiladi. |
| GET | `/api/me/cabinet/items/<pk>/` | Bitta pozitsiya | Mini-kartochka uchun tafsilot. |
| PATCH | `/api/me/cabinet/items/<pk>/` | Yangilash | Yaroqlilik muddati, eslatmalar, foto va hokazo. |
| DELETE | `/api/me/cabinet/items/<pk>/` | Shkafdan olib tashlash | Foydalanuvchi yozuvi o‘chiriladi. |
| POST | `/api/me/cabinet/recognize/` | Suratdan tanish | `multipart`, maydon `image`; tanilgan nom va mos kelganda ma’lumotnomadagi dori qaytadi. |
| GET | `/api/me/recent-drugs/` | Yaqinda ko‘rilganlar | `limit` orqali cheklov; «oldingi ko‘rilganlar» bloki uchun. |

---

## Kontent

**Guruh ma’nosi (Swagger):** statik sahifalar (kompaniya haqida, maxfiylik), ilova konfiguratsiyasi, so‘rovnomalar.

**TZ:** §7.15 Kompaniya haqida, §7.16 Maxfiylik; so‘rovnomalar/bannerlar — ShK yordamchi kontenti.

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/content/pages/<slug>/` | Sahifa matni | Admin orqali HTML/matn (`about`, `privacy` va boshqalar). |
| GET | `/api/content/config/` | Ochiq sozlamalar | Avtorizatsiyasiz: masalan trial muddati, psixolog emaili. |
| POST | `/api/me/survey/` | So‘rovnoma yuborish | Avtorizatsiyali foydalanuvchi javoblari saqlanadi (qalqib chiquvchi so‘rovnomalar). |

---

## Tibbiy muassasalar

**Guruh ma’nosi (Swagger):** shaharlar, dorixonalar va kasalxonalar, muassasa kartochkasi (TZ §7.13).

**TZ:** §7.13 Tibbiy muassasalar ma’lumotnomasi.

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/geo/cities/` | Shaharlar ro‘yxati | Shahar avtoto‘ldirish; `q`, `limit` parametrlari. |
| GET | `/api/geo/facilities/` | Dorixonalar / kasalxonalar | Filtr `kind` (pharmacy/hospital), `city_id`, `q` qidiruv. |
| GET | `/api/geo/facilities/<pk>/` | Muassasa kartochkasi | Koordinatalar, ish vaqti va hokazo bilan tafsilot. |

---

## Bildirishnomalar

**Guruh ma’nosi (Swagger):** voqealar (REST), foydali lenta, sozlamalar; real vaqtda push uchun WebSocket `ws/notifications/?token=JWT` (TZ §7.12).

**TZ:** §7.12 Bildirishnomalar; §7.12.1 Voqealar; §7.12.2 Foydali; maslahatlarga obuna.

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/me/notifications/events/` | Voqealar lentasi | Foydalanuvchi bildirishnomalari; chaqiruvda eslatmalar logikasi qo‘shimcha ishga tushishi mumkin (backend). |
| POST | `/api/me/notifications/events/` | Eslatma/voqea yaratish | Yozuv yaratiladi (oilaviy profil uchun `subject_user_id` bilan). |
| POST | `/api/me/notifications/events/<pk>/read/` | O‘qilgan deb belgilash | `read_at` qo‘yiladi. |
| GET | `/api/me/notifications/badge/` | Qo‘ng‘iroqcha uchun hisoblagichlar | O‘qilmagan voqealar, «Foydali», tavsiya etilgan tab. |
| GET | `/api/me/notifications/useful/` | «Foydali» tabi | Maslahatlar va ilova yangilanishlari (faol obuna bo‘lsa maslahatlar). |
| POST | `/api/me/notifications/useful/seen/` | «Foydali» ko‘rilgan deb belgilash | Foydali blokdagi unread hisoblash uchun. |
| GET | `/api/me/tip-settings/` | Maslahat sozlamalari | Kuniga maslahat limiti, foydali obuna belgisi. |
| PATCH | `/api/me/tip-settings/` | Maslahat sozlamalarini yangilash | Limit va obunani o‘zgartiradi. |
| POST | `/api/me/disease-tip-subscribe/<disease_id>/` | Kasallik bo‘yicha maslahatga obuna | Obunani yoqadi. |
| DELETE | `/api/me/disease-tip-subscribe/<disease_id>/` | Kasallik bo‘yicha obunani bekor qilish | Obunani o‘chiradi. |
| WS | `/ws/notifications/?token=<JWT_access>` | Darhol yangilanishlar | REST emas: API bilan bir xil `access`; voqealar o‘zgarganda push. |

---

## Qo‘llab-quvvatlash

**Guruh ma’nosi (Swagger):** fikr-mulohaza, psixologga savol, qo‘llab-quvvatlash chati (TZ §7.17–7.18).

**TZ:** §7.17 Fikr-mulohaza; §7.17.1 Chat; §7.17.2 Xat; mutaxassisga savol (TZda §7.19 «shifokor» ham bor — bu yerda psixolog alohida endpoint).

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| POST | `/api/support/feedback/` | Fikr-mulohaza | MBda tiket yaratiladi (API tavsifidagi xat ssenariysi). |
| POST | `/api/support/psychology/` | Psixologga savol | Murojaat saqlanadi; server sozlamalaridagi emailga yuborish. |
| GET | `/api/me/chat/threads/` | Qo‘llab-quvvatlash chatlari | Foydalanuvchi tredlari. |
| POST | `/api/me/chat/threads/` | Chat yaratish | Ixtiyoriy sarlavha bilan yangi tred. |
| GET | `/api/me/chat/threads/<thread_id>/messages/` | Xabarlar tarixi | Tanlangan treddagi xabarlar. |
| POST | `/api/me/chat/threads/<thread_id>/messages/` | Xabar yuborish | Foydalanuvchi xabari qo‘shiladi. |

---

## Relaks

**Guruh ma’nosi (Swagger):** GIF va video lenta (TZ §7.21).

**TZ:** §7.21 Relaks.

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/relax/feed/` | Kontent lentasi | `category` parametri: `gif` yoki `video`; admin orqali berilgan kontent. |

---

## Ovoz

**Guruh ma’nosi (Swagger):** formalardagi maydonlar uchun nutqni tanib olish (vaqtincha stub / tashqi STT, TZ §8.2.2).

**TZ:** §8.2.2 (formalarda ovozli kiritish).

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| POST | `/api/me/voice/transcribe/` | Maydonlar uchun STT | `audio` qabul qiladi; hozirgi realizatsiya — stub (501) va tashqi STT ulash bo‘yicha ko‘rsatma. |

---

## Administratsiya

**Guruh ma’nosi (Swagger):** xodimlar uchun metrikalar va svodkalar (TZ §5.1).

**TZ:** §5.1 Analitika (xodimlar uchun agregat ma’lumot).

| Metod | Yo‘l | Nima uchun | Chaqirilganda nima bo‘ladi |
|--------|------|------------|---------------------------|
| GET | `/api/admin/metrics/summary/` | Svodka | Faqat `is_staff`; masalan shaharlar bo‘yicha foydalanuvchilar. |

---

## Qisqa jadval: «TZ mavzusi — API guruhi»

| TZ mavzusi | API guruhi |
|------------|------------|
| Ro‘yxatdan o‘tish, kirish, parol | Avtorizatsiya |
| Profil, oila | Profil |
| Kasalliklar ma’lumotnomasi | Kasalliklar |
| Dori-darmonlar ma’lumotnomasi | Dori-darmonlar + alohida teglar: sharhlar, muhokama, yulduzcha, analoglar, ko‘rishlar |
| Kasalliklar tarixi | Sog‘liq tarixi, Tashriflar, Tahlillar, Retseptlar |
| Yordamchi, simptomlar, AI | Yordamchi (+ katalogdagi simptom/tana qismlari) |
| Bildirishnomalar | Bildirishnomalar (+ WebSocket) |
| Tibbiy muassasalar | Tibbiy muassasalar |
| Dori shkafi | Dori shkafi |
| Kompaniya, maxfiylik, so‘rovnomalar | Kontent |
| Qo‘llab-quvvatlash, chat, xat, psixolog | Qo‘llab-quvvatlash |
| Relaks | Relaks |
| Ovozli kiritish | Ovoz (stub) |
| Adminlar uchun analitika | Administratsiya |

PDF bilan **qat’iy** moslashtirish kerak bo‘lsa, 7.x va 8.x bandlari matnini yuqoridagi jadval bilan qator-qator solishtiring.
