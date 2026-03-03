import abc
import traceback
from typing import Any, Dict, Optional


class AgentWorkflowModule(abc.ABC):
   

    def __init__(
        self,
        name: str,
        version: str = "1.0",
        max_retries: int = 0,
        timeout_seconds: Optional[int] = None,
        allow_failure: bool = False,
    ):
        self.name = name
        self.version = version
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.allow_failure = allow_failure


    def execute(self, workflow_state: Any, input_data: Dict[str, Any]) -> Dict[str, Any]:
    
        attempt = 0
        last_exception = None

        self._validate_input_structure(input_data)

        while attempt <= self.max_retries:
            try:
                output = self._execute(workflow_state, input_data)

                self._validate_output_structure(output)

                return {
                    "status": "success",
                    "module": self.name,
                    "output": output,
                    "error": None,
                }

            except Exception as e:
                attempt += 1
                last_exception = e

                if attempt > self.max_retries:
                    error_payload = {
                        "status": "failed",
                        "module": self.name,
                        "output": None,
                        "error": {
                            "message": str(e),
                            "trace": traceback.format_exc(),
                        },
                    }

                    if not self.allow_failure:
                        raise RuntimeError(error_payload)

                    return error_payload

        # Should never reach here
        raise RuntimeError("Unexpected execution failure state")

    @abc.abstractmethod
    def _execute(self, workflow_state: Any, input_data: Dict[str, Any]) -> Dict[str, Any]:
       
        pass

   
    @abc.abstractmethod
    def get_description(self) -> str:
        
        pass

    @abc.abstractmethod
    def get_input_structure(self) -> Dict[str, Any]:
        
        pass

    @abc.abstractmethod
    def get_output_structure(self) -> Dict[str, Any]:
       
        pass


    def _validate_input_structure(self, input_data: Dict[str, Any]):
        if not isinstance(input_data, dict):
            raise ValueError("Input data must be a dictionary")

    def _validate_output_structure(self, output_data: Dict[str, Any]):
        if not isinstance(output_data, dict):
            raise ValueError("Output must be a dictionary")