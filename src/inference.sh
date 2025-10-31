curl -X POST  http://35.232.150.117:31504/v1/infer \
  -H "Content-Type: application/json" \
  -d '{
  "model": "magistral-small-2506-vllm-block",
  "session_id": "session-234",
  "seq_no": 23,
  "data": {
    "mode": "generate",
    "generation_config": {
      "temperature": 0.7,
      "repetition_penalty": 1.0,
      "min_p": 0.01,
      "top_k": -1,
      "top_p": 0.95,
      "max_tokens": 512 
    },
    "prompt": "Give me code for adding two integers list element wise in python",
    "system_message": "You are a helpful assistant that provides code examples."
  },
  "graph": {},
  "files": {},
  "selection_query": {}
}'
