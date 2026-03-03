from agents_llm import AIGridClient
from agents_llm import OpenAIBlockInferenceSystem

llm_ai = AIGridClient()


llm_ai.add_block(
    registry_base_url="http://34.58.1.86:30100",
    inference_server_id="",
    model="gemma3-27b-block",
    mode="rest",
    block_data={},
    default_headers={},
    urls={
        "rest": "http://35.232.150.117:31504"
    }
)

waiter = llm_ai.async_chat_completions(session_id="session-1214", messages=[
    {"role": "user", "content": "What is 2 + 2?"}
], data={
    "mode": "chat",
    "generation_config": {
        "max_new_tokens": 512,
        "do_sample": False,
        "top_k": 50,
        "top_p": 0.95,
        "temperature": 1.0
    },
})

print(waiter.wait())


