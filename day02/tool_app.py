# 260818 §4-7 — 브라우저에서 도구가 도는 챗봇 (금요일 app.py 의 확장)
# 실행: streamlit run tool_app.py   (종료는 터미널에서 Ctrl+C)
# tool_chat.py 와 다른 것은 그릇뿐 — 도구·왕복 루프는 한 글자도 다르지 않다.
import json
import re
import urllib.request

import streamlit as st
from openai import OpenAI

st.title("도구 달린 챗봇")          # 내 것으로 바꿔도 된다

client = OpenAI()
API_MODEL = "gpt-5.4-nano"

# ── 도구 두 개 — tool_chat.py 와 동일 ──────────────────────────────────

def get_weather(city: str, latitude: float, longitude: float) -> str:
    """그 좌표의 지금 날씨를 open-meteo 에서 가져온다 (키 불필요)"""
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}"
           f"&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m&timezone=auto")
    with urllib.request.urlopen(url, timeout=10) as resp:
        c = json.load(resp)["current"]
    return (f"{city} 기온 {c['temperature_2m']}도, 습도 {c['relative_humidity_2m']}%, "
            f"강수 {c['precipitation']}mm, 바람 {c['wind_speed_10m']}m/s")

def calc(expression: str) -> str:
    """수식을 계산한다. 모델이 준 문자열이므로 허용 문자 검사부터 (02_tools.py §7)"""
    if not re.fullmatch(r"[0-9+\-*/(). %]+", expression) or "**" in expression or len(expression) > 80:
        return "허용되지 않는 수식이라 계산을 거부했다"
    return str(eval(expression, {"__builtins__": {}}, {}))

TOOL_FUNCS = {"get_weather": get_weather, "calc": calc}

tools = [
    {"type": "function", "function": {
        "name": "get_weather",
        "description": "그 도시의 지금 날씨를 알려 준다. 위도·경도는 네가 아는 값을 채워라.",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "도시 이름"},
            "latitude": {"type": "number", "description": "그 도시의 위도"},
            "longitude": {"type": "number", "description": "그 도시의 경도"},
        }, "required": ["city", "latitude", "longitude"]},
    }},
    {"type": "function", "function": {
        "name": "calc",
        "description": "수식을 정확하게 계산한다. 예: 739521468 * 8462137",
        "parameters": {"type": "object", "properties": {
            "expression": {"type": "string", "description": "계산할 수식"},
        }, "required": ["expression"]},
    }},
]

# ── 여기부터는 금요일의 app.py 그대로 + ②만 루프로 ─────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": "너는 친절한 비서야. 세 문장 이내로 답해."},
    ]

# 재실행될 때마다 지금까지의 대화를 처음부터 다시 그린다
# (system 과 도구 왕복 조각은 건너뛴다 — 말풍선은 사람과 모델의 '말'만)
for msg in st.session_state.messages:
    # 배열에는 내가 만든 딕셔너리와 모델이 준 요청서 객체가 섞여 있다 — 꺼내는 법이 달라서 갈라 본다
    role = msg["role"] if isinstance(msg, dict) else msg.role
    content = msg["content"] if isinstance(msg, dict) else msg.content
    if role in ("user", "assistant") and content:
        st.chat_message(role).write(content)

prompt = st.chat_input("날씨나 계산을 물어보세요")
if prompt:
    # ① 내 말을 배열 뒤에 붙이고 화면에도 그린다 (금요일 그대로)
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # ② 배열을 통째로 보낸다 — tool_chat.py 와 같은 왕복 루프
    for _ in range(5):
        response = client.chat.completions.create(
            model=API_MODEL,
            messages=st.session_state.messages,
            tools=tools,
            max_completion_tokens=500,
        )
        msg = response.choices[0].message
        if not msg.tool_calls:
            break

        st.session_state.messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = TOOL_FUNCS[tc.function.name](**args)
            st.caption(f"[도구] {tc.function.name}({args}) → {result}")   # 왕복이 화면에도 보이게
            st.session_state.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    # 상한 5바퀴를 다 돌고도 말 답이 없으면 None 이 배열에 실려 다음 턴이 400 난다 — 빈 답을 막는다
    answer = msg.content or "(도구 왕복이 상한에 걸렸다 — 질문을 나눠서 다시 물어보자)"

    # ③ 모델의 답도 배열 뒤에 붙이고 화면에 그린다 (금요일 그대로)
    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.chat_message("assistant").write(answer)