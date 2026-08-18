import html
import json
import random
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import streamlit as st
from openai import OpenAI
from pydantic import BaseModel
from travel_data import DESTINATIONS


st.set_page_config(
    page_title="어디든 떠나봇",
    page_icon=":material/flight_takeoff:",
    layout="wide",
)


# ── 앱 설정 ──────────────────────────────────────────────────────────────

API_MODEL = "gpt-5.4-nano"
ORIGIN = {
    "city": "서울",
    "airport": "ICN",
    "timezone": "Asia/Seoul",
    "currency": "KRW",
}


# 도시·항공·명소·음식 데이터는 travel_data.py 한 곳에서 관리한다.
COUNTRY_CURRENCIES = {
    "JP": "JPY", "TW": "TWD", "VN": "VND", "TH": "THB", "SG": "SGD",
    "ID": "IDR", "FR": "EUR", "ES": "EUR", "IT": "EUR", "DE": "EUR",
    "PT": "EUR", "NL": "EUR", "BE": "EUR", "AT": "EUR", "GR": "EUR",
    "GB": "GBP", "CZ": "CZK", "US": "USD", "AU": "AUD", "TR": "TRY",
    "IS": "ISK", "MA": "MAD", "KR": "KRW", "CN": "CNY", "HK": "HKD",
    "MO": "MOP", "MY": "MYR", "PH": "PHP", "AE": "AED", "QA": "QAR",
    "IN": "INR", "CH": "CHF", "HU": "HUF", "PL": "PLN", "DK": "DKK",
    "SE": "SEK", "NO": "NOK", "CA": "CAD", "MX": "MXN", "BR": "BRL",
    "AR": "ARS", "NZ": "NZD", "EG": "EGP", "ZA": "ZAR", "KE": "KES",
    "TZ": "TZS",
}

WEATHER_CODES = {
    0: "맑음", 1: "대체로 맑음", 2: "부분적으로 흐림", 3: "흐림",
    45: "안개", 48: "서리 안개", 51: "약한 이슬비", 53: "이슬비",
    55: "강한 이슬비", 61: "약한 비", 63: "비", 65: "강한 비",
    71: "약한 눈", 73: "눈", 75: "강한 눈", 80: "소나기",
    81: "강한 소나기", 82: "매우 강한 소나기", 95: "뇌우",
}


# ── 구조화된 결과 모델 ─────────────────────────────────────────────────

class WeatherInfo(BaseModel):
    condition: str
    temperature: float
    feels_like: float
    rain_probability: int


class FlightInfo(BaseModel):
    departure_airport: str
    arrival_airport: str
    direct_available: bool
    stops: int
    duration: str
    note: str


class TravelBriefing(BaseModel):
    city: str
    country: str
    local_time: str
    time_difference: str
    currency: str
    exchange_rate: float | None
    converted_amount: float | None
    base_amount_krw: int
    weather: WeatherInfo
    flight: FlightInfo
    attractions: list[str]
    foods: list[str]
    travel_tip: str


# ── 실제 도구 함수 ──────────────────────────────────────────────────────

def request_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "TravelBriefBot/1.0"})
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.load(response)


def find_catalog_city(city: str) -> tuple[str | None, dict[str, Any] | None]:
    normalized = city.strip().lower()
    for name, data in DESTINATIONS.items():
        candidates = [name.lower(), *(alias.lower() for alias in data["aliases"])]
        if normalized in candidates:
            return name, data
    return None, None


@st.cache_data(ttl=60 * 60 * 24, max_entries=100)
def geocode_city(city: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"name": city, "count": 1, "language": "ko", "format": "json"})
    data = request_json(f"https://geocoding-api.open-meteo.com/v1/search?{query}")
    if not data.get("results"):
        raise ValueError(f"'{city}'의 위치를 찾지 못했습니다.")
    place = data["results"][0]
    return {
        "city": place["name"],
        "country": place.get("country", "국가 정보 없음"),
        "country_code": place.get("country_code", ""),
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "timezone": place["timezone"],
    }


@st.cache_data(ttl=60 * 15, max_entries=100)
def get_city_weather(city: str) -> dict[str, Any]:
    """도시 이름을 받아 현재 날씨와 온도, 체감온도, 강수확률을 조회한다."""
    place = geocode_city(city)
    params = urllib.parse.urlencode({
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "current": "temperature_2m,apparent_temperature,weather_code",
        "hourly": "precipitation_probability",
        "forecast_days": 1,
        "timezone": "auto",
    })
    data = request_json(f"https://api.open-meteo.com/v1/forecast?{params}")
    current = data["current"]
    current_hour = current["time"][:13] + ":00"
    try:
        hour_index = data["hourly"]["time"].index(current_hour)
        rain_probability = data["hourly"]["precipitation_probability"][hour_index] or 0
    except (ValueError, KeyError, IndexError):
        rain_probability = 0
    return {
        **place,
        "condition": WEATHER_CODES.get(current["weather_code"], "날씨 정보 확인 필요"),
        "temperature": current["temperature_2m"],
        "feels_like": current["apparent_temperature"],
        "rain_probability": int(rain_probability),
    }


def get_time_info(city: str) -> dict[str, Any]:
    """서울과 목적지의 현재 시각 및 시차를 계산한다."""
    place = geocode_city(city)
    seoul_now = datetime.now(ZoneInfo(ORIGIN["timezone"]))
    destination_now = datetime.now(ZoneInfo(place["timezone"]))
    difference = (destination_now.utcoffset() - seoul_now.utcoffset()).total_seconds() / 3600
    if difference == 0:
        description = "서울과 같은 시간"
    elif difference > 0:
        description = f"서울보다 {abs(difference):g}시간 빠름"
    else:
        description = f"서울보다 {abs(difference):g}시간 느림"
    return {
        "city": place["city"],
        "timezone": place["timezone"],
        "local_time": destination_now.strftime("%H:%M"),
        "time_difference": description,
    }


@st.cache_data(ttl=60 * 60, max_entries=100)
def get_exchange_info(city: str, amount_krw: int = 100_000) -> dict[str, Any]:
    """목적지 통화를 찾고 원화를 현지 통화로 환산한다."""
    catalog_name, catalog = find_catalog_city(city)
    place = geocode_city(catalog_name or city)
    currency = catalog["currency"] if catalog else COUNTRY_CURRENCIES.get(place["country_code"])
    if not currency:
        return {
            "city": catalog_name or place["city"], "currency": "확인 필요",
            "rate": None, "amount_krw": amount_krw, "converted_amount": None,
        }
    if currency == "KRW":
        rate = 1.0
    else:
        data = request_json(f"https://api.frankfurter.dev/v2/rate/KRW/{currency}")
        rate = float(data["rate"])
    return {
        "city": catalog_name or place["city"],
        "currency": currency,
        "rate": rate,
        "amount_krw": amount_krw,
        "converted_amount": round(amount_krw * rate, 2),
    }


def get_flight_info(city: str) -> dict[str, Any]:
    """서울 인천공항 출발 기준으로 통상적인 직항 노선 여부를 확인한다."""
    catalog_name, catalog = find_catalog_city(city)
    if not catalog:
        return {
            "city": city, "departure_airport": ORIGIN["airport"], "arrival_airport": "확인 필요",
            "direct_available": False, "stops": 1, "duration": "확인 필요",
            "note": "첫 버전의 항공 노선 데이터에 없는 도시입니다. 실제 일정은 항공사에서 확인하세요.",
        }
    direct = catalog["direct"]
    return {
        "city": catalog_name,
        "departure_airport": ORIGIN["airport"],
        "arrival_airport": catalog["airport"],
        "direct_available": direct,
        "stops": 0 if direct else 1,
        "duration": catalog["flight_hours"],
        "note": (
            "서울 출발 직항 노선이 통상 운항됩니다. 날짜별 편성은 항공사에서 다시 확인하세요."
            if direct else
            "서울 출발 직항 데이터가 없어 1회 이상 경유가 필요할 수 있습니다."
        ),
    }


def get_city_guide(city: str) -> dict[str, Any]:
    """큐레이션된 대표 명소와 현지 음식을 조회한다."""
    catalog_name, catalog = find_catalog_city(city)
    if not catalog:
        return {
            "city": city,
            "attractions": ["현지 중심가", "대표 박물관", "전통 시장"],
            "foods": ["현지 대표 요리", "지역 디저트", "전통 음료"],
            "tip": "아직 큐레이션되지 않은 도시라 방문 전 최신 현지 정보를 확인하세요.",
        }
    return {
        "city": catalog_name,
        "attractions": catalog["attractions"],
        "foods": catalog["foods"],
        "tip": f"{catalog_name}에서는 명소를 한 구역씩 묶어 이동하면 시간을 아낄 수 있어요.",
    }


def pick_random_city(preference: str = "완전 랜덤") -> dict[str, Any]:
    """여행 취향에 맞는 후보 중 도시 하나를 무작위로 고른다."""
    candidates = [
        name for name, data in DESTINATIONS.items()
        if preference == "완전 랜덤" or preference in data["themes"]
    ]
    if not candidates:
        candidates = list(DESTINATIONS)
    city = random.choice(candidates)
    return {"city": city, "preference": preference, "candidate_count": len(candidates)}


TOOL_FUNCS = {
    "get_city_weather": get_city_weather,
    "get_time_info": get_time_info,
    "get_exchange_info": get_exchange_info,
    "get_flight_info": get_flight_info,
    "get_city_guide": get_city_guide,
    "pick_random_city": pick_random_city,
}

TOOLS = [
    {"type": "function", "function": {
        "name": "get_city_weather",
        "description": "도시의 위치와 현재 날씨, 온도, 체감온도, 강수확률을 조회한다.",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "조회할 도시 이름"},
        }, "required": ["city"]},
    }},
    {"type": "function", "function": {
        "name": "get_time_info",
        "description": "목적지의 현재 시각과 서울과의 시차를 계산한다.",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "목적지 도시 이름"},
        }, "required": ["city"]},
    }},
    {"type": "function", "function": {
        "name": "get_exchange_info",
        "description": "목적지 통화의 원화 환율을 조회하고 지정한 원화를 현지 통화로 환산한다.",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "목적지 도시 이름"},
            "amount_krw": {"type": "integer", "description": "환산할 원화 금액"},
        }, "required": ["city", "amount_krw"]},
    }},
    {"type": "function", "function": {
        "name": "get_flight_info",
        "description": "인천공항 출발 기준 목적지 직항 여부와 일반적인 비행시간을 확인한다.",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "목적지 도시 이름"},
        }, "required": ["city"]},
    }},
    {"type": "function", "function": {
        "name": "get_city_guide",
        "description": "목적지의 대표 명소, 현지 음식, 여행 팁을 조회한다.",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "목적지 도시 이름"},
        }, "required": ["city"]},
    }},
    {"type": "function", "function": {
        "name": "pick_random_city",
        "description": "사용자가 도시를 고르지 못했을 때 여행 취향에 맞는 도시를 무작위로 하나 고른다.",
        "parameters": {"type": "object", "properties": {
            "preference": {
                "type": "string",
                "enum": ["완전 랜덤", "미식", "휴양", "자연", "도시", "예술", "역사", "야경", "가성비", "가까운 곳", "따뜻한 곳", "특별한 곳"],
            },
        }, "required": ["preference"]},
    }},
]

SYSTEM_PROMPT = """
너는 '어디든 떠나봇'이라는 한국어 여행 컨시어지다.
사용자가 특정 도시의 여행 정보를 요청하면 반드시 같은 도시로 다음 다섯 도구를 모두 호출한다:
get_city_weather, get_time_info, get_exchange_info, get_flight_info, get_city_guide.
get_exchange_info의 amount_krw는 사용자가 지정한 예산을 쓰고, 없으면 100000을 쓴다.
사용자가 랜덤 추천을 요청하면 먼저 pick_random_city를 호출하고, 그 결과로 선택된 도시에 대해 위 다섯 도구를 모두 호출한다.
도구가 준 현재 정보와 숫자를 임의로 바꾸지 않는다. 도구 호출이 끝나면 추천 이유를 포함해 3문장 이내로 친절하게 요약한다.
항공 정보는 실시간 좌석 검색이 아니라 일반 노선 안내임을 필요할 때 밝힌다.
""".strip()


def build_briefing(results: dict[str, dict[str, Any]]) -> TravelBriefing | None:
    required = {"get_city_weather", "get_time_info", "get_exchange_info", "get_flight_info", "get_city_guide"}
    if not required.issubset(results):
        return None
    weather = results["get_city_weather"]
    time_info = results["get_time_info"]
    exchange = results["get_exchange_info"]
    flight = results["get_flight_info"]
    guide = results["get_city_guide"]
    catalog_name, catalog = find_catalog_city(weather["city"])
    country = catalog["country"] if catalog else weather["country"]
    return TravelBriefing(
        city=catalog_name or weather["city"],
        country=country,
        local_time=time_info["local_time"],
        time_difference=time_info["time_difference"],
        currency=exchange["currency"],
        exchange_rate=exchange["rate"],
        converted_amount=exchange["converted_amount"],
        base_amount_krw=exchange["amount_krw"],
        weather=WeatherInfo(
            condition=weather["condition"],
            temperature=weather["temperature"],
            feels_like=weather["feels_like"],
            rain_probability=weather["rain_probability"],
        ),
        flight=FlightInfo(**{key: flight[key] for key in FlightInfo.model_fields}),
        attractions=guide["attractions"],
        foods=guide["foods"],
        travel_tip=guide["tip"],
    )


def run_bot(prompt: str, progress: Any) -> tuple[str, TravelBriefing | None, list[dict[str, Any]]]:
    client = OpenAI()
    st.session_state.api_messages.append({"role": "user", "content": prompt})
    collected: dict[str, dict[str, Any]] = {}
    trace: list[dict[str, Any]] = []
    answer = "여행 정보를 모두 모으지 못했어요. 질문을 조금 더 구체적으로 적어 주세요."

    for _ in range(8):
        response = client.chat.completions.create(
            model=API_MODEL,
            messages=st.session_state.api_messages,
            tools=TOOLS,
            max_completion_tokens=700,
        )
        message = response.choices[0].message
        st.session_state.api_messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            answer = message.content or answer
            break

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments)
                result = TOOL_FUNCS[name](**arguments)
                collected[name] = result
                trace.append({"name": name, "arguments": arguments, "result": result, "ok": True})
                progress.write(f":material/check_circle: `{name}` 완료")
                content = json.dumps(result, ensure_ascii=False)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                trace.append({"name": name, "arguments": tool_call.function.arguments, "result": error, "ok": False})
                progress.write(f":material/error: `{name}` 실패 — {exc}")
                content = json.dumps({"error": error}, ensure_ascii=False)
            st.session_state.api_messages.append({
                "role": "tool", "tool_call_id": tool_call.id, "content": content,
            })

    return answer, build_briefing(collected), trace


# ── 화면 ─────────────────────────────────────────────────────────────────

st.html("""
<style>
    :root { color-scheme: dark; }
    .stApp {
        color: #eef6ff;
        background:
            radial-gradient(circle at 82% -5%, rgba(34, 211, 238, .18), transparent 31rem),
            radial-gradient(circle at 5% 38%, rgba(124, 58, 237, .14), transparent 28rem),
            linear-gradient(145deg, #050811 0%, #07111c 52%, #050914 100%);
    }
    .stApp::before {
        content: ""; position: fixed; inset: 0; pointer-events: none; opacity: .12;
        background-image: radial-gradient(rgba(148, 213, 255, .8) .65px, transparent .65px);
        background-size: 9px 9px; mask-image: linear-gradient(to bottom, black, transparent 78%);
    }
    .block-container { max-width: 1180px; padding-top: 2rem; padding-bottom: 7rem; }
    [data-testid="stSidebar"] {
        background: rgba(5, 10, 21, .86); border-right: 1px solid rgba(148, 213, 255, .12);
        backdrop-filter: blur(18px);
    }
    .travel-hero {
        position: relative; overflow: hidden; min-height: 292px; display: flex; align-items: center;
        padding: 2.6rem 2.7rem; border: 1px solid rgba(148, 213, 255, .18); border-radius: 30px;
        background:
            linear-gradient(105deg, rgba(7, 17, 28, .96) 12%, rgba(9, 26, 42, .84) 58%, rgba(22, 78, 99, .36)),
            radial-gradient(circle at 80% 30%, rgba(34, 211, 238, .18), transparent 42%);
        box-shadow: 0 34px 100px rgba(0, 0, 0, .38), inset 0 1px 0 rgba(255, 255, 255, .06);
        margin-bottom: 1.15rem;
    }
    .travel-hero::after {
        content: ""; position: absolute; inset: 0; pointer-events: none; opacity: .2;
        background-image: radial-gradient(rgba(147, 231, 255, .9) .8px, transparent .9px);
        background-size: 7px 7px; mask-image: linear-gradient(90deg, transparent 42%, black 100%);
    }
    .hero-content { position: relative; z-index: 2; max-width: 710px; }
    .travel-kicker { display: flex; align-items: center; gap: .55rem; color: #7dd3fc;
        font-size: .72rem; font-weight: 800; letter-spacing: .19em; }
    .travel-kicker::before { content: ""; width: 7px; height: 7px; border-radius: 99px;
        background: #67e8f9; box-shadow: 0 0 18px #22d3ee; animation: status-pulse 2.2s ease-in-out infinite; }
    .travel-title { color: #f8fbff; font-size: clamp(2.7rem, 7vw, 5.4rem); line-height: .92;
        font-weight: 850; letter-spacing: -.065em; margin: .72rem 0 1.05rem; }
    .travel-subtitle { color: #9fb2c8; font-size: 1.02rem; line-height: 1.75; max-width: 640px; margin: 0; }
    .hero-tags { display: flex; flex-wrap: wrap; gap: .5rem; margin-top: 1.4rem; }
    .hero-tags span { padding: .34rem .62rem; border: 1px solid rgba(125, 211, 252, .17);
        border-radius: 999px; color: #b9ccdc; background: rgba(8, 20, 33, .54); font: 700 .66rem/1 monospace;
        letter-spacing: .08em; }
    .hero-radar { position: absolute; z-index: 1; right: 5%; top: 50%; width: 240px; aspect-ratio: 1;
        transform: translateY(-50%); border: 1px solid rgba(125, 211, 252, .17); border-radius: 50%; }
    .hero-radar::before, .hero-radar::after { content: ""; position: absolute; border-radius: 50%;
        border: 1px solid rgba(125, 211, 252, .14); inset: 20%; }
    .hero-radar::after { inset: 39%; background: rgba(34, 211, 238, .07); box-shadow: 0 0 45px rgba(34, 211, 238, .18); }
    .hero-radar-line { position: absolute; left: 50%; top: 50%; width: 48%; height: 1px;
        transform-origin: left center; background: linear-gradient(90deg, #67e8f9, transparent);
        animation: radar-sweep 7s linear infinite; }
    .hero-radar-code { position: absolute; inset: 0; display: grid; place-items: center; color: #dff9ff;
        font: 800 .7rem/1 monospace; letter-spacing: .18em; }
    .app-rail { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin: 0 .25rem .8rem;
        color: #668095; font: 750 .64rem/1 monospace; letter-spacing: .12em; }
    .app-rail-brand { display: flex; align-items: center; gap: .5rem; color: #b8cfde; }
    .app-rail-mark { width: 23px; height: 23px; display: grid; place-items: center; border: 1px solid rgba(103,232,249,.3);
        border-radius: 8px; color: #67e8f9; background: rgba(34,211,238,.07); }
    .app-rail-live { display: flex; align-items: center; gap: .45rem; }
    .app-rail-live::before { content: ""; width: 5px; height: 5px; border-radius: 50%; background: #34d399;
        box-shadow: 0 0 10px rgba(52,211,153,.9); }

    .route-card { position: relative; overflow: hidden; border: 1px solid rgba(125, 211, 252, .24);
        border-radius: 28px; padding: 1.7rem 1.9rem 1.45rem;
        background: linear-gradient(135deg, rgba(12, 31, 48, .96), rgba(7, 16, 29, .94));
        box-shadow: 0 24px 70px rgba(0, 0, 0, .3), inset 0 1px 0 rgba(255, 255, 255, .05);
        margin: .5rem 0 1.1rem; }
    .route-card::after { content: ""; position: absolute; width: 310px; height: 310px; right: -110px; top: -160px;
        border-radius: 50%; background: rgba(34, 211, 238, .09); filter: blur(22px); }
    .route-head { position: relative; z-index: 1; display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
    .route-label { color: #7dd3fc; letter-spacing: .15em; font: 800 .68rem/1 monospace; }
    .route-status { color: #bff7e4; border: 1px solid rgba(52, 211, 153, .27); background: rgba(6, 78, 59, .23);
        padding: .34rem .6rem; border-radius: 999px; font: 750 .65rem/1 monospace; letter-spacing: .08em; }
    .route-status.transfer { color: #fde68a; border-color: rgba(251, 191, 36, .28); background: rgba(120, 53, 15, .22); }
    .route-row { position: relative; z-index: 1; display: grid; grid-template-columns: minmax(100px, 1fr) minmax(170px, 2fr) minmax(100px, 1fr);
        align-items: center; gap: 1.4rem; margin-top: 1.35rem; }
    .route-code { display: inline-block; font: 900 clamp(2.7rem, 7vw, 5.6rem)/.92 ui-monospace, SFMono-Regular, Menlo, monospace;
        letter-spacing: -.09em; background-image: radial-gradient(circle, #e8fbff 1.2px, transparent 1.45px);
        background-size: 4px 4px; background-clip: text; -webkit-background-clip: text; color: transparent;
        filter: drop-shadow(0 0 10px rgba(103, 232, 249, .12)); }
    .route-destination { text-align: right; }
    .route-city { color: #8ea5ba; font-size: .78rem; letter-spacing: .05em; margin-top: .55rem; }
    .route-track { position: relative; height: 34px; }
    .route-track::before { content: ""; position: absolute; left: 5px; right: 5px; top: 16px; height: 1px;
        background: repeating-linear-gradient(90deg, #3d6377 0 5px, transparent 5px 10px); }
    .route-track::after { content: ""; position: absolute; left: 5px; top: 12px; width: 9px; height: 9px; border-radius: 50%;
        background: #67e8f9; box-shadow: calc(100% - 9px) 0 0 #67e8f9, 0 0 14px rgba(34, 211, 238, .75); }
    .route-plane { position: absolute; z-index: 2; top: 1px; left: 10%; color: #dffaff; font-size: 1.35rem;
        filter: drop-shadow(0 0 9px rgba(103, 232, 249, .7)); animation: route-fly 5.5s ease-in-out infinite alternate; }
    .route-footer { position: relative; z-index: 1; display: grid; grid-template-columns: repeat(3, 1fr); gap: .7rem;
        border-top: 1px solid rgba(148, 213, 255, .11); margin-top: 1.4rem; padding-top: 1rem; }
    .route-meta { min-width: 0; }
    .route-meta-label { color: #5f7a8e; font: 750 .61rem/1.2 monospace; letter-spacing: .12em; }
    .route-meta-value { color: #dcebf6; font-size: .82rem; font-weight: 650; margin-top: .35rem; white-space: nowrap;
        overflow: hidden; text-overflow: ellipsis; }

    .destination-reveal { display: flex; align-items: end; justify-content: space-between; gap: 1.5rem; margin: 1.7rem .15rem .9rem; }
    .destination-copy { min-width: 0; }
    .section-kicker { color: #5f7a8e; font: 800 .63rem/1 monospace; letter-spacing: .17em; margin-bottom: .55rem; }
    .flap-display { display: flex; flex-wrap: wrap; gap: .25rem; }
    .flap-cell { position: relative; min-width: 2.15rem; height: 2.7rem; display: grid; place-items: center; padding: 0 .38rem;
        border: 1px solid #263342; border-radius: 5px; color: #eafaff; background: linear-gradient(#19232e 49%, #0d141c 50%);
        box-shadow: inset 0 1px 0 rgba(255,255,255,.05), 0 7px 18px rgba(0,0,0,.22);
        font: 800 1.15rem/1 ui-monospace, SFMono-Regular, Menlo, monospace;
        animation: flap-in .55s cubic-bezier(.2,.8,.2,1) both; animation-delay: calc(var(--i) * 55ms); }
    .flap-cell::after { content: ""; position: absolute; left: 0; right: 0; top: 50%; height: 1px; background: #05090e;
        box-shadow: 0 1px 0 rgba(255,255,255,.025); }
    .destination-count { flex: 0 0 auto; color: #5f7a8e; font: 700 .65rem/1.5 monospace; text-align: right; }
    .destination-count strong { display: block; color: #d5e8f5; font-size: 1.05rem; }

    .insight-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: .75rem; margin-bottom: .85rem; }
    .insight-card { position: relative; overflow: hidden; min-height: 138px; padding: 1.05rem;
        border: 1px solid rgba(148,213,255,.13); border-radius: 19px;
        background: linear-gradient(145deg, rgba(14,29,45,.86), rgba(7,16,28,.8));
        box-shadow: inset 0 1px 0 rgba(255,255,255,.035); transition: transform .25s ease, border-color .25s ease; }
    .insight-card:hover { transform: translateY(-4px); border-color: rgba(103,232,249,.32); }
    .insight-card::after { content: ""; position: absolute; width: 95px; height: 95px; right: -35px; bottom: -50px;
        border-radius: 50%; background: var(--glow, rgba(34,211,238,.13)); filter: blur(4px); }
    .insight-icon { width: 30px; height: 30px; display: grid; place-items: center; border: 1px solid rgba(125,211,252,.16);
        border-radius: 9px; color: #83e6f5; background: rgba(34,211,238,.07); font: 800 .62rem/1 monospace; }
    .insight-label { color: #70899d; font: 800 .61rem/1 monospace; letter-spacing: .13em; margin-top: .9rem; }
    .insight-value { color: #f0f9ff; font-size: clamp(1.1rem, 2vw, 1.45rem); font-weight: 760; letter-spacing: -.035em;
        margin-top: .34rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .insight-detail { color: #849bae; font-size: .72rem; margin-top: .28rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

    .field-guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: .85rem; margin: .85rem 0; }
    .guide-panel { position: relative; overflow: hidden; padding: 1.25rem; border: 1px solid rgba(148,213,255,.14);
        border-radius: 22px; background: linear-gradient(145deg, rgba(13,27,43,.9), rgba(7,15,26,.84)); }
    .guide-panel.food { background: linear-gradient(145deg, rgba(39,28,24,.75), rgba(12,16,25,.88)); }
    .guide-panel::before { content: ""; position: absolute; width: 150px; height: 150px; right: -75px; top: -85px;
        border-radius: 50%; background: rgba(124,58,237,.15); filter: blur(12px); }
    .guide-panel.food::before { background: rgba(249,115,22,.13); }
    .guide-head { position: relative; display: flex; align-items: center; justify-content: space-between; margin-bottom: .75rem; }
    .guide-title { color: #eef8ff; font-size: 1rem; font-weight: 750; }
    .guide-index { color: #657e91; font: 700 .62rem/1 monospace; letter-spacing: .1em; }
    .pick-list { position: relative; display: grid; gap: .48rem; }
    .pick-row { display: grid; grid-template-columns: 34px 1fr auto; align-items: center; gap: .7rem; padding: .72rem .78rem;
        border: 1px solid rgba(148,213,255,.09); border-radius: 13px; background: rgba(2,8,18,.33);
        transition: transform .25s ease, background .25s ease, border-color .25s ease; }
    .pick-row:hover { transform: translateX(7px); background: rgba(14,37,55,.62); border-color: rgba(103,232,249,.22); }
    .guide-panel.food .pick-row:hover { background: rgba(67,37,24,.42); border-color: rgba(251,146,60,.22); }
    .pick-number { color: #7dd3fc; font: 800 .69rem/1 monospace; }
    .guide-panel.food .pick-number { color: #fdba74; }
    .pick-name { color: #cfdfeb; font-size: .84rem; font-weight: 620; }
    .pick-arrow { color: #50697c; font-size: .9rem; }
    .travel-tip-card { position: relative; overflow: hidden; display: grid; grid-template-columns: auto 1fr; gap: .9rem;
        align-items: center; padding: 1rem 1.1rem; margin: .85rem 0; border: 1px solid rgba(167,139,250,.2);
        border-radius: 18px; background: linear-gradient(100deg, rgba(76,29,149,.16), rgba(8,18,31,.55)); }
    .tip-mark { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 11px;
        color: #ddd6fe; background: rgba(124,58,237,.2); font: 800 .72rem/1 monospace; }
    .tip-label { color: #8d78bf; font: 800 .6rem/1 monospace; letter-spacing: .14em; }
    .tip-copy { color: #c9d8e4; font-size: .82rem; line-height: 1.55; margin-top: .3rem; }

    [data-testid="stMetric"] { border: 1px solid rgba(148, 213, 255, .13); border-radius: 18px;
        padding: 1rem 1.1rem; background: linear-gradient(145deg, rgba(13, 27, 43, .78), rgba(8, 17, 29, .72));
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, .035); }
    [data-testid="stMetric"] [data-testid="stMetricValue"] { color: #f0f9ff; letter-spacing: -.035em; }
    [data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: rgba(148, 213, 255, .14); background: rgba(8, 18, 31, .38); border-radius: 20px;
    }
    .st-key-random_panel, .st-key-spot_card, .st-key-food_card, .st-key-flight_note {
        box-shadow: inset 0 1px 0 rgba(255,255,255,.025);
    }
    [data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"] {
        background: rgba(3,10,20,.55); border-color: rgba(148,213,255,.15); border-radius: 12px;
    }
    [data-testid="stTextInputRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within {
        border-color: rgba(103,232,249,.52); box-shadow: 0 0 0 3px rgba(34,211,238,.08);
    }
    .stButton > button, .stFormSubmitButton > button { transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease; }
    .stButton > button:hover, .stFormSubmitButton > button:hover { transform: translateY(-2px); border-color: rgba(103,232,249,.55);
        box-shadow: 0 10px 30px rgba(6,182,212,.14); }

    @keyframes status-pulse { 50% { opacity: .45; transform: scale(.78); } }
    @keyframes radar-sweep { to { transform: rotate(360deg); } }
    @keyframes route-fly { from { left: 9%; } to { left: calc(91% - 1.35rem); } }
    @keyframes flap-in { from { opacity: 0; transform: rotateX(-75deg) translateY(-5px); } to { opacity: 1; transform: none; } }
    @media (prefers-reduced-motion: reduce) { .travel-kicker::before, .hero-radar-line, .route-plane, .flap-cell { animation: none; } }
    @media (max-width: 760px) {
        .travel-hero { min-height: 250px; padding: 1.8rem; }
        .hero-radar { width: 185px; right: -42px; opacity: .48; }
        .travel-subtitle { max-width: 78%; font-size: .92rem; }
        .route-card { padding: 1.35rem; }
        .route-row { grid-template-columns: 1fr; gap: .5rem; }
        .route-destination { text-align: left; }
        .route-track { width: 100%; }
        .route-footer { grid-template-columns: 1fr 1fr; }
        .destination-reveal { align-items: start; }
        .destination-count { display: none; }
        .insight-grid { grid-template-columns: 1fr 1fr; }
        .field-guide-grid { grid-template-columns: 1fr; }
        .flap-cell { min-width: 1.8rem; height: 2.3rem; font-size: .95rem; }
    }
    @media (max-width: 430px) {
        .app-rail > span:last-child { display: none; }
        .insight-grid { grid-template-columns: 1fr; }
        .travel-subtitle { max-width: 92%; }
    }
</style>
""")

if "api_messages" not in st.session_state:
    st.session_state.api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "briefing" not in st.session_state:
    st.session_state.briefing = None
if "tool_trace" not in st.session_state:
    st.session_state.tool_trace = []

with st.sidebar:
    st.subheader("여행 설정")
    st.selectbox("출발지", ["서울 · 인천국제공항 (ICN)"], disabled=True)
    budget = st.number_input(
        "환산할 여행 예산", min_value=10_000, max_value=10_000_000,
        value=100_000, step=10_000, format="%d",
    )
    st.caption(f"서울 출발 기준 · 현재 {len(DESTINATIONS)}개 도시 지원")
    with st.expander("지원 도시 전체 보기", icon=":material/location_city:"):
        st.caption(" · ".join(sorted(DESTINATIONS)))
    if st.button("대화와 결과 초기화", icon=":material/refresh:", width="stretch"):
        st.session_state.api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        st.session_state.chat_history = []
        st.session_state.briefing = None
        st.session_state.tool_trace = []
        st.rerun()

st.html("""
<div class="app-rail">
  <div class="app-rail-brand"><span class="app-rail-mark">A</span><span>ANYWHERE DESK</span></div>
  <div class="app-rail-live"><span>LIVE DATA</span></div>
  <span>SEOUL · KOREA / 37.46°N</span>
</div>
<section class="travel-hero">
  <div class="hero-content">
    <div class="travel-kicker">AI TRAVEL CONCIERGE · LIVE</div>
    <div class="travel-title">어디든<br>떠나봇</div>
    <p class="travel-subtitle">가고 싶은 도시 하나면 충분해요. 지금 날씨부터 시차, 환율, 항공편, 먹거리까지 한 장의 브리핑으로 정리합니다.</p>
    <div class="hero-tags"><span>WEATHER LIVE</span><span>FX RATE</span><span>ROUTE CHECK</span><span>LOCAL PICKS</span></div>
  </div>
  <div class="hero-radar" aria-hidden="true"><span class="hero-radar-line"></span><span class="hero-radar-code">ICN · 37.46°N</span></div>
</section>
""")

direct_prompt = None
random_prompt = None

with st.form("destination_form", border=True):
    input_col, submit_col = st.columns([4, 1], vertical_alignment="bottom")
    destination = input_col.text_input("어디로 떠나고 싶나요?", placeholder="예: 맨체스터, 바르셀로나, 도쿄")
    submitted = submit_col.form_submit_button(
        "브리핑 만들기", icon=":material/arrow_forward:", type="primary", width="stretch",
    )
    if submitted and destination.strip():
        direct_prompt = f"서울에서 {destination.strip()}로 가고 싶어. {budget}원을 현지 통화로 환산해서 여행 브리핑을 만들어 줘."

with st.container(border=True, key="random_panel"):
    st.markdown("#### :material/casino: 도시를 못 정했다면")
    st.caption("취향을 하나 고르면 지원 도시 중 오늘의 목적지를 뽑아 드려요.")
    preference = st.pills(
        "여행 취향",
        ["완전 랜덤", "미식", "휴양", "자연", "도시", "예술", "역사", "야경", "가성비", "가까운 곳", "따뜻한 곳", "특별한 곳"],
        default="완전 랜덤",
        label_visibility="collapsed",
    )
    if st.button("운명에 맡기기", icon=":material/casino:", width="stretch"):
        random_prompt = f"{preference or '완전 랜덤'} 취향으로 도시를 무작위로 골라 줘. {budget}원을 현지 통화로 환산해 줘."

chat_prompt = st.chat_input(
    "예: 비슷하지만 더 따뜻한 도시로 바꿔줘",
    key="travel_chat_input",
    submit_mode="disable",
)
prompt = direct_prompt or random_prompt or chat_prompt

if prompt:
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.status("여행 도구를 준비하고 있어요", expanded=True) as progress:
        try:
            answer, briefing, trace = run_bot(prompt, progress)
            if briefing:
                st.session_state.briefing = briefing.model_dump()
            st.session_state.tool_trace = trace
            progress.update(label="여행 브리핑이 준비됐어요", state="complete", expanded=False)
        except Exception as exc:
            answer = f"브리핑을 만들지 못했어요: {exc}"
            progress.update(label="여행 정보를 불러오지 못했어요", state="error", expanded=True)
    st.session_state.chat_history.append({"role": "assistant", "content": answer})

if st.session_state.briefing:
    brief = TravelBriefing.model_validate(st.session_state.briefing)
    origin_code = html.escape(brief.flight.departure_airport)
    destination_code = html.escape(brief.flight.arrival_airport)
    city_label = html.escape(f"{brief.city}, {brief.country}")
    route_status = "DIRECT" if brief.flight.direct_available else "TRANSFER"
    route_status_ko = "직항 노선" if brief.flight.direct_available else "경유 필요"
    route_status_class = "" if brief.flight.direct_available else " transfer"
    flap_cells = "".join(
        f'<span class="flap-cell" style="--i:{index}">{html.escape(character)}</span>'
        for index, character in enumerate(brief.city.replace(" ", "·"))
    )
    st.space("medium")
    st.html(f"""
    <section class="route-card">
      <div class="route-head">
        <div class="route-label">FLIGHT BRIEF · {route_status}</div>
        <div class="route-status{route_status_class}">{route_status_ko}</div>
      </div>
      <div class="route-row">
        <div><div class="route-code">{origin_code}</div><div class="route-city">Seoul, Korea</div></div>
        <div class="route-track"><span class="route-plane" aria-hidden="true">&#9992;</span></div>
        <div class="route-destination"><div class="route-code">{destination_code}</div><div class="route-city">{city_label}</div></div>
      </div>
      <div class="route-footer">
        <div class="route-meta"><div class="route-meta-label">LOCAL TIME</div><div class="route-meta-value">{html.escape(brief.local_time)}</div></div>
        <div class="route-meta"><div class="route-meta-label">TIME SHIFT</div><div class="route-meta-value">{html.escape(brief.time_difference)}</div></div>
        <div class="route-meta"><div class="route-meta-label">FLIGHT TIME</div><div class="route-meta-value">{html.escape(brief.flight.duration)}</div></div>
      </div>
    </section>
    """)

    converted = "확인 필요" if brief.converted_amount is None else f"{brief.converted_amount:,.2f} {brief.currency}"
    attraction_rows = "".join(
        f'<div class="pick-row"><span class="pick-number">{index:02d}</span><span class="pick-name">{html.escape(item)}</span><span class="pick-arrow">↗</span></div>'
        for index, item in enumerate(brief.attractions, 1)
    )
    food_rows = "".join(
        f'<div class="pick-row"><span class="pick-number">{index:02d}</span><span class="pick-name">{html.escape(item)}</span><span class="pick-arrow">↗</span></div>'
        for index, item in enumerate(brief.foods, 1)
    )
    st.html(f"""
    <section class="destination-reveal">
      <div class="destination-copy"><div class="section-kicker">DESTINATION UNLOCKED</div><div class="flap-display">{flap_cells}</div></div>
      <div class="destination-count"><strong>{html.escape(brief.country)}</strong>YOUR FIELD GUIDE · 01</div>
    </section>
    <section class="insight-grid">
      <article class="insight-card"><div class="insight-icon">LT</div><div class="insight-label">LOCAL TIME</div><div class="insight-value">{html.escape(brief.local_time)}</div><div class="insight-detail">{html.escape(brief.time_difference)}</div></article>
      <article class="insight-card" style="--glow:rgba(14,165,233,.15)"><div class="insight-icon">WX</div><div class="insight-label">WEATHER NOW</div><div class="insight-value">{brief.weather.temperature:g} °C</div><div class="insight-detail">{html.escape(brief.weather.condition)} · 체감 {brief.weather.feels_like:g} °C</div></article>
      <article class="insight-card" style="--glow:rgba(59,130,246,.15)"><div class="insight-icon">RN</div><div class="insight-label">RAIN CHANCE</div><div class="insight-value">{brief.weather.rain_probability}%</div><div class="insight-detail">현재 시간대 기준</div></article>
      <article class="insight-card" style="--glow:rgba(124,58,237,.16)"><div class="insight-icon">FX</div><div class="insight-label">{brief.base_amount_krw:,} KRW</div><div class="insight-value">{html.escape(converted)}</div><div class="insight-detail">현재 환율 기준 환산</div></article>
    </section>
    <section class="field-guide-grid">
      <article class="guide-panel">
        <div class="guide-head"><div class="guide-title">이곳이 재미있는 이유</div><div class="guide-index">SPOTS · 03</div></div>
        <div class="pick-list">{attraction_rows}</div>
      </article>
      <article class="guide-panel food">
        <div class="guide-head"><div class="guide-title">이곳에서 꼭 먹을 것</div><div class="guide-index">TASTES · 03</div></div>
        <div class="pick-list">{food_rows}</div>
      </article>
    </section>
    <aside class="travel-tip-card">
      <div class="tip-mark">TIP</div>
      <div><div class="tip-label">LOCAL NOTE</div><div class="tip-copy">{html.escape(brief.travel_tip)}</div></div>
    </aside>
    """)

    with st.container(border=True, key="flight_note"):
        badge_color = "green" if brief.flight.direct_available else "orange"
        badge_text = "직항 가능" if brief.flight.direct_available else "경유 필요 가능성"
        with st.container(horizontal=True, vertical_alignment="center"):
            st.badge(badge_text, icon=":material/flight:", color=badge_color)
            st.markdown(f"**{brief.flight.departure_airport} → {brief.flight.arrival_airport}** · {brief.flight.duration}")
        st.caption(brief.flight.note)

if st.session_state.chat_history:
    st.space("medium")
    st.subheader("컨시어지와 나눈 대화")
    with st.container(height=300, border=True):
        for chat in st.session_state.chat_history:
            avatar = ":material/person:" if chat["role"] == "user" else ":material/travel_explore:"
            with st.chat_message(chat["role"], avatar=avatar):
                st.write(chat["content"])

if st.session_state.tool_trace:
    with st.expander("이번 브리핑에 사용한 도구", icon=":material/build:"):
        for item in st.session_state.tool_trace:
            icon = ":material/check_circle:" if item["ok"] else ":material/error:"
            st.markdown(f"{icon} **{item['name']}**")
            st.json({"입력": item["arguments"], "결과": item["result"]}, expanded=False)

st.caption("날씨·환율은 조회 시점 기준이며, 항공편은 일반 노선 안내입니다. 실제 예약 전 항공사 최신 일정을 확인하세요.")
