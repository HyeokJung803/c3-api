from openai import OpenAI

client = OpenAI()
API_MODEL = "gpt-5.4-nano"

# 멀티턴 대화 기억용. 여기에 계속 대화가 추가됨
messages = [
    {"role": "system", "content": "너는 친절한 대화 봇이야. 3문장 이내로만 답해" },
]
total_tokens = 0
print("AI와 대화해요. 나가시려면 exit 입력해주세요.")
while True:
    user_input = input("\nuser > ")
    if user_input == "exit":
        break
    # 사용자 입력을 목록에 덧붙인다.
    messages.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model=API_MODEL,
        messages=messages,
        max_completion_tokens=300,
    )
    answer = response.choices[0].message.content
    # 응답받은 결과를 목록에 추가
    messages.append({"role": "assistant", "content": answer})
    total_tokens += response.usage.total_tokens

    # AI의 응답과 토큰 수를 확인
    print(f"\nAI > {answer}  ({response.usage.total_tokens}/{total_tokens})") 