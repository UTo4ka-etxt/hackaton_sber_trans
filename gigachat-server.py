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
RUNTIME_AUTHORIZATION_KEY = None
RUNTIME_2GIS_KEY = None
TLS_CONTEXT = None

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

def tls_context():
    """Keep TLS verification on while combining Windows and optional PEM roots."""
    global TLS_CONTEXT
    if TLS_CONTEXT:
        return TLS_CONTEXT
    context = ssl.create_default_context()
    for bundle in (
        os.environ.get("GIGACHAT_CA_BUNDLE"),
        os.environ.get("GIGACHAT_SUB_CA_BUNDLE"),
        ROOT / "russian_trusted_root_ca_pem.crt",
        ROOT / "russian_trusted_sub_ca_pem.crt",
        os.environ.get("GIGACHAT_EXTRA_CA_BUNDLE"),
    ):
        if bundle and Path(bundle).is_file():
            context.load_verify_locations(cafile=bundle)
    if os.name == "nt":
        # Corporate TLS inspection roots normally live in Windows certificate stores.
        for store in ("ROOT", "CA"):
            try:
                for certificate, encoding, _trust in ssl.enum_certificates(store):
                    if encoding == "x509_asn":
                        try:
                            context.load_verify_locations(cadata=certificate)
                        except ssl.SSLError:
                            pass
            except OSError:
                pass
    TLS_CONTEXT = context
    return context

def https_open(request, timeout):
    return urlopen(request, timeout=timeout, context=tls_context())

def tula_query(query):
    """Bias free-form searches toward Tula without breaking named regional places."""
    return query if re.search(r"тул|щёк|узлов|новомоск|донск|вен[её]в|ясногор|ефрем", query, re.I) else query + " Тула"

def two_gis_route(source, target):
    """Build a public-transport itinerary via the 2GIS Routing API."""
    key = RUNTIME_2GIS_KEY or os.environ.get("TWOGIS_API_KEY")
    if not key:
        raise RuntimeError("Ключ 2ГИС не задан")
    payload = {
        "source": {"point": {"lat": source["lat"], "lon": source["lon"]}},
        "target": {"point": {"lat": target["lat"], "lon": target["lon"]}},
        "transport": ["pedestrian", "bus", "tram", "trolleybus", "shuttle_bus", "suburban_train"],
        "locale": "ru",
        "enable_schedule": True,
        "max_result_count": 10,
        "direct_routes_count": 5,
    }
    url = "https://routing.api.2gis.com/public_transport/2.0?" + urlencode({"key": key})
    request = Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    with https_open(request, timeout=45) as response:
        return json.load(response)

def _route_names(movement):
    """Extract the public route numbers exposed by a 2GIS transport movement."""
    names = []
    for item in movement.get("routes", []):
        names.extend(item.get("names", []) or [])
        for field in ("name", "number", "ref"):
            value = item.get(field)
            if value:
                names.append(str(value))
    return {re.sub(r"[^0-9a-zа-яё]", "", str(name).lower()) for name in names}

def two_gis_line(source, target, transport, number):
    """Ask 2GIS for the actual public-transport geometry of one selected line.

    The previous client-only implementation joined stops with straight segments.
    Here the geometry and platform locations come directly from Routing API.
    """
    type_map = {
        "bus": "bus", "tram": "tram", "trolley": "trolleybus",
        "minibus": "shuttle_bus", "train": "suburban_train",
    }
    if transport not in type_map:
        raise ValueError("Неизвестный вид транспорта")
    key = RUNTIME_2GIS_KEY or os.environ.get("TWOGIS_API_KEY")
    if not key:
        raise RuntimeError("Ключ 2ГИС не задан")
    payload = {
        "source": {"point": {"lat": source[0], "lon": source[1]}},
        "target": {"point": {"lat": target[0], "lon": target[1]}},
        "transport": ["pedestrian", type_map[transport]],
        "locale": "ru",
        "enable_schedule": True,
        "max_result_count": 12,
        "direct_routes_count": 12,
    }
    url = "https://routing.api.2gis.com/public_transport/2.0?" + urlencode({"key": key})
    request = Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    with https_open(request, timeout=45) as response:
        candidates = json.load(response)
    wanted = re.sub(r"[^0-9a-zа-яё]", "", str(number).lower())
    for candidate in candidates:
        if any(wanted in _route_names(movement) for movement in candidate.get("movements", [])):
            return candidate
    raise RuntimeError(f"2ГИС не подтвердил трассу маршрута №{number} для выбранного направления")

def two_gis_geocode(query):
    """Resolve a passenger-entered stop, address, or landmark to 2GIS coordinates."""
    key = RUNTIME_2GIS_KEY or os.environ.get("TWOGIS_API_KEY")
    if not key:
        raise RuntimeError("Ключ 2ГИС не задан")
    params = urlencode({
        "q": tula_query(query),
        "type": "station,building,street,attraction,adm_div.place",
        "sort_point": "37.618,54.193",
        "fields": "items.point,items.address,items.full_name,items.name_ex",
        "key": key,
        "locale": "ru_RU",
    })
    request = Request("https://catalog.api.2gis.com/3.0/items?" + params)
    request.add_header("Accept", "application/json")
    with https_open(request, timeout=20) as response:
        return json.load(response)

def two_gis_stop_board(query):
    """Return a matching 2GIS stop and the transport lines known for it."""
    key = RUNTIME_2GIS_KEY or os.environ.get("TWOGIS_API_KEY")
    if not key:
        raise RuntimeError("Ключ 2ГИС не задан")
    params = urlencode({
        "q": tula_query(query),
        "type": "station",
        "sort_point": "37.618,54.193",
        "fields": "items.point,items.routes,items.directions,items.address,items.full_name",
        "key": key,
        "locale": "ru_RU",
    })
    request = Request("https://catalog.api.2gis.com/3.0/items?" + params)
    request.add_header("Accept", "application/json")
    with https_open(request, timeout=20) as response:
        return json.load(response)

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
        key = RUNTIME_AUTHORIZATION_KEY or os.environ.get("GIGACHAT_AUTHORIZATION_KEY")
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
        global RUNTIME_AUTHORIZATION_KEY, RUNTIME_2GIS_KEY
        if self.path == "/api/config/gigachat":
            try:
                length = int(self.headers.get("Content-Length", 0))
                key = json.loads(self.rfile.read(length)).get("authorizationKey", "").strip()
                if len(key) < 20:
                    raise ValueError("Некорректный ключ")
                RUNTIME_AUTHORIZATION_KEY = key
                Giga.token, Giga.expires = None, 0
                self.send_response(204); self.end_headers()
            except (ValueError, json.JSONDecodeError) as error:
                self.send_response(400); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": str(error)}, ensure_ascii=False).encode())
            return
        if self.path == "/api/config/2gis":
            try:
                length = int(self.headers.get("Content-Length", 0))
                key = json.loads(self.rfile.read(length)).get("apiKey", "").strip()
                if len(key) < 20:
                    raise ValueError("Некорректный ключ 2ГИС")
                RUNTIME_2GIS_KEY = key
                self.send_response(204); self.end_headers()
            except (ValueError, json.JSONDecodeError) as error:
                self.send_response(400); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": str(error)}, ensure_ascii=False).encode())
            return
        if self.path == "/api/transport/2gis/line":
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length))
                route_type, number = payload.get("type"), str(payload.get("number", "")).strip()
                source, target = payload.get("source"), payload.get("target")
                if not number or not isinstance(source, list) or not isinstance(target, list) or len(source) != 2 or len(target) != 2:
                    raise ValueError("Не хватает данных выбранного маршрута")
                if not all(isinstance(value, (int, float)) for value in source + target):
                    raise ValueError("Некорректные координаты остановок")
                result = two_gis_line(source, target, route_type, number)
                self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps(result, ensure_ascii=False).encode())
            except (ValueError, json.JSONDecodeError) as error:
                self.send_response(400); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": str(error)}, ensure_ascii=False).encode())
            except HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")[:500]
                self.send_response(502); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": f"2ГИС HTTP {error.code}: {detail}"}, ensure_ascii=False).encode())
            except (URLError, RuntimeError) as error:
                self.send_response(502); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": str(error)}, ensure_ascii=False).encode())
            return
        if self.path == "/api/transport/2gis/route":
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length))
                source, target = payload.get("source"), payload.get("target")
                for point in (source, target):
                    if not isinstance(point, dict) or not isinstance(point.get("lat"), (int, float)) or not isinstance(point.get("lon"), (int, float)):
                        raise ValueError("Нужны координаты точек A и B")
                result = two_gis_route(source, target)
                self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps(result, ensure_ascii=False).encode())
            except (ValueError, json.JSONDecodeError) as error:
                self.send_response(400); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": str(error)}, ensure_ascii=False).encode())
            except HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")[:500]
                self.send_response(502); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": f"2ГИС HTTP {error.code}: {detail}"}, ensure_ascii=False).encode())
            except (URLError, RuntimeError) as error:
                self.send_response(502); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": str(error)}, ensure_ascii=False).encode())
            return
        if self.path == "/api/transport/2gis/geocode":
            try:
                length = int(self.headers.get("Content-Length", 0))
                query = json.loads(self.rfile.read(length)).get("query", "").strip()
                if not query or len(query) > 200:
                    raise ValueError("Введите точку отправления или назначения")
                result = two_gis_geocode(query)
                self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps(result, ensure_ascii=False).encode())
            except (ValueError, json.JSONDecodeError) as error:
                self.send_response(400); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": str(error)}, ensure_ascii=False).encode())
            except HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")[:500]
                self.send_response(502); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": f"2ГИС HTTP {error.code}: {detail}"}, ensure_ascii=False).encode())
            except (URLError, RuntimeError) as error:
                self.send_response(502); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": str(error)}, ensure_ascii=False).encode())
            return
        if self.path == "/api/transport/2gis/stop-board":
            try:
                length = int(self.headers.get("Content-Length", 0))
                query = json.loads(self.rfile.read(length)).get("query", "").strip()
                if not query or len(query) > 200:
                    raise ValueError("Введите название остановки")
                result = two_gis_stop_board(query)
                self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps(result, ensure_ascii=False).encode())
            except (ValueError, json.JSONDecodeError) as error:
                self.send_response(400); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": str(error)}, ensure_ascii=False).encode())
            except HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")[:500]
                self.send_response(502); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": f"2ГИС HTTP {error.code}: {detail}"}, ensure_ascii=False).encode())
            except (URLError, RuntimeError) as error:
                self.send_response(502); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": str(error)}, ensure_ascii=False).encode())
            return
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

    def do_GET(self):
        if self.path == "/api/status":
            ready = bool(RUNTIME_AUTHORIZATION_KEY or os.environ.get("GIGACHAT_AUTHORIZATION_KEY") or os.environ.get("GIGACHAT_ACCESS_TOKEN"))
            two_gis_ready = bool(RUNTIME_2GIS_KEY or os.environ.get("TWOGIS_API_KEY"))
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"gigachatConfigured": ready, "twoGisConfigured": two_gis_ready}, ensure_ascii=False).encode())
            return
        if self.path == "/api/map-config":
            key = RUNTIME_2GIS_KEY or os.environ.get("TWOGIS_API_KEY")
            if not key:
                self.send_response(503); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"error": "Ключ 2ГИС не задан"}, ensure_ascii=False).encode())
                return
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps({"apiKey": key}, ensure_ascii=False).encode())
            return
        super().do_GET()

if __name__ == "__main__":
    print("Прототип доступен на http://127.0.0.1:8771")
    ThreadingHTTPServer(("127.0.0.1", 8771), Handler).serve_forever()
