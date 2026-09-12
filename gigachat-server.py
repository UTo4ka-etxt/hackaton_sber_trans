"""Local RAG proxy for the passenger-support prototype.

The GigaChat authorization key is accepted only through an environment variable,
never from the browser and never saved to disk.
"""
import json
import os
import re
import ssl
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "dist" if (ROOT / "dist").exists() else ROOT
AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URLS = [
    "https://api.giga.chat/v1/chat/completions",
    "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
]
USER_AGENT = "TulaTransportAssistant/1.0"

KNOWLEDGE = [
    ["Льготный проезд", "Льготный проезд действует для установленных федеральных и региональных льготных категорий. Право подтверждается статусом льготника.", "Постановление администрации Тульской области № 83", "https://tularegion.ru/upload/iblock/cb3/yv6hnn3uigkzly2fr5z6wlpucbgs6iqc.docx", "льгот льгота пенсионер ветеран инвалид кому положен"],
    ["Стоимость льготного проезда", "750 ₽ в месяц для федеральных и региональных льготников, пенсионеров и студентов. Для школьников: 200 ₽ на один вид транспорта или 350 ₽ на три.", "Постановление Правительства Тульской области № 59", "http://publication.pravo.gov.ru/document/7100202507230001?index=2", "стоимость цена льготный пенсионер студент школьник 750 200 350"],
    ["Маршруты и схемы", "Актуальные схемы и изменения движения публикуются на сайте МКП «Тулгорэлектротранс» и в официальных сообщениях администрации Тулы.", "Схемы маршрутов МКП «Тулгорэлектротранс»", "https://tulatrans.ru/marshruty/skhemy-marshrutov/", "схема движение автобус маршрут изменение"],
    ["Стоимость обычного проезда", "В городе: 36 ₽ по транспортной карте, 38 ₽ банковской картой, 45 ₽ наличными. В пригородном и межмуниципальном сообщении — 4,46 ₽ за км.", "Постановление Правительства Тульской области № 59", "https://tulatrans.ru/pasazhiru/oplata-proezda/", "стоимость цена проезд тариф наличные банковская карта"],
    ["Отслеживание транспорта", "Можно использовать «Умный транспорт», Яндекс Карты, Bustime и портал РНИС Тульской области. Отдельного НПА с перечнем приложений в материалах нет.", "Справочные сведения", "https://portal-rnis.orgpn.ru/map/bus", "приложение отслеживать автобус где транспорт карта"],
    ["Способы оплаты", "Проезд оплачивают транспортной картой, банковской картой или наличными. Льготный билет оформляют на социальную транспортную карту или карту «Мир».", "Информация об оплате проезда", "https://tulatrans.ru/pasazhiru/oplata-proezda/", "оплатить оплата способ карта наличные"],
    ["Льготный абонемент в пригороде", "Проверьте, входит ли маршрут в перечень. Если входит, обратитесь в ОЕИРЦ с картой и документами: +7 (4872) 705-507 или +7 (920) 777-55-99.", "Правила льготного билета", "https://tulatrans.ru/pasazhiru/oplata-proezda/", "абонемент проездной не действует пригород"],
    ["Оплата телефоном или часами", "Льготный билет привязан к социальной транспортной карте или конкретной карте «Мир». Телефон или часы не являются тем же носителем, поэтому льгота на них не переносится.", "ОЕИРЦ: носители льготного проездного", "https://oeirc.ru/?page=tk/stk.php", "телефон часы смартфон мир абонемент"],
    ["Уведомление об оплате", "Уведомление может задерживаться из-за обработки транзакции. Нормативный срок доставки уведомления в доступных материалах не указан.", "Информация об оплате проезда", "https://tulatrans.ru/pasazhiru/oplata-proezda/", "уведомление смс пуш задержка"],
    ["Повторное списание", "Проверьте историю операций. При подтверждённом двойном списании обратитесь к оператору транспортной системы или в банк, сообщив дату, время, маршрут и данные операции.", "Справочный материал о спорных списаниях", "https://okulovskij-r49.gosweb.gosuslugi.ru/dlya-zhiteley/organizatsii/upravleniya-rospotrebnadzora/novosti_5180.html", "списание дважды повторно лишние деньги"],
    ["Построение маршрута", "Уточните точку отправления и нужную остановку. Построить маршрут помогут схемы маршрутов, «Умный транспорт», Яндекс Карты, Bustime или РНИС.", "Схемы маршрутов МКП «Тулгорэлектротранс»", "https://tulatrans.ru/marshruty/skhemy-marshrutov/", "добраться доехать остановка куда маршрут"],
    ["Оформление льготы", "Первичная выдача социальной транспортной карты и регистрация льготы оформляются через МФЦ. Заявление на подтверждение категории можно подать через УСЗН, МФЦ или Госуслуги.", "Постановление № 83 и инструкция ОЕИРЦ", "https://oeirc.ru/?page=tk/stk.php", "оформить школьный студенческий мфц"],
    ["Льготный проездной без прописки", "Право зависит от льготной категории и подтверждённых сведений, а не только от места обращения. Для проверки ситуации обратитесь в МФЦ или ОЕИРЦ.", "Постановление администрации Тульской области № 83", "https://base.garant.ru/30316564/", "прописка регистрация оформить не тула"],
    ["Передача льготного абонемента", "Нет. Льготный проездной предназначен для конкретного льготника и подтверждает его личное право на льготный проезд.", "Постановление администрации Тульской области № 83", "https://base.garant.ru/30316564/", "передать родственник семья чужой"],
    ["Потеря карты", "Обратитесь в центр обслуживания ОЕИРЦ для повторной выдачи или регистрации льготы. Повторная социальная транспортная карта стоит 100 ₽.", "ОЕИРЦ: часто задаваемые вопросы", "https://oeirc.ru/?page=tk/faq.php", "потерял украли восстановить карта"],
    ["Валидатор", "Успешное завершение операции на валидаторе подтверждает оплату. Сам по себе цвет экрана не является юридическим подтверждением: ориентируйтесь на итог операции, чек или данные транзакции.", "Техническая логика работы валидатора", "", "зеленый экран валидатор подтверждение"],
    ["Жалоба на автобус", "Зафиксируйте номер маршрута или автобуса, дату, время, остановку и описание проблемы. Для Тулы: (4872) 55-64-73 или (4872) 76-03-43. Горячая линия: 8-919-070-26-81, пн–пт 09:00–18:00.", "Горячая линия по вопросам работы общественного транспорта", "https://mvp.tularegion.ru/press_center/vazhnye-soobshcheniya/goryachaya-liniya-po-voprosam-raboty-obshchestvennogo-transporta/", "автобус опоздал расписание жалоба грязный водитель"],
    ["Новая остановка", "Установка возможна, но зависит от схемы движения, места и решения уполномоченных органов. Министерство транспорта: 8 (800) 200-71-02.", "Разъяснение Министерства транспорта Тульской области", "https://transport.tularegion.ru/press_center/news/zhitelyam-razyasnili-kogda-mozhno-ustanovit-novuyu-ostanovku/", "новая остановка поставить комплекс"],
]

def tokens(text):
    return set(re.findall(r"[а-яa-z0-9]{3,}", text.lower().replace("ё", "е")))

def https_open(request, timeout):
    """Keep TLS verification on; an optional PEM bundle supports НУЦ/corporate CAs."""
    bundle = os.environ.get("GIGACHAT_CA_BUNDLE")
    context = ssl.create_default_context(cafile=bundle) if bundle else ssl.create_default_context()
    return urlopen(request, timeout=timeout, context=context)

def retrieve(question):
    words = tokens(question)
    ranked = []
    for item in KNOWLEDGE:
        score = len(words & tokens(item[0] + " " + item[4]))
        ranked.append((score, item))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [item for score, item in ranked[:4] if score > 0]

class Giga:
    token = None
    expires = 0

    @classmethod
    def access_token(cls):
        if cls.token and cls.expires - time.time() > 60:
            return cls.token
        supplied_token = os.environ.get("GIGACHAT_ACCESS_TOKEN")
        if supplied_token:
            cls.token, cls.expires = supplied_token, time.time() + 25 * 60
            return cls.token
        key = os.environ.get("GIGACHAT_AUTHORIZATION_KEY")
        if not key:
            raise RuntimeError("Ключ GigaChat не задан")
        preferred = os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        scopes = list(dict.fromkeys([preferred, "GIGACHAT_API_PERS", "GIGACHAT_API_B2B", "GIGACHAT_API_CORP"]))
        last_error = None
        for scope in scopes:
            request = Request(AUTH_URL, data=urlencode({"scope": scope}).encode("utf-8"), method="POST")
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
            request.add_header("Accept", "application/json")
            request.add_header("RqUID", str(uuid.uuid4()))
            request.add_header("Authorization", "Basic " + key)
            request.add_header("User-Agent", USER_AGENT)
            try:
                with https_open(request, timeout=30) as response:
                    data = json.load(response)
                cls.token, cls.expires = data["access_token"], float(data["expires_at"])
                return cls.token
            except HTTPError as error:
                last_error = error
                if error.code not in (401, 403):
                    raise
        raise last_error or RuntimeError("Не удалось получить токен GigaChat")

    @classmethod
    def answer(cls, question, context):
        if not context:
            return {"answer": "В предоставленных материалах нет подтверждённой информации для точного ответа. Уточните, пожалуйста, маршрут и что именно произошло, либо обратитесь в ОЕИРЦ: +7 (4872) 705-507.", "source": None}
        facts = "\n\n".join(f"[{n+1}] {item[0]}: {item[1]}" for n, item in enumerate(context))
        system = """Ты — ассистент первой линии поддержки пассажиров Тульской области. Отвечай только на русском и только по фактам из КОНТЕКСТА. Не придумывай тарифы, сроки, правила, контакты и маршруты. Если хотя бы один фрагмент КОНТЕКСТА относится к вопросу, обязательно дай полезный ответ по этому фрагменту: переформулировки «цена билета» и «стоимость проезда», «где автобус» и «отслеживание транспорта» означают один и тот же смысл. Пиши НЕДОСТАТОЧНО_ДАННЫХ только если ни один фрагмент не относится к вопросу. Если не хватает важного параметра, задай один короткий уточняющий вопрос после доступного ответа. Не упоминай номера фрагментов и не говори, что ты ИИ."""
        payload = json.dumps({"model": "GigaChat-2-Pro", "temperature": 0.15, "messages": [{"role": "system", "content": system}, {"role": "user", "content": "КОНТЕКСТ:\n" + facts + "\n\nВОПРОС ПАССАЖИРА:\n" + question}]}).encode("utf-8")
        last_error = None
        for chat_url in CHAT_URLS:
            request = Request(chat_url, data=payload, method="POST")
            request.add_header("Content-Type", "application/json")
            request.add_header("Accept", "application/json")
            request.add_header("Authorization", "Bearer " + cls.access_token())
            request.add_header("User-Agent", USER_AGENT)
            try:
                with https_open(request, timeout=90) as response:
                    text = json.load(response)["choices"][0]["message"]["content"].strip()
                break
            except URLError as error:
                last_error = error
        else:
            raise last_error or RuntimeError("Не удалось соединиться с GigaChat")
        if text == "НЕДОСТАТОЧНО_ДАННЫХ":
            item = context[0]
            return {"answer": item[1], "source": {"name": item[2], "url": item[3]}}
        item = context[0]
        return {"answer": text, "source": {"name": item[2], "url": item[3]}}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204); self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS"); self.send_header("Access-Control-Allow-Headers", "Content-Type"); self.end_headers()

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404); return
        try:
            length = int(self.headers.get("Content-Length", 0))
            question = json.loads(self.rfile.read(length)).get("question", "").strip()
            if not question or len(question) > 2000: raise ValueError("Некорректный вопрос")
            result = Giga.answer(question, retrieve(question))
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps(result, ensure_ascii=False).encode())
        except (ValueError, KeyError) as error:
            self.send_response(400); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": str(error)}, ensure_ascii=False).encode())
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:300]
            self.send_response(502); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": f"GigaChat HTTP {error.code}: {detail}"}, ensure_ascii=False).encode())
        except URLError as error:
            self.send_response(502); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": f"Не удалось установить защищённое соединение с GigaChat: {error.reason}"}, ensure_ascii=False).encode())
        except RuntimeError as error:
            self.send_response(502); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": str(error)}, ensure_ascii=False).encode())

if __name__ == "__main__":
    print("Прототип доступен на http://127.0.0.1:8771")
    ThreadingHTTPServer(("127.0.0.1", 8771), Handler).serve_forever()
