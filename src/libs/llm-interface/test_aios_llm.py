from agents_llm import AIGridClient
from agents_llm.custom import OpenAIBlockInferenceSystem

llm_ai = AIGridClient()


llm_ai.add_block(
    network_host="34.58.1.86",
    inference_server_id="",
    model="qwen3-1-7b-vllm-block",
    mode="rest",
    block_data={},
    default_headers={},
    urls={
        "rest": "http://35.232.150.117:31504"
    }
)

waiter = llm_ai.async_chat_completions(session_id="session-12133", messages=[
    {"role": "user", "content": "What is 2 + 2?"}
], data={
    "mode": "chat",
    "generation_config": {
        "top_k": 50,
        "top_p": 0.95,
        "temperature": 1.0
    },
})

waiter = llm_ai.async_infer(session_id="session-x8", data={
    "mode": "generate",
    "generation_config": {
        "max_tokens": 512,
        "top_k": 50,
        "top_p": 0.95,
        "temperature": 1.0
    },
    "prompt": "Hello, how are you?",
    "system_message": "You are a helpful assistant."
})

print(waiter.wait())
