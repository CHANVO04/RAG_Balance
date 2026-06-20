from query.clients import get_llm_client
from query.config import LLM_MODEL

def generate_answer(system_prompt: str, user_prompt: str) -> str:
    print("[LLM] Đang tổng hợp câu trả lời...")
    llm = get_llm_client()
    
    response = llm.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        max_tokens=1024
    )
    
    return response.choices[0].message.content
