import json
import random
import re

import streamlit as st
from openai import OpenAI


st.set_page_config(page_title="AI 끝말잇기", layout="centered")

st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(1200px 600px at 50% -10%, #1a1440 0%, #0b0e2a 45%, #05060f 100%);
        color: #e7e9ff;
    }
    [data-testid="stHeader"] {
        background: transparent;
    }
    [data-testid="stSidebar"] {
        background: rgba(10, 12, 32, 0.88);
        border-right: 1px solid rgba(167, 139, 250, 0.18);
    }
    .block-container {
        max-width: 760px;
        padding-top: 2.5rem;
        padding-bottom: 6rem;
    }
    html, body, [class*="css"] {
        font-family: "Pretendard", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
        letter-spacing: -0.01em;
    }
    .app-title {
        font-size: 2.5rem;
        font-weight: 800;
        text-align: center;
        margin-bottom: 0.35rem;
        background: linear-gradient(90deg, #a78bfa 0%, #60a5fa 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .app-subtitle {
        text-align: center;
        color: #9aa0c7;
        font-size: 0.98rem;
        margin-bottom: 1.8rem;
        line-height: 1.6;
    }
    .glass-card {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(167, 139, 250, 0.22);
        border-radius: 18px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 1.2rem;
        backdrop-filter: blur(8px);
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
    }
    .status-card {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        text-align: center;
        margin-bottom: 0;
    }
    .st-key-status_bar {
        position: sticky;
        top: 0.75rem;
        z-index: 999;
        padding-bottom: 1.2rem;
    }
    .st-key-status_bar::before {
        content: "";
        position: absolute;
        inset: -0.75rem -0.5rem 0.4rem -0.5rem;
        z-index: -1;
        background: linear-gradient(180deg, #0b0e2a 72%, rgba(11, 14, 42, 0));
        pointer-events: none;
    }
    .status-item {
        flex: 1;
    }
    .status-label {
        font-size: 0.8rem;
        color: #8b91bd;
        margin-bottom: 0.4rem;
    }
    .status-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #e7e9ff;
    }
    .status-value.accent {
        color: #a78bfa;
    }
    .status-divider {
        width: 1px;
        background: rgba(167, 139, 250, 0.25);
    }
    [data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.045);
        border: 1px solid rgba(167, 139, 250, 0.18);
        border-radius: 14px;
        padding: 0.8rem 1rem;
    }
    [data-testid="stChatMessage"] {
        background: rgba(255, 255, 255, 0.045);
        border: 1px solid rgba(167, 139, 250, 0.16);
        border-radius: 18px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.8rem;
    }
    [data-testid="stChatMessageAvatarUser"],
    [data-testid="stChatMessageAvatarAssistant"] {
        display: none;
    }
    [data-testid="stChatMessageContent"] {
        padding-left: 0;
    }
    [data-testid="stChatInput"] {
        border: 1px solid rgba(167, 139, 250, 0.4);
        border-radius: 16px;
        background: #10142c;
    }
    .stButton > button {
        border-radius: 12px;
        border: 1px solid rgba(167, 139, 250, 0.4);
        background: linear-gradient(135deg, #7c3aed 0%, #6366f1 100%);
        color: #ffffff;
        font-weight: 700;
        transition: transform 0.1s ease, box-shadow 0.1s ease;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 8px 20px rgba(124, 58, 237, 0.35);
        border-color: rgba(167, 139, 250, 0.7);
        color: #ffffff;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="app-title">AI 끝말잇기</div>'
    '<div class="app-subtitle">길게 이을수록 점수가 커집니다. '
    '제한 없이 최고 기록에 도전하세요.</div>',
    unsafe_allow_html=True,
)

API_MODEL = "gpt-5.4-nano"
START_WORDS = [
    "사과", "과자", "자동차", "학교", "고양이", "이야기", "기차", "바다",
    "다리", "리본", "노래", "도서관", "강아지", "사진", "나무", "우산",
    "시장", "장미", "미술관", "하늘", "늘보", "보석", "석양", "양말",
]

# 앞 단어의 마지막 글자에 두음법칙을 적용한 첫 글자도 인정한다.
DOOEUM = {
    "냐": "야", "녀": "여", "녜": "예", "뇨": "요", "뉴": "유", "니": "이",
    "라": "나", "락": "낙", "란": "난", "람": "남", "랑": "낭", "래": "내",
    "랴": "야", "려": "여", "력": "역", "련": "연", "렬": "열", "렴": "염",
    "령": "영", "례": "예", "로": "노", "롱": "농", "뢰": "뇌", "료": "요",
    "루": "누", "류": "유", "륙": "육", "르": "느", "리": "이", "린": "인",
    "림": "임", "립": "입",
}


def clean_word(word: str) -> str:
    """점수와 규칙 검사에 쓸 수 있도록 공백과 문장부호를 제거한다."""
    return re.sub(r"[^0-9A-Za-z가-힣]", "", word).strip()


def allowed_first_letters(last_letter: str) -> set[str]:
    letters = {last_letter}
    if last_letter in DOOEUM:
        letters.add(DOOEUM[last_letter])
    return letters


def reset_game() -> None:
    previous_word = st.session_state.get("current_word")
    candidates = [word for word in START_WORDS if word != previous_word]
    start_word = random.choice(candidates)
    st.session_state.score = 0
    st.session_state.high_score = st.session_state.get("high_score", 0)
    st.session_state.used_words = [clean_word(start_word)]
    st.session_state.current_word = start_word
    st.session_state.game_over = False
    st.session_state.chat_log = [
        {"role": "assistant", "content": f"제가 먼저 시작할게요. **{start_word}**"}
    ]


def finish_game(reason: str) -> None:
    st.session_state.game_over = True
    st.session_state.high_score = max(
        st.session_state.high_score, st.session_state.score
    )
    st.session_state.chat_log.append(
        {
            "role": "assistant",
            "content": f"{reason}\n\n게임 종료. 최종 점수는 **{st.session_state.score}점**입니다.",
        }
    )


def ask_ai(user_word: str) -> dict:
    """입력 단어를 판정하고 다음 AI 단어를 JSON으로 받는다."""
    used = ", ".join(st.session_state.used_words + [user_word])
    last_letter = user_word[-1]
    possible_starts = ", ".join(sorted(allowed_first_letters(last_letter)))

    system_prompt = """
너는 한국어 끝말잇기 심판이자 참가자다.

[인정하는 단어]
- 실제로 존재하는 일반 명사
- 과학, 의학, 화학, 법률, 공학 등에서 실제로 쓰이는 학술 용어와 전문 용어
- 여러 명사가 붙은 긴 합성 명사와 사전식 붙여쓰기로 등록된 긴 단어
- 널리 알려진 유명인의 정확한 실명 또는 활동명
- 널리 알려진 방송 프로그램, 영화, 드라마의 정확한 제목

[인정하지 않는 단어]
- 문장, 조사나 어미가 붙은 표현, 임의로 만든 말
- 정확성을 확인하기 어려운 지나치게 생소한 이름이나 제목
- 오타가 있거나 존재하지 않는 단어

단어가 길거나 생소하다는 이유만으로 무효 처리하지 마라.
전문 용어의 실제 사용 가능성이 높다면 유효한 것으로 판정하라.
판정이 확실하지 않을 때는 사용자의 단어를 인정하라.
예를 들어 '기체크로마토질량분석법'은 유효한 전문 용어로 인정한다.

사용자 단어가 인정되면 그 단어의 마지막 글자로 시작하는 다음 단어를 하나 골라라.
두음법칙을 적용한 시작 글자도 가능하다. 이미 사용한 단어는 절대 고르지 마라.
AI도 위의 인정 규칙을 지켜야 한다.

반드시 설명이나 마크다운 없이 아래 형식의 JSON 객체 하나만 출력하라.
{"valid": true, "reason": "짧은 판정 이유", "ai_word": "다음 단어"}
사용자 단어가 무효이면 ai_word는 빈 문자열로 출력하라.
"""
    user_prompt = f"""
사용자가 낸 단어: {user_word}
AI가 다음에 낼 수 있는 첫 글자: {possible_starts}
지금까지 사용한 단어: {used}
"""

    client = OpenAI()
    response = client.chat.completions.create(
        model=API_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=500,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


if "score" not in st.session_state:
    reset_game()

with st.sidebar:
    st.header("게임 현황")
    st.metric("현재 점수", f"{st.session_state.score}점")
    st.metric("최고 점수", f"{st.session_state.high_score}점")
    st.write(f"사용한 단어: **{len(st.session_state.used_words)}개**")
    if st.button("새 게임", use_container_width=True):
        reset_game()
        st.rerun()

    st.divider()
    st.subheader("규칙")
    st.markdown(
        """
        - 앞 단어의 마지막 글자로 시작
        - 두음법칙 허용
        - 같은 단어 재사용 금지
        - 한 글자 단어 금지
        - 전문용어와 긴 합성명사 허용
        - 유명인·프로그램·영화·드라마 허용
        - 공백과 문장부호를 뺀 글자 수만큼 득점
        - 점수 상한 없음
        """
    )

    with st.expander("사용한 단어 목록"):
        for index, used_word in enumerate(st.session_state.used_words, start=1):
            st.write(f"{index}. {used_word}")

current_word = st.session_state.current_word
start_letters = " / ".join(sorted(allowed_first_letters(current_word[-1])))
with st.container(key="status_bar"):
    st.markdown(
        f"""
        <div class="glass-card status-card">
            <div class="status-item">
                <div class="status-label">현재 AI 단어</div>
                <div class="status-value">{current_word}</div>
            </div>
            <div class="status-divider"></div>
            <div class="status-item">
                <div class="status-label">시작해야 하는 글자</div>
                <div class="status-value accent">{start_letters}</div>
            </div>
            <div class="status-divider"></div>
            <div class="status-item">
                <div class="status-label">현재 점수</div>
                <div class="status-value">{st.session_state.score}점</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

for message in st.session_state.chat_log:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if st.session_state.game_over:
    st.info("사이드바의 ‘새 게임’ 버튼을 눌러 다시 도전하세요.")

prompt = st.chat_input(
    f"‘{st.session_state.current_word[-1]}’(으)로 시작하는 단어",
    disabled=st.session_state.game_over,
)

if prompt:
    display_word = prompt.strip()
    word = clean_word(display_word)
    st.session_state.chat_log.append({"role": "user", "content": display_word})

    expected = st.session_state.current_word[-1]
    allowed = allowed_first_letters(expected)

    if len(word) < 2:
        finish_game("두 글자 이상의 단어를 입력해야 해요.")
    elif word in st.session_state.used_words:
        finish_game(f"**{display_word}**은(는) 이미 사용한 단어예요.")
    elif word[0] not in allowed:
        choices = " 또는 ".join(f"‘{letter}’" for letter in sorted(allowed))
        finish_game(f"{choices}(으)로 시작하는 단어가 아니에요.")
    else:
        try:
            with st.spinner("AI가 단어를 확인하고 있어요..."):
                result = ask_ai(word)

            if not result.get("valid", False):
                reason = result.get("reason", "인정할 수 없는 단어예요.")
                finish_game(f"**{display_word}**: {reason}")
            else:
                ai_display_word = str(result.get("ai_word", "")).strip()
                ai_word = clean_word(ai_display_word)
                ai_allowed = allowed_first_letters(word[-1])

                if (
                    len(ai_word) < 2
                    or ai_word in st.session_state.used_words
                    or ai_word == word
                    or ai_word[0] not in ai_allowed
                ):
                    raise ValueError("AI가 규칙에 맞는 다음 단어를 만들지 못했습니다.")

                earned_score = len(word)
                st.session_state.score += earned_score
                st.session_state.high_score = max(
                    st.session_state.high_score, st.session_state.score
                )
                st.session_state.used_words.extend([word, ai_word])
                st.session_state.current_word = ai_word
                st.session_state.chat_log.append(
                    {
                        "role": "assistant",
                        "content": (
                            f"**+{earned_score}점** · 현재 {st.session_state.score}점\n\n"
                            f"제 단어는 **{ai_display_word}**"
                        ),
                    }
                )
        except Exception as error:
            st.session_state.chat_log.append(
                {
                    "role": "assistant",
                    "content": (
                        "AI 응답을 처리하지 못했어요. 점수나 차례는 바뀌지 않았으니 "
                        f"다시 입력해 주세요.\n\n`{error}`"
                    ),
                }
            )

    st.rerun()
