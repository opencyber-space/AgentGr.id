# Code Generator SDK — Client Developer Documentation

## Introduction

The **Code Generator SDK** (`agents_codegen`) lets agents generate code with an LLM and, optionally, execute it at runtime.

It provides:

* **Pluggable backends**:
    * **AIOS** — code models served as AIOS blocks, called over REST (`AIOSCodeGeneratorAPI`).
    * **OpenAI** — the OpenAI Chat Completions API (`OpenAICodeGenerator`).
    * **Custom** — your own subclass of `BaseCodeGenerator`.
* **A registry** (`AgentCodeGenerator`) for addressing generators by name.
* **Generate-and-execute**: generate Python, install its declared dependencies, load it as a module and call a function or method from it.

Markdown code fences (```` ```python … ``` ````) are stripped from generated code automatically.

---

## Installation

The SDK lives in `libs/codegen-sdk` (package `agents_codegen`). It has no `setup.py`, so add `libs/codegen-sdk` to `PYTHONPATH` or copy the package into your agent. It depends on `openai` and `requests`.

## Import and Setup

```python
from agents_codegen.generator import AgentCodeGenerator
from agents_codegen.aios import AIOSCodeGeneratorAPI, CodeGenerationError
from agents_codegen.custom import BaseCodeGenerator, OpenAICodeGenerator

codegen = AgentCodeGenerator()
```

---

## Using the AIOS Backend

Register a generator backed by an AIOS code model:

```python
codegen.register_new_code_generator(
    name="aios-default",
    model="magistral-small-2506-llama-cpp-block",       # block ID of the model
    inference_server_id="inference-server-1",           # or a direct URL: "http://35.232.150.117:31504"
    aios_url_map={
        "inference_server_url": "http://<inference-server-registry>",
        "blocks_db_url": "http://<blocks-db>",
    },
    system_message=(
        "You are a helpful assistant that writes clean Python 3 code. "
        "Always include a top-level function `def main(*args, **kwargs): ...` that returns the result. "
        "Declare external packages with REQUIREMENTS = [...] or '# requirements: pkg1, pkg2'."
    ),
    overwrite=True,
)
```

| Argument              | Default        | Description                                                                 |
| --------------------- | -------------- | --------------------------------------------------------------------------- |
| `name`                | — (required)   | Registry name                                                               |
| `model`               | — (required)   | Block ID of the code model                                                  |
| `inference_server_id` | — (required)   | Inference server ID, looked up in the registry; or an `http(s)://` URL used directly |
| `aios_url_map`        | — (required)   | `inference_server_url` (registry) and, optionally, `blocks_db_url` (used to verify the model exists) |
| `system_message`      | `""`           | Default system message (falls back to "You are a helpful assistant that provides code examples.") |
| `session_id`          | auto           | Session ID (`codegen-<uuid>`)                                               |
| `overwrite`           | `False`        | Replace an existing generator with the same name (otherwise `ValueError`)   |

Each call sends `POST <inference-server>/v1/infer`:

```json
{
  "model": "magistral-small-2506-llama-cpp-block",
  "session_id": "codegen-...",
  "seq_no": 1735689600123,
  "data": {
    "mode": "chat",
    "gen_params": { "temperature": 0.1, "top_p": 0.95, "max_tokens": 4096 },
    "message": "<prompt>",
    "system_message": "<system message>"
  },
  "graph": {},
  "selection_query": {}
}
```

The code is read from `data.reply` in the response.

---

## Using the OpenAI Backend

```python
from openai import OpenAI

openai_gen = OpenAICodeGenerator(
    model="gpt-4o-mini",          # default
    client=OpenAI(),              # optional; created from OPENAI_API_KEY if omitted
    default_system_message="You write concise, correct Python.",
)
codegen.register_custom_generator(name="openai", generator=openai_gen)
```

`OpenAICodeGenerator` sends `max_tokens` as `max_completion_tokens`. It does not forward `temperature` or `top_p`.

---

## Generating Code

```python
code = codegen.generate_code(
    name="aios-default",
    prompt="Write a function `main(a, b)` that returns the element-wise sum of two integer lists.",
    temperature=0.1,
    top_p=0.95,
    max_tokens=4096,
    system_message=None,        # override the generator's default
)
print(code)
```

AIOS generators also accept `seq_no` and `extra_headers`.

---

## Generating and Executing Code

`generate_and_execute` generates Python, prepares it, and calls an entry point:

```python
result = codegen.generate_and_execute(
    name="aios-default",
    prompt="""
Write Python that accepts two lists of integers and returns their element-wise sum using numpy.
Implement `def main(a, b): ...` that returns the summed list.
""",
    function_name="main",                        # default entry point
    args=[[1, 2, 3], [4, 5, 6]],
    kwargs={},
    scope_objects={"EXTRA_CONFIG": {"env": "dev"}},   # injected as module globals
    install_deps=True,
)
print(result)   # [5, 7, 9]
```

Steps:

1. **Generate** the code and strip Markdown fences.
2. **Collect dependencies** from any of:
    * `REQUIREMENTS = ["pkg", "pkg==1.2"]`
    * `# requirements: a, b==1.2` or `# deps: a b==1.2`
    * a fenced ```` ```requirements.txt ```` block
3. **Install** them with `pip install --upgrade` when `install_deps=True`. A failed install raises `RuntimeError`.
4. **Load** the code as a new module (`__generated_<uuid>__`, registered in `sys.modules`), after injecting `scope_objects` as module globals.
5. **Resolve and call** the entry point, in this order:
    1. a top-level function named `function_name` (default `main`);
    2. else `class_name().method_name` if both are given;
    3. else the single class in the module that defines `__call__` (it is instantiated, and the instance is called).

    Otherwise a `RuntimeError` is raised.

> Generated code runs in the agent's own process with full privileges, and dependency installation modifies the agent's environment. Only enable this for trusted models and prompts.

---

## Managing Generators

```python
codegen.list_generators()             # ['aios-default', 'openai']
codegen.has_generator("openai")       # True
gen = codegen.get_generator("openai") # KeyError if missing
codegen.unregister_generator("openai")
codegen.clear_generators()
```

---

## Writing a Custom Backend

Subclass `BaseCodeGenerator` and implement `generate_code`. All its parameters are keyword-only.

```python
from typing import Any, Optional
from agents_codegen.custom import BaseCodeGenerator, CodeGenerationError


class TemplateCodeGenerator(BaseCodeGenerator):
    def __init__(self, **kwargs: Any):
        super().__init__(model="template", **kwargs)

    def generate_code(
        self,
        *,
        prompt: str,
        temperature: float = 0.1,
        top_p: float = 0.95,
        max_tokens: int = 4096,
        system_message: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        if "sum" not in prompt:
            raise CodeGenerationError("Unsupported prompt")
        return "def main(a, b):\n    return [x + y for x, y in zip(a, b)]\n"


codegen.register_custom_generator(name="template", generator=TemplateCodeGenerator())
codegen.generate_and_execute(name="template", prompt="sum two lists", args=[[1], [2]])   # [3]
```

`BaseCodeGenerator.__init__` takes keyword-only `model`, `session_id`, `logger` and `default_system_message`, and provides the `_strip_markdown_fences()` and `_effective_system_message()` helpers. Only `BaseCodeGenerator` instances can be registered with `register_custom_generator`.
