from typing import List
from openai import OpenAI
from pydantic import BaseModel

client = OpenAI()
API_MODEL= "gpt-5.4-nano"

class Question(BaseModel):
    question: str
    choices: List[str]               # 보기 4개
    answer: int                      # 1~4
    explanation: str

class Quiz(BaseModel):
    questions: List[Question]

topic = input("퀴즈 주제를 정해주세요. > ").strip()
print(f"\n{topic}과 관련된 퀴즈를 만드는 중입니다...")

rq = client.chat.completions.parse(
    model=API_MODEL,
    messages=[
        {"role": "system", "content": "객관식 퀴즈를 만든다. 보기는 4개, 정답번호는 1~4."},
        {"role": "user", "content": f"주제: {topic}, 4문항."},   # 주제를 바꾸면 내 퀴즈가 된다
    ],
    response_format=Quiz,
    max_completion_tokens=1200,
)
quiz = rq.choices[0].message.parsed # 퀴즈

score = 0

for i, q in enumerate(quiz.questions, 1):
    print(f"\nQ{i}. {q.question}")
    for j, opt in enumerate(q.choices, 1):
        print(f"   {j}) {opt}")
    try:
        pick = int(input("답을 입력해주세요 (1,2,3,4) >"))
    except ValueError:
        pick = 0
    if pick == q.answer: # 정답을 맞췄을 경우
        score += 1
        print("축하합니다, 정답을 맞추셨습니다!")
    else:
        print(f"아깝습니다, 정답은 {q.answer}입니다.")
        print(f"해설: {q.explanation}")
print(f"{score} 개 맞추셨습니다!")