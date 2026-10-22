# Agent LLM Interface — Client Developer Documentation

## Introduction

Agents call LLMs and other AI models through two libraries:

| Library | Package | Use it for |
|---|---|---|
| **LLM Interface** | `agents_llm` (`libs/llm-interface`) | Full inference client. Calls AIOS **blocks** over gRPC or REST, AIOS **vDAGs**, OpenAI, or custom backends. Supports `infer`, chat completions, completions, multipart inference, async calls, block pre/post-processing policies, latency metrics and LLM-based selection |
| **LLM Interface Lite** | `agents_llm_lite` (`libs/llm-interface-lite`) | A simple prompt-in / text-out registry of inference providers (AIOS or OpenAI). Includes generate-and-execute for code |

A typical workflow is:

1. **Declare a ModelItem** in the Subject Specification (optional) to record which models the agent uses.
2. **Create a client** and **register one or more backends** under names.
3. **Run inference** by backend name.

---

## Registering LLMs in Subject Specification

Models can be recorded in the subject's `integrations.models` list using `ModelItem`.

### Data Class Reference

```python
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class ModelItem:
    llm_type: str
    llm_block_id: str
    llm_selection_query: Dict[str, Any] = field(default_factory=dict)
    llm_parameters: Dict[str, Any] = field(default_factory=dict)
```

### Example Configuration

```json
{
  "llm_type": "inference",
  "llm_block_id": "gemma3-27b-block",
  "llm_selection_query": {},
  "llm_parameters": {
    "network_host": "34.93.251.223",
    "inference_server_id": "inference-server-1",
    "mode": "auto"
  }
}
```

### Field Descriptions

| Field                     | Type   | Description                                                                 |
| ------------------------- | ------ | --------------------------------------------------------------------------- |
| **llm\_type**             | `str`  | Model kind, e.g. `"inference"`.                                             |
| **llm\_block\_id**        | `str`  | AIOS block ID (model) or provider model name.                               |
| **llm\_selection\_query** | `dict` | Optional selector for picking a deployment.                                 |
| **llm\_parameters**       | `dict` | Backend settings, e.g. `network_host`, `inference_server_id`, `mode`.       |

> The agents SDK does not build LLM clients from `ModelItem` entries automatically. Read them from `self.subject.integrations.models` and register backends yourself (see below).

---

# Part 1 — `agents_llm` (LLM Interface)

## Import and Setup

```python
from agents_llm import AIGridClient
from agents_llm.custom import AbstractBlockInferenceSystem, OpenAIBlockInferenceSystem

client = AIGridClient()
```

`AIGridClient` keeps a registry of **inference systems** by name. Methods called without `name=` use the system registered as `"default"`.

---

## Registering Backends

### A. AIOS block (gRPC or REST)

```python
client.add_block(
    name="gemma",
    network_host="34.93.251.223",            # host of the AIOS registries
    inference_server_id="inference-server-1",
    model="gemma3-27b-block",                # block ID
    mode="auto",                             # "auto" | "grpc" | "rest"
)
```

How the block is resolved:

1. **Inference server.** If `inference_server_id` is set, the server record is fetched from the inference server registry at `http://<network_host>:30105`. Its `inference_server_urls` give the REST URL (`rest` / `http` / `https`, else `inference_server_public_url`) and the gRPC address (`grpc` / `grpc_address` / `grpc_url`).
2. **Direct URLs.** If `inference_server_id=""`, pass `urls={"rest": "http://...:31504"}` and/or `urls={"grpc": "host:port"}` instead.
3. **Transport.** `mode="auto"` picks gRPC when available, else REST. Asking for a transport that isn't available raises `RuntimeError`.
4. **Block data.** The block record is fetched from the blocks registry at `http://<network_host>:30100`. If it defines policies named `agents_pre_processing` / `agents_post_processing`, they run on every request payload and response.

```python
# Direct REST URL, no inference server registry lookup
client.add_block(
    name="gemma-rest",
    network_host="34.93.251.223",
    inference_server_id="",
    model="gemma3-27b-block",
    mode="rest",
    urls={"rest": "http://35.232.150.117:31504"},
)
```

`default_headers` (optional) are sent to the inference server registry.

### B. AIOS vDAG

```python
client.add_vdag(
    name="pipeline",
    registry_base_url="http://<vdag-controller-registry>",
    vdag_uri="my-vdag:1.0-stable",
    mode="auto",
)
```

All vDAG controllers registered for `vdag_uri` are listed and one is picked at random. Its REST and gRPC endpoints come from `config.urls` (`rest`/`http`/`https`, else `public_url`; `grpc`, else `config.grpc_address`/`config.grpc_url`).

### C. OpenAI

```python
openai_llm = OpenAIBlockInferenceSystem(
    model="gpt-4o-mini",          # default
    api_key=None,                 # default: OPENAI_API_KEY (required)
    base_url=None,                # optional OpenAI-compatible endpoint
    organization=None,
    project=None,
)
client.add_custom_block(name="openai", system=openai_llm)
```

* Only OpenAI-supported keys are forwarded from `data`. Chat: `messages, temperature, top_p, max_tokens, n, stop, presence_penalty, frequency_penalty, logit_bias, user, tools, tool_choice, response_format, seed, metadata`. Text: the same, minus `tools`/`tool_choice`/`response_format`, plus `prompt`.
* `infer()` routes to chat when `data` contains `messages` (or is a list of role/content dicts), and to text completions when it contains `prompt` (or is a string or list). If the model does not support text completions, the call is retried as a chat completion.
* Multipart inference is not supported.

### D. Custom backends

See [Writing a Custom Backend](#writing-a-custom-backend).

### Managing backends

```python
client.list()            # ['gemma', 'openai', ...]
system = client.get("gemma")
client.remove("gemma")
```

---

## Running Inference

### Chat completions

```python
resp = client.chat_completions(
    name="openai",
    session_id="sess-001",
    messages=[{"role": "user", "content": "Explain quantum computing in one paragraph."}],
    data={"temperature": 0.2, "max_tokens": 256},
)
print(resp["choices"][0]["message"]["content"])
```

For AIOS blocks, `messages` is merged into `data` (`data["messages"] = messages`). The pre-processing policy (if any) runs on `data`, and the result is sent to `POST /v1/chat/completions` (REST) or the gRPC `chat_completions` call. Generation settings for the block go in `data`, for example:

```python
resp = client.chat_completions(
    name="gemma-rest",
    session_id="session-1214",
    messages=[{"role": "user", "content": "What is 2 + 2?"}],
    data={
        "mode": "chat",
        "generation_config": {"max_new_tokens": 512, "do_sample": False, "top_p": 0.95, "temperature": 1.0},
    },
)
```

### Completions

```python
resp = client.completions(name="gemma", session_id="sess-002",
                          prompts="Write a haiku about the ocean", data={})
```

For AIOS blocks, always pass a dict as `data` (the prompt is added to it as `data["prompt"]`).

> `client.completions(...)` currently fails with a `TypeError` for OpenAI and other custom systems: `AIGridClient` always passes `data=`, which `AbstractBlockInferenceSystem.completions` does not accept. Call the system directly instead — `client.get("openai").completions(prompt="...", session_id="sess-002")` — or use chat completions.

### Raw inference

```python
resp = client.infer(name="gemma", session_id="sess-003", data={"mode": "chat", "message": "Hello"})
```

For AIOS blocks this calls `POST /v1/infer` (or gRPC `infer`) with `model`, `session_id`, `seq_no`, `data`, `files`, `graph` and `selection_query`.

### Multipart inference (files)

```python
resp = client.infer_multipart(name="gemma-rest", session_id="sess-004", data={"mode": "vision"})
```

Multipart is only available over REST (`POST /v1/infer-multipart`).

### Full-parameter calls

The simplified methods above always send `seq_no=0` and no `files`, `graph`, `selection_query`, `frame_ptr` or `output_ptr`. To set these, use the `internal_*` methods. They pass keyword arguments straight to the backend:

```python
client.internal_infer(
    name="gemma",
    session_id="sess-005",
    seq_no=7,
    data={"mode": "chat", "message": "Describe this image"},
    files=["/tmp/cat.png"],
    selection_query={},
    graph={},
)
```

> vDAG systems take a smaller set of arguments (for example, `infer(session_id, seq_no, data, files, frame_ptr, ts)`), so call them through `internal_*` methods or `client.get(name)` rather than the simplified methods.

### Async calls

Every call has an async variant (`async_infer`, `async_chat_completions`, `async_completions`, `async_infer_multipart`, plus `internal_async_*`). Each runs in a background thread and returns a `ResultWaiter`:

```python
waiter = client.async_chat_completions(
    name="openai",
    session_id="sess-006",
    messages=[{"role": "user", "content": "What is 2 + 2?"}],
    data={},
)
waiter.ready()                 # True once finished
resp = waiter.wait(timeout=30) # raises TimeoutError, or re-raises the call's exception
```

### Metrics

Each system keeps rolling latency metrics:

```python
client.get("gemma").get_metrics()
# {"count": 12, "last_latency": 0.41, "min_latency": 0.32, "max_latency": 1.2, "avg_latency": 0.47}
```

---

## LLM-based Selection (`SelectionEngine`)

`SelectionEngine` asks a model to pick the single best candidate for a query. Candidates are any objects with an `id` and a `get_searchable_representation()` method.

```python
from dataclasses import dataclass
from typing import List

@dataclass
class Shoe:
    id: str
    title: str
    tags: List[str]

    def get_searchable_representation(self) -> str:
        return f"title={self.title}; tags={','.join(self.tags)}"

engine = client.create_selector(name="openai", base_query="Select the best product for the user.")

result = engine.select(
    entities=[Shoe("A1", "Red Running Shoes", ["running"]), Shoe("B2", "Trail Shoes", ["trail"])],
    user_query="I need running shoes for daily jogging.",
    session_id="sess-007",
    extra_data={"max_tokens": 64},
)
result.selected_id   # "A1"
result.raw_json      # {"id": "A1"}
```

The engine sends a chat completion with strict JSON-only instructions and `response_format={"type": "json_object"}`, `temperature=0.0`, `max_tokens=32` (overridable through `extra_data`). It parses `{"id": ...}` from the reply. `ValueError` is raised if the reply isn't valid JSON or the ID is not one of the candidates.

---

## Writing a Custom Backend

Subclass `AbstractBlockInferenceSystem` and implement the four `_do_*` hooks. The base class provides the public `infer` / `chat_completions` / `completions` / `infer_multipart` methods, their async variants, and latency metrics.

```python
from typing import Any, Dict, List, Optional
from agents_llm.custom import AbstractBlockInferenceSystem


class EchoLLM(AbstractBlockInferenceSystem):
    def __init__(self):
        super().__init__(model="echo")

    def _do_infer(self, *, session_id, seq_no, data, files, selection_query, graph, frame_ptr, output_ptr):
        return {"reply": data}

    def _do_chat_completions(self, *, messages, session_id, seq_no, selection_query, graph,
                             frame_ptr, output_ptr, data=None):
        last = messages[-1]["content"] if messages else ""
        return {"choices": [{"message": {"role": "assistant", "content": last}}]}

    def _do_completions(self, *, prompt, session_id, seq_no, selection_query, graph,
                        frame_ptr, output_ptr, data=None):
        return {"choices": [{"text": prompt}]}

    def _do_infer_multipart(self, *, session_id, seq_no, data, ts, frame_ptr, files):
        raise RuntimeError("not supported")


client.add_custom_block(name="echo", system=EchoLLM())
```

Optional hooks:

* `_finalize_mode()` — resolve `mode` (`"auto"` → `"grpc"`/`"rest"`) at construction.
* `_check_mode(operation)` — reject operations the transport doesn't support.

---

## Block Discovery

`BlockSearchClient` queries the AIOS search service for blocks:

```python
from agents_llm.discovery import BlockSearchClient

search = BlockSearchClient("http://<search-service>")
search.filter_query(filter={"tags": "llm"})                          # POST /api/filter
search.search(policyRuleURI="policies/rank-blocks:1.0-stable",       # POST /api/search
              filter={"tags": "llm"}, policy_params={})
```

---

# Part 2 — `agents_llm_lite` (LLM Interface Lite)

`agents_llm_lite` is a registry of simple text-generation providers. Every provider implements:

```python
infer(*, prompt, callback, temperature=0.1, top_p=0.95, max_tokens=4096, system_message=None, **kwargs) -> str
```

`callback(raw_response) -> str` extracts the text from the provider's raw response. Markdown fences are stripped from the result.

```python
from agents_llm_lite.inference import AgentInferenceManager
from agents_llm_lite.custom import BaseInference, OpenAIInference

llm = AgentInferenceManager()
```

### AIOS provider

```python
llm.register_new_inference(
    name="aios",
    model="magistral-small-2506-llama-cpp-block",
    inference_server_id="http://35.232.150.117:31504",   # or a registry ID
    aios_url_map={"inference_server_url": "http://<registry>", "blocks_db_url": "http://<blocks-db>"},
    system_message="You are a concise assistant.",
)

text = llm.infer(
    name="aios",
    prompt="Summarize the benefits of vector databases.",
    callback=lambda raw: raw["data"]["reply"],
)
```

The request is `POST /v1/infer` with `data = {"mode": "chat", "gen_params": {temperature, top_p, max_tokens}, "message": prompt, "system_message": ...}`.

### OpenAI provider

```python
llm.register_custom_inference(name="openai", provider=OpenAIInference(model="gpt-4o-mini"))

text = llm.infer(
    name="openai",
    prompt="Write a haiku about the ocean",
    callback=lambda resp: resp.choices[0].message.content,
)
```

`OpenAIInference` uses `OPENAI_API_KEY` unless you pass `client=OpenAI(...)`. It sends `max_tokens` as `max_completion_tokens`, and does not forward `temperature` or `top_p`.

### Generate and execute

`infer_and_execute` works like the [Code Generator SDK](agent-code-generator.md)'s `generate_and_execute`: it generates code, installs declared requirements, loads the code as a module, and calls `main` (or `class_name().method_name`, or a single callable class):

```python
result = llm.infer_and_execute(
    name="aios",
    prompt="Write `def main(a, b)` returning the element-wise sum of two lists.",
    callback=lambda raw: raw["data"]["reply"],
    args=[[1, 2], [3, 4]],
)
```

### Managing providers

```python
llm.list_inferences()
llm.has_inference("openai")
llm.get_inference("openai")
llm.unregister_inference("openai")
llm.clear_inferences()
```

Custom providers subclass `BaseInference` (keyword-only `model`, `session_id`, `logger`, `default_system_message`) and implement `infer`. Lite providers can also be used as the `llm` of `AgentRAG` (see [Accessing Vector Databases](agent-vector-storage.md)).

---

## Best Practices

* Keep API keys in environment variables (`OPENAI_API_KEY`) rather than in code or subject specs.
* Use `async_*` calls with `ResultWaiter.wait(timeout=...)` to bound waiting time.
* Use block pre/post-processing policies to adapt payloads per model without changing agent code.
* Use `get_metrics()` to monitor backend latency.
