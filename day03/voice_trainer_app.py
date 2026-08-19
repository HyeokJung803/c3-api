"""AI Voice Trainer — Responses API와 TTS로 만드는 맞춤 운동 코치."""

import io
import json
import os
import re
import zipfile
import streamlit as st
from openai import OpenAI
from pydantic import BaseModel, Field


st.set_page_config(
    page_title="AI 보이스 트레이너",
    page_icon=":material/fitness_center:",
    layout="wide",
)


TEXT_MODEL = "gpt-5.6-luna"
TTS_MODEL = "gpt-4o-mini-tts"
VOICE_LABELS = {
    "marin": "Marin · 밝고 힘찬 코치",
    "cedar": "Cedar · 차분하고 단단한 코치",
    "coral": "Coral · 친근한 코치",
    "alloy": "Alloy · 균형 잡힌 코치",
}
SESSION_EXERCISES = {20: 3, 30: 4, 45: 5, 60: 6}


class Exercise(BaseModel):
    name: str = Field(description="한국어 운동명")
    target_muscles: list[str] = Field(min_length=1, max_length=4)
    equipment: str
    sets: int = Field(ge=2, le=5)
    reps: str = Field(description="예: 10회 또는 30초")
    rest_seconds: int = Field(ge=30, le=180)
    estimated_minutes: int = Field(ge=3, le=10)
    form_steps: list[str] = Field(min_length=2, max_length=4)
    focus: str
    caution: str
    coaching_script: str = Field(
        description="운동명, 세트 수, 자세, 집중 부위, 안전 주의를 담은 자연스러운 한국어 TTS 대본"
    )


class WorkoutPlan(BaseModel):
    title: str
    summary: str
    warmup: list[str] = Field(min_length=2, max_length=4)
    exercises: list[Exercise]
    cooldown: list[str] = Field(min_length=2, max_length=4)
    total_minutes: int


@st.cache_resource
def get_client() -> OpenAI:
    return OpenAI()


def output_item_types(response: object) -> list[str]:
    """output_text가 비었을 때 확인할 Responses API 출력 타입 목록."""
    return [getattr(item, "type", type(item).__name__) for item in getattr(response, "output", [])]


def build_plan_prompt(
    *,
    goal: str,
    level: str,
    minutes: int,
    place: str,
    body_parts: list[str],
    equipment: list[str],
    notes: str,
) -> str:
    exercise_count = SESSION_EXERCISES[minutes]
    return f"""
당신은 안전을 우선하는 한국어 피트니스 코치다. 아래 조건으로 근력 운동 루틴을 설계하라.

- 목표: {goal}
- 운동 경험: {level}
- 전체 시간: {minutes}분
- 장소: {place}
- 집중 부위: {', '.join(body_parts)}
- 사용 가능 장비: {', '.join(equipment)}
- 피하고 싶은 동작 또는 참고 사항: {notes or '없음'}
- 본운동 종목 수: 정확히 {exercise_count}개

요구사항:
1. 준비운동과 마무리운동을 포함하고 전체 시간이 {minutes}분에 가깝게 구성한다.
2. 각 본운동은 준비와 휴식을 포함해 약 4~7분이 되게 한다.
3. 초보자도 이해할 수 있는 짧고 구체적인 자세 설명을 쓴다.
4. 통증을 참고 운동하라고 안내하지 말고, 날카롭거나 비정상적인 통증이 있으면 즉시 중단하도록 한다.
5. 참고 사항에 부상이나 질환이 있더라도 진단·치료·재활 처방을 하지 말고 전문가 확인을 권한다.
6. coaching_script는 실제 코치가 말하듯 작성한다. 반드시 운동명, 총 세트 수, 반복 수,
   시작 자세, 동작 방법, 집중 부위, 호흡, 휴식 시간과 안전 주의를 포함한다.
7. 과장된 효과나 보장 표현을 사용하지 않는다.
""".strip()


def generate_plan(prompt: str) -> tuple[WorkoutPlan, list[str]]:
    response = get_client().responses.parse(
        model=TEXT_MODEL,
        instructions="운동 계획을 요청한 구조에 맞춰 한국어로 작성한다.",
        input=prompt,
        text_format=WorkoutPlan,
        text={"verbosity": "low"},
    )
    diagnostics = output_item_types(response)
    if response.output_parsed is None:
        raise RuntimeError(
            "구조화된 운동 계획이 비어 있습니다. "
            f"output 아이템 타입: {diagnostics or ['없음']}"
        )
    return response.output_parsed, diagnostics


def generate_speech(exercise: Exercise, voice: str, coach_style: str) -> bytes:
    style_instructions = {
        "활기차게": "밝고 힘찬 한국어 피트니스 코치처럼 말한다. 중요한 자세 포인트는 또렷하게 강조한다.",
        "차분하게": "차분하고 안정적인 한국어 피트니스 코치처럼 천천히 또렷하게 말한다.",
        "엄격하게": "절도 있고 집중력 있는 한국어 피트니스 코치처럼 말하되 위협적이지 않게 한다.",
    }
    speech = get_client().audio.speech.create(
        model=TTS_MODEL,
        voice=voice,
        instructions=style_instructions[coach_style],
        input=exercise.coaching_script,
        response_format="mp3",
    )
    return speech.content


def safe_filename(name: str, index: int) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", name).strip("_")
    return f"{index:02d}_{cleaned or 'exercise'}.mp3"


def make_audio_zip(plan: WorkoutPlan, audio_files: dict[int, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, exercise in enumerate(plan.exercises, start=1):
            if index in audio_files:
                archive.writestr(safe_filename(exercise.name, index), audio_files[index])
        archive.writestr(
            "routine.json",
            json.dumps(plan.model_dump(), ensure_ascii=False, indent=2),
        )
    return buffer.getvalue()


def reset_result() -> None:
    st.session_state.plan = None
    st.session_state.audio_files = {}
    st.session_state.diagnostics = []


st.session_state.setdefault("plan", None)
st.session_state.setdefault("audio_files", {})
st.session_state.setdefault("diagnostics", [])


with st.sidebar:
    st.subheader("음성 코치 설정")
    voice = st.selectbox(
        "코치 목소리",
        options=list(VOICE_LABELS),
        format_func=VOICE_LABELS.get,
        key="voice",
    )
    coach_style = st.segmented_control(
        "말투",
        options=["활기차게", "차분하게", "엄격하게"],
        default="활기차게",
        key="coach_style",
    )
    st.caption("생성되는 목소리는 실제 트레이너가 아닌 AI 음성입니다.")
    if st.button("결과 초기화", icon=":material/refresh:", width="stretch"):
        reset_result()
        st.rerun()


st.title("AI 보이스 트레이너")
st.write("내 조건에 맞는 근력 루틴을 만들고, 종목별 자세 안내를 MP3로 들어보세요.")

with st.container(horizontal=True):
    st.badge("Responses API", icon=":material/neurology:", color="blue")
    st.badge("구조화된 출력", icon=":material/data_object:", color="violet")
    st.badge("AI 음성 MP3", icon=":material/graphic_eq:", color="green")

st.caption(
    "이 서비스는 일반적인 운동 정보만 제공합니다. 통증, 부상 또는 질환이 있다면 운동 전 전문가와 상담하세요."
)


with st.form("routine_form", border=True):
    st.subheader("오늘의 운동 조건")
    first, second = st.columns(2)
    with first:
        goal = st.selectbox("운동 목표", ["근력 향상", "근육량 증가", "체력 관리", "체중 관리"])
        level = st.segmented_control(
            "운동 경험",
            ["입문", "초급", "중급"],
            default="초급",
        )
        minutes = st.segmented_control(
            "운동 시간",
            [20, 30, 45, 60],
            default=30,
            format_func=lambda value: f"{value}분",
        )
    with second:
        place = st.selectbox("운동 장소", ["헬스장", "집", "야외"])
        body_parts = st.multiselect(
            "집중 부위",
            ["전신", "가슴", "등", "어깨", "팔", "하체", "코어"],
            default=["전신"],
        )
        equipment = st.multiselect(
            "사용 가능 장비",
            ["맨몸", "덤벨", "바벨", "케틀벨", "밴드", "벤치", "머신"],
            default=["맨몸", "덤벨"],
        )
    notes = st.text_input(
        "피하고 싶은 동작 또는 참고 사항",
        placeholder="예: 점프 동작 제외, 손목에 부담이 큰 동작 제외",
        max_chars=200,
    )
    submitted = st.form_submit_button(
        "AI 루틴 만들기",
        type="primary",
        icon=":material/auto_awesome:",
        width="stretch",
    )


if submitted:
    if not body_parts or not equipment:
        st.error("집중 부위와 사용 가능 장비를 하나 이상 선택해 주세요.", icon=":material/error:")
    elif minutes not in SESSION_EXERCISES:
        st.error("지원하는 운동 시간을 선택해 주세요.", icon=":material/error:")
    elif coach_style not in {"활기차게", "차분하게", "엄격하게"}:
        st.error("코치 말투를 선택해 주세요.", icon=":material/error:")
    elif not os.getenv("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY 환경 변수가 필요합니다.", icon=":material/key:")
    else:
        reset_result()
        prompt = build_plan_prompt(
            goal=goal,
            level=level,
            minutes=minutes,
            place=place,
            body_parts=body_parts,
            equipment=equipment,
            notes=notes.strip(),
        )
        try:
            with st.status("AI가 운동 루틴을 설계하고 있어요", expanded=True) as status:
                status.write("운동 조건을 확인했습니다.")
                plan, diagnostics = generate_plan(prompt)
                status.write("세트, 반복 수와 자세 포인트를 구성했습니다.")
                status.update(label="운동 루틴이 완성됐습니다", state="complete", expanded=False)
            st.session_state.plan = plan.model_dump()
            st.session_state.diagnostics = diagnostics
            st.toast("맞춤 운동 루틴을 만들었습니다.", icon=":material/check_circle:")
        except Exception as exc:
            st.error(f"운동 루틴 생성에 실패했습니다: {exc}", icon=":material/error:")


if st.session_state.plan:
    plan = WorkoutPlan.model_validate(st.session_state.plan)

    st.space("medium")
    st.subheader(plan.title)
    st.write(plan.summary)

    metrics = st.columns(3)
    metrics[0].metric("전체 시간", f"약 {plan.total_minutes}분")
    metrics[1].metric("본운동", f"{len(plan.exercises)}종목")
    metrics[2].metric("음성 준비", f"{len(st.session_state.audio_files)}/{len(plan.exercises)}")

    warmup_col, cooldown_col = st.columns(2)
    with warmup_col.container(border=True, height="stretch"):
        st.markdown("#### :material/directions_run: 준비운동")
        for item in plan.warmup:
            st.write(f"- {item}")
    with cooldown_col.container(border=True, height="stretch"):
        st.markdown("#### :material/self_improvement: 마무리운동")
        for item in plan.cooldown:
            st.write(f"- {item}")

    st.space("small")
    with st.container(horizontal=True, horizontal_alignment="right"):
        generate_all = st.button(
            "모든 MP3 만들기",
            type="primary",
            icon=":material/record_voice_over:",
            disabled=len(st.session_state.audio_files) == len(plan.exercises),
        )

    if generate_all:
        if coach_style not in {"활기차게", "차분하게", "엄격하게"}:
            st.error("코치 말투를 선택해 주세요.")
        else:
            try:
                with st.status("종목별 AI 음성을 만들고 있어요", expanded=True) as status:
                    for index, exercise in enumerate(plan.exercises, start=1):
                        if index not in st.session_state.audio_files:
                            status.write(f"{index}. {exercise.name} 음성 생성 중")
                            st.session_state.audio_files[index] = generate_speech(
                                exercise, voice, coach_style
                            )
                    status.update(label="모든 MP3가 완성됐습니다", state="complete", expanded=False)
                st.toast("종목별 MP3 생성을 완료했습니다.", icon=":material/check_circle:")
                st.rerun()
            except Exception as exc:
                st.error(f"음성 생성에 실패했습니다: {exc}", icon=":material/error:")

    for index, exercise in enumerate(plan.exercises, start=1):
        with st.container(border=True):
            heading, timing = st.columns([4, 1], vertical_alignment="center")
            heading.markdown(f"### {index}. {exercise.name}")
            timing.metric("예상 시간", f"약 {exercise.estimated_minutes}분")

            st.markdown(
                f"**{exercise.sets}세트 × {exercise.reps}** · "
                f"세트 사이 **{exercise.rest_seconds}초 휴식** · {exercise.equipment}"
            )
            st.caption("집중 부위 · " + " · ".join(exercise.target_muscles))

            detail_col, focus_col = st.columns([3, 2])
            with detail_col:
                st.markdown("**자세 순서**")
                for step_number, step in enumerate(exercise.form_steps, start=1):
                    st.write(f"{step_number}. {step}")
            with focus_col:
                st.markdown("**집중 포인트**")
                st.write(exercise.focus)
                st.warning(exercise.caution, icon=":material/health_and_safety:")

            audio = st.session_state.audio_files.get(index)
            if audio:
                st.audio(audio, format="audio/mpeg")
                st.download_button(
                    "MP3 다운로드",
                    data=audio,
                    file_name=safe_filename(exercise.name, index),
                    mime="audio/mpeg",
                    key=f"download_{index}",
                    icon=":material/download:",
                    on_click="ignore",
                )
            elif st.button(
                f"{exercise.name} 음성 만들기",
                key=f"speech_{index}",
                icon=":material/volume_up:",
            ):
                try:
                    with st.spinner(f"{exercise.name} 코칭 음성을 만들고 있어요"):
                        st.session_state.audio_files[index] = generate_speech(
                            exercise, voice, coach_style
                        )
                    st.rerun()
                except Exception as exc:
                    st.error(f"음성 생성에 실패했습니다: {exc}")

            with st.expander("AI 코칭 대본", icon=":material/description:"):
                st.write(exercise.coaching_script)

    if st.session_state.audio_files:
        st.download_button(
            "완성된 MP3와 루틴을 ZIP으로 받기",
            data=make_audio_zip(plan, st.session_state.audio_files),
            file_name="ai_voice_trainer.zip",
            mime="application/zip",
            type="primary",
            icon=":material/folder_zip:",
            width="stretch",
            on_click="ignore",
        )

    with st.expander("API 응답 진단", icon=":material/monitor_heart:"):
        st.caption("output_text 또는 구조화된 출력이 비었을 때 먼저 확인할 Responses API 아이템 타입입니다.")
        st.code("\n".join(st.session_state.diagnostics) or "output 아이템 없음")


st.caption("운동 중 날카롭거나 비정상적인 통증, 어지러움 또는 호흡 곤란이 있으면 즉시 중단하세요.")
