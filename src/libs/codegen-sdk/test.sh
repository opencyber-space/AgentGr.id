curl -X POST  http://35.232.150.117:31504/v1/infer \
    -H "Content-Type: application/json" \
    -d '{

  "model": "magistral-small-2506-llama-cpp-block",

  "session_id": "session-2",

  "seq_no": 16,
  "files": {},

  "data": {

    "mode": "chat",

    "gen_params": {

      "temperature": 0.1,

      "top_p": 0.95,

      "max_tokens": 4096

    },

    "message": "Give me code for adding two integers list element wise in python, no additional text and only code has to be provided",

    "system_message": "You are a helpful assistant that provides code examples."

  },

  "graph": {},

  "selection_query": {

  }

}'