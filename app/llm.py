from typing import Iterator

from ollama import Client

OLLAMA_HOST = "http://localhost:11434"
LLM_MODEL = "qwen3:8b"

client = Client(host=OLLAMA_HOST)

def generate_answer(
    system_prompt: str,
    user_prompt: str
) -> str:
    
    response = client.chat(
        model=LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
            
        ],
        options={
            "temperature": 0.0,
        },
        think=True
    )
    
    return response["message"]["content"]


def stream_answer(
    system_prompt: str,
    user_prompt: str
) -> Iterator[str]:
    
    response = client.chat(
        model=LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        options={
            "temperature": 0.0
        },
        # Same generation settings as generate_answer(), which is what the
        # evaluation measures. Thinking arrives in message["thinking"] and
        # is not streamed to the client; only answer content is.
        think=True,
        stream=True,
    )
    
    for chunk in response:
        content = chunk["message"]["content"]
        
        if content:
            yield content


def complete(
    system_prompt: str,
    user_prompt: str,
    *,
    think: bool = False,
) -> str:
    
    response = client.chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        options={"temperature": 0.0},
        think=think,
    )
    return response["message"]["content"]