# Code Generator SDK

## Introduction

The **Code Generator Sandbox SDK** is a Python-based framework designed to dynamically generate, instantiate, and execute Python code using Large Language Models (LLMs). It supports both local and remote LLMs, such as:

* **OpenAI** (`gpt-4`, `gpt-4o`, etc.)
* **Custom inference servers** via **gRPC** (like AIOS BlockInferenceService)

This SDK enables intelligent code generation workflows that can:

* Dynamically construct executable Python classes or functions based on a task description.
* Automatically resolve dependencies by extracting `import` statements and preparing a `requirements.txt`.
* Dynamically load and execute generated code at runtime.
* Plug in different LLM backends through a common interface.

It is particularly suited for:

* **Policy or function generation at runtime**
* **Serverless or modular AI systems**
* **AI-augmented development environments**
* **Adaptive DSL-based workflows**

---

**Key Capabilities:**

* Abstracts LLM interaction behind a unified interface (`CodeGeneratorAPI`)
* Uses pre- and post-processing hooks for controlled code shaping
* Supports multiple backends (OpenAI, gRPC-based services)
* Dynamically loads generated Python code via sandboxed temp execution
* Handles lifecycle, error handling, and resource cleanup

This documentation provides a comprehensive guide to the SDK's structure, core classes, usage examples, and execution flow.


---

## Installation

You can install the **Code Generator Sandbox SDK** by cloning the repository and installing it using `pip`. Make sure you have **Python 3.7+** installed.

### 1. Clone the Repository

```bash
cd codegen_sandbox
```

---

### 2. Install via pip

```bash
pip install .
```

---

### 3. (Optional) Install Development Dependencies

For development, testing, and linting:

```bash
pip install .[dev]
```

This installs:

* `pytest` for testing
* `flake8` for linting

---

### 4. Required Runtime Dependencies

The following Python packages are required and are installed automatically:

| Package    | Purpose                        |
| ---------- | ------------------------------ |
| `grpcio`   | For gRPC-based inference calls |
| `openai`   | For OpenAI model integration   |
| `requests` | Supporting HTTP operations     |

---

### 5. Verifying Installation

After installation, verify that the package is accessible:

```bash
python -c "from core import CodeGeneratorSandbox; print('Codegen SDK is installed')"
```

If no error is raised, the installation is successful.

---

## Usage

This section explains how to use the **Code Generator Sandbox SDK** with:

1. The default **OpenAI** LLM backend
2. A custom **AIOS gRPC-based** inference backend

Each backend conforms to the shared `CodeGeneratorAPI` interface, allowing seamless switching with minimal changes.

---

### Prerequisites

* Ensure you've installed the SDK and its dependencies (see [Installation](#installation)).
* Set up your OpenAI API key or have a running AIOS inference block.

---

### 1. Using the OpenAI Backend

This is the simplest setup using OpenAI’s GPT models (`gpt-4o`, `gpt-4`, etc.).

#### Example

```python
from core import CodeGeneratorSandbox
from core.default import OpenAILLM

# Initialize the OpenAI backend with your API key
openai_generator = OpenAILLM(
    api_key='your-openai-api-key',
    model='gpt-4o',              # Optional: defaults to gpt-4o
    temperature=0.7,
    max_tokens=1000
)

# Create the sandbox instance
sandbox = CodeGeneratorSandbox(
    global_settings={},
    global_parameters={},
    global_state={},
    generator_api=openai_generator
)

# Generate and instantiate code from a task description
instantiator = sandbox.generate_and_instantiate(
    task_description="Create a method called add(a, b, c), I will use that method to perform additions"
)

# Call the generated function
print(instantiator.function_instance.add(10, 20, 30))
```

---

### 2. Using the AIOS Inference Backend (gRPC)

Use this setup if you have a running **BlockInferenceService** (from the AIOS runtime) and want to call it via gRPC.

#### Example

```python
from core import CodeGeneratorSandbox
from core.default import AIOSLLM

# Initialize AIOS gRPC client
aios_generator = AIOSLLM(
    server_address="localhost:50051",   # Replace with actual gRPC address
    block_id="block-codegen",
    instance_id="instance-123",
    session_id="session-abc",
    seq_no=1,
    frame_ptr=b"",                      # Frame pointer (if any)
    query_parameters=b"",              # Custom parameters
    is_frame=False                     # Whether this is a frame-based packet
)

# Create the sandbox instance
sandbox = CodeGeneratorSandbox(
    global_settings={},
    global_parameters={},
    global_state={},
    generator_api=aios_generator
)

# Generate and instantiate function
instantiator = sandbox.generate_and_instantiate(
    task_description="Generate a Python function called greet(name) that returns 'Hello, {name}!'"
)

# Call the function
print(instantiator.function_instance.greet("Alice"))
```

---

## Custom Prompts and Advanced Features

The **Code Generator Sandbox SDK** offers flexible customization capabilities to help tailor code generation and execution workflows for diverse use cases. This section outlines how to customize prompts, templates, pre-processing, and more.

---

### 1. Custom Task Descriptions

At the core of the SDK is the **task description** — a natural language prompt that tells the LLM what code to generate.

#### Example:

```python
task_description = "Create a Python class with a method multiply(x, y) that returns the product."
```

This will be passed to the selected LLM backend, optionally enriched with structured descriptors (see below).

---

### 2. Using Custom Descriptors

You can inject **descriptors** alongside your task description. These help guide the LLM in shaping the output.

#### Example:

```python
custom_descriptors = {
    "structure": "include docstrings and typing hints",
    "style": "return raw Python code only",
    "template": "# My custom starter template\n\n"
}
```

Pass them to `generate_code` or `generate_and_instantiate`:

```python
sandbox.generate_and_instantiate(
    task_description="Define a function divide(a, b) that handles divide-by-zero",
    descriptors=custom_descriptors
)
```

> ⚠️ If `use_default_descriptors=True` (default), these descriptors will be **merged** with SDK defaults. You can disable that by setting it to `False` in lower-level usage of `generate_code()`.

---

### 3. Custom Templates

By default, the SDK uses a generic template that includes a placeholder Python class:

```python
class AgentSpaceV1PolicyRule:
    def __init__(...):
        pass

    def eval(...):
        pass
```

You can override this by passing a custom `template` when initializing the `CodeGenerator` or `CodeGeneratorSandbox`.

#### Example:

```python
my_template = """
# Custom logic class

class MyGeneratedPolicy:
    def run(self, config, input_data):
        # Your logic here
        pass
"""

sandbox = CodeGeneratorSandbox(
    global_settings={},
    global_parameters={},
    global_state={},
    template=my_template,
    generator_api=openai_generator
)
```

> Your prompt and descriptors can reference fields like `"template": my_template` to inform the LLM.

---

### 4. Pre-Processing Hooks

Both `OpenAILLM` and `AIOSLLM` allow you to register a **custom pre-processor** that modifies the task description before sending it to the LLM.

#### Default Behavior

The default pre-processor appends descriptor key-value pairs to the task:

```python
# Input:
task_description = "Create a class Calculator"
descriptors = {"style": "concise", "include_tests": "yes"}

# Resulting prompt:
"Create a class Calculator style: concise include_tests: yes"
```

#### Custom Pre-Processor

```python
def custom_pre_processor(task, descriptors):
    return f"[Task] {task}\n[Hints] {json.dumps(descriptors)}"

openai_generator.set_pre_processor(custom_pre_processor)
```

---

### 5. Accessing Generated Files

The output of `generate_code(...)` is a dictionary:

```python
{
    "main.py": "<generated Python code>",
    "requirements.txt": "<auto-extracted dependencies>"
}
```

You can save these manually or allow the SDK to handle instantiation and execution.

---

### 6. Direct Execution with Parameters

Once the function is instantiated, you can execute it directly:

```python
sandbox.execute_function(
    parameters={"a": 5, "b": 10},
    input_data={"trigger": True},
    context={}
)
```

This will call the `eval()` method of the dynamically generated class.

---

### 7. Cleanup

To delete temp files and release resources:

```python
sandbox.cleanup()
```

Always call this if you’re managing instantiation and execution manually.

---

### Summary of Advanced Features

| Feature                | Description                                                         |
| ---------------------- | ------------------------------------------------------------------- |
| **Custom descriptors** | Add constraints or hints to LLM behavior                            |
| **Template override**  | Define the class/function structure                                 |
| **Pre-processor hook** | Modify prompt before sending to LLM                                 |
| **Flexible I/O**       | Output is structured into code and requirements buffers             |
| **LLM plug-in system** | Easily switch between OpenAI or gRPC backends                       |
| **Eval interface**     | Standardized execution via `.eval(parameters, input_data, context)` |

---


Understood. Here's the cleaned-up version of the section without any emojis:

---

## Plugging in a Custom Model Server

The **Code Generator Sandbox SDK** supports integration with custom LLM servers through a clean and extensible interface: the `CodeGeneratorAPI` abstract base class. This allows you to plug in any model backend — REST, gRPC, WebSocket, or local — by implementing a single method.

---

### Overview

To integrate a custom model server, you must:

1. Create a new Python class that inherits from `CodeGeneratorAPI`
2. Implement the `generate(...)` method
3. (Optionally) Add a pre-processing hook

This integration allows your backend to seamlessly work with `CodeGenerator`, `CodeGeneratorSandbox`, and all other components of the SDK.

---

### Abstract Interface: `CodeGeneratorAPI`

```python
from abc import ABC

class CodeGeneratorAPI(ABC):
    def generate(self, task_description: str, descriptors: Dict[str, str]) -> str:
        """
        Generate code from a task description and descriptors.

        Parameters:
            task_description (str): Natural language prompt describing the code.
            descriptors (Dict[str, str]): Key-value pairs to guide output formatting.

        Returns:
            str: Generated Python code as a raw string (no markdown formatting).
        """
        pass
```

This method should return **plain Python code** as a string. Do not include formatting like markdown code blocks. The SDK will handle templating, validation, dependency extraction, and runtime execution.

---

### Example: Custom REST API Integration

```python
import requests
from typing import Dict, Callable
from core.generator import CodeGeneratorAPI

class MyRESTLLM(CodeGeneratorAPI):
    def __init__(self, endpoint_url: str):
        self.endpoint_url = endpoint_url
        self.pre_processor: Callable[[str, Dict[str, str]], str] = self.default_pre_processor

    def set_pre_processor(self, fn: Callable[[str, Dict[str, str]], str]):
        self.pre_processor = fn

    def default_pre_processor(self, task: str, descriptors: Dict[str, str]) -> str:
        for k, v in descriptors.items():
            task += f" {k}: {v}"
        return task

    def generate(self, task_description: str, descriptors: Dict[str, str]) -> str:
        prompt = self.pre_processor(task_description, descriptors)

        try:
            response = requests.post(
                self.endpoint_url,
                json={"prompt": prompt}
            )
            response.raise_for_status()
            return response.json()["code"]

        except Exception as e:
            raise RuntimeError(f"REST model server failed: {str(e)}")
```

---

### Example Usage with `CodeGeneratorSandbox`

```python
llm = MyRESTLLM(endpoint_url="http://localhost:8000/generate")

sandbox = CodeGeneratorSandbox(
    global_settings={},
    global_parameters={},
    global_state={},
    generator_api=llm
)

instance = sandbox.generate_and_instantiate(
    task_description="Write a function that reverses a string"
)

print(instance.function_instance.reverse("hello"))
```

---

### Implementation Notes

| Feature                 | Description                                                              |
| ----------------------- | ------------------------------------------------------------------------ |
| Plain Code Output       | Return code as raw string; do not wrap in markdown or special formatting |
| Descriptor Support      | Use `descriptors` to enrich prompt context or model instructions         |
| Safe Exception Handling | Wrap external API failures with clear error messages                     |
| Pluggable Preprocessing | Allow pre-processing overrides via `set_pre_processor(...)`              |

---

## Code Generator Wrapper (Agent SDK Integration)

### Overview

The **`CodeGenerators`** class is a higher-level abstraction built on top of the `CodeGeneratorSandbox`. It allows dynamic registration and management of multiple named code generation backends (e.g., OpenAI, custom gRPC, REST).

This module is embedded into the **Agents SDK** and made accessible via:

```python
from utils import code_gen_api
```

This allows seamless integration of dynamic LLM-based code generation into agents or policies.

---

### Class: `CodeGenerators`

#### Initialization

```python
code_gen_api = CodeGenerators(global_settings, global_parameters, global_state)
```

Stores global configurations and initializes the registry of sandboxes.

---

### Method: `register_code_generator(...)`

```python
register_code_generator(name: str, generator_api: CodeGeneratorAPI, template: Optional[str] = None)
```

Registers a new named generator.

* `name`: Logical name used to reference the generator
* `generator_api`: Must implement `CodeGeneratorAPI`
* `template`: Optional Python class/function template for output

Raises error if the name already exists.

---

### Method: `generate(...)`

```python
generate(name: str, task_description: str, descriptors: Optional[Dict[str, str]] = None)
```

Generates code (without instantiating) using the named backend.

Returns a dictionary:

```python
{
  "main.py": "...generated code...",
  "requirements.txt": "...auto-extracted requirements..."
}
```

---

### Method: `generate_and_instantiate(...)`

```python
generate_and_instantiate(name: str, task_description: str, descriptors: Optional[Dict[str, str]] = None)
```

Generates code and initializes a live Python object from it. Internally uses `GeneratedFunctionInstantiator`.

Returns the `instantiator`, which gives access to:

```python
instantiator.function_instance.eval(...)
```

---

### Method: `execute_function(...)`

```python
execute_function(name: str, parameters: dict, input_data: dict, context: dict)
```

Executes the `eval()` method on the generated and loaded function.

This is the standard entry point for runtime execution.

---

### Method: `cleanup(...)`

```python
cleanup(name: Optional[str] = None)
```

* If `name` is provided: cleans up the named generator’s temp files
* If omitted: cleans up all registered generators

---

### Method: `list_code_generators()`

Returns a dictionary mapping generator names to their `CodeGeneratorSandbox` instances.

---

### Abstract Interface: `CodeGeneratorAPI` (Extended)

Any custom generator backend must implement:

```python
class CodeGeneratorAPI(ABC):
    @abstractmethod
    def generate(self, task_description: str, descriptors: Dict[str, str]) -> str:
        pass

    @abstractmethod
    def check_execute(self, query: dict):
        pass

    @abstractmethod
    def get_current_estimates(self):
        pass
```

Only `generate(...)` is used internally for code execution. The other two methods (`check_execute`, `get_current_estimates`) are meant for extended planner capabilities and can raise `NotImplementedError` if unused.

---

### Example

```python
from utils.code_gen_api import CodeGenerators
from core.default import OpenAILLM

openai_backend = OpenAILLM(api_key="...")

code_gen_api.register_code_generator("openai", openai_backend)

output = code_gen_api.generate_and_instantiate(
    name="openai",
    task_description="Define a class Calculator with a method add(x, y)"
)

print(output.function_instance.add(5, 7))
```

---

### Notes

* You can register multiple backends (e.g., `"openai"`, `"local"`, `"grpc_llm"`) and switch by name.
* Descriptors and custom templates can be passed at generation time.
* This system is built to be agent-friendly and reusable across policy blocks and execution pipelines.
