# test_codegen.py
import logging
from typing import Any, Dict

from agents_codegen.generator import AgentCodeGenerator


MODEL_NAME = "magistral-small-2506-llama-cpp-block"

INFERENCE_SERVER_REGISTRY_URL = "http://<AIOS-INFERENCE-REGISTRY>/api"  
BLOCKS_DB_URL = "http://34.58.1.86:30100"                           
INFERENCE_SERVER_ID = "http://35.232.150.117:31504"                    


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("test-codegen")

    ag = AgentCodeGenerator(logger=log)

    gen_name = "aios-default"
    ag.register_new_code_generator(
        name=gen_name,
        model=MODEL_NAME,
        inference_server_id=INFERENCE_SERVER_ID,
        aios_url_map={
            "inference_server_url": INFERENCE_SERVER_REGISTRY_URL,
            "blocks_db_url": BLOCKS_DB_URL,
        },
        system_message=(
            "You are a helpful assistant that writes clean Python 3 code. "
            "Always include a top-level function `def main(*args, **kwargs): ...` "
            "that returns the final result. If external packages are needed, "
            "declare them using either a top-level REQUIREMENTS = [...] list or "
            "a comment like '# requirements: package1, package2==x.y'."
            "Strictly don't write extra content"
        ),
        overwrite=True,
    )

    prompt = """
Write Python that:
- Accepts two lists of integers and returns their element-wise sum using numpy library.
- Implement `def main(a, b): ...` that returns the summed list.
# (Optional) Show how to declare deps: '# requirements: numpy'
# Keep it simple and standard library only for this example.
"""

    scope_objects: Dict[str, Any] = {
        "EXTRA_CONFIG": {"owner": "Prasanna", "env": "dev"}
    }

    a = [1, 2, 3, 4]
    b = [10, 20, 30, 40]
    try:
        result = ag.generate_and_execute(
            name=gen_name,
            prompt=prompt,
            args=(a, b),                 
            scope_objects=scope_objects,  # injected into module globals
            # seq_no=123, extra_headers={"X-Trace": "test"}
            install_deps=True
        )
        print("Result from generated main(...):", result)
    except Exception as e:
        log.exception("Generation/execution failed: %s", e)
        raise


if __name__ == "__main__":
    main()
