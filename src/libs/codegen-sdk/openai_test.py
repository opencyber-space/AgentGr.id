# test_openai_complex.py
import logging
import os
from typing import Any, Dict
from openai import OpenAI

from agents_codegen.custom import OpenAICodeGenerator
from agents_codegen.generator import AgentCodeGenerator

# Adjust imports to your layout:
# from your_pkg.codegen.openai import OpenAICodeGenerator
# from your_pkg.agent_codegen import AgentCodeGenerator

MODEL_NAME = "gpt-5-mini-2025-08-07"

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("test-openai-complex")

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY in env before running.")


    openai_client = OpenAI()
    openai_gen = OpenAICodeGenerator(
        client=openai_client,
        model=MODEL_NAME,
        default_system_message=(
            "You generate robust, production-grade Python 3 code with type hints. "
            "Always include a top-level function `def main(*args, **kwargs): ...` that returns results. "
            "If you need external packages, declare REQUIREMENTS = [...] at the module top."
            "Strictly don't write extra content."
        ),
    )

    ag = AgentCodeGenerator(logger=log)
    ag.register_custom_generator(name="openai-complex", generator=openai_gen, overwrite=True)

    prompt = r"""
Write a single Python module that:

- Optionally declares REQUIREMENTS if needed (prefer stdlib if possible).

- Implements:
    class Task:
        name: str
        deps: list[str]
        fn: callable  # function with signature fn(context: dict) -> None

    def topo_sort(tasks: dict[str, Task]) -> list[str]:
        - Return a valid topological order.
        - Raise ValueError on cycles.

    def run_dag(tasks: dict[str, Task], order: list[str], context: dict) -> dict:
        - Execute tasks in the given order by calling task.fn(context).
        - Each fn can write into context; return the final context.

    Provide 3 built-in tasks:
        - "load": put {"data": [1, 2, 3, 10, 20]} into context
        - "transform": square each number into "data2"
        - "reduce": sum "data2" into "total"

- Provide: def main(request: dict | None=None) -> dict
    - Build the tasks graph:
        load -> transform -> reduce
    - topo sort it
    - run it with a fresh context + any overrides from `request` (dict merged into context)
    - Return {"order": order, "result": context}

- Include light error handling and docstrings.
"""

    scope_objects: Dict[str, Any] = {
        "GREETING": "hello from test",
    }

    out = ag.generate_and_execute(
        name="openai-complex",
        prompt=prompt,
        args=({"override": True},),  # main(request={"override": True})
        scope_objects=scope_objects,
    )

    print("ORDER:", out.get("order"))
    print("RESULT CONTEXT:", out.get("result"))


if __name__ == "__main__":
    main()
