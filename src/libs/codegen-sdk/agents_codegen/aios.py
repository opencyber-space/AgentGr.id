import logging
import uuid
import time
from typing import Any, Dict, Optional
from openai import OpenAI

from .block.rest import RESTBlockInference
from .block.block_client import BlocksClient
from .block.inference_server import InferenceServerRegistryClient
from .custom import BaseCodeGenerator


class CodeGenerationError(RuntimeError):
    pass


class CodeGenerator:

    def __init__(
        self,
        *,
        client: "RESTBlockInference",
        model: str,
        session_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        default_system_message: str = "You are a helpful assistant that provides code examples.",
    ) -> None:
        self.client = client
        self.model = model
        self.session_id = session_id or f"codegen-{uuid.uuid4()}"
        self.logger = logger or logging.getLogger(__name__)
        self.default_system_message = default_system_message

    def generate_code(
        self,
        *,
        prompt: str,
        temperature: float = 0.1,
        top_p: float = 0.95,
        max_tokens: int = 4096,
        system_message: Optional[str] = None,
        seq_no: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> str:

        data: Dict[str, Any] = {
            "mode": "chat",
            "gen_params": {
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
            },
            "message": prompt,
            "system_message": system_message or self.default_system_message,
        }

        try:
            raw = self.client.infer(
                model=self.model,
                session_id=self.session_id,
                seq_no=seq_no if seq_no is not None else self.client._now_ms(),
                data=data,
                graph={},
                selection_query={},
                extra_headers=extra_headers,
            )
        except Exception as e:
            self.logger.exception("Code generation request failed")
            raise CodeGenerationError(str(e)) from e

        try:
            code_text = raw["data"]["reply"]
        except Exception:
            self.logger.error(
                "Response did not contain expected 'data.reply': %r", raw)
            raise CodeGenerationError("No code found in response.")

        if not isinstance(code_text, str) or not code_text.strip():
            raise CodeGenerationError("Empty code text in response.")

        if code_text.strip().startswith("```"):
            lines = code_text.strip().splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            code_text = "\n".join(lines)

        return code_text


class AIOSCodeGeneratorAPI(BaseCodeGenerator):
   
    def __init__(
        self,
        model: str,
        inference_server_id: str,
        aios_url_map: Dict[str, str] = {},
        system_message: str = "",
        *,
        session_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(
            model=model,
            session_id=session_id,
            logger=logger,
            default_system_message=system_message or "You are a helpful assistant that provides code examples.",
        )
        self.inference_server_id: str = inference_server_id
        self.inference_server_registry_url = aios_url_map.get("inference_server_url")
        self.blocks_db_url = aios_url_map.get("blocks_db_url")

        # Load metadata/URLs
        self.block_data = self._load_block_data()
        self.inference_server_url = self._load_inference_server_data()

        # REST client to the target server
        self.block_inference = RESTBlockInference(self.inference_server_url)

    # ----------------- Discovery helpers -----------------

    def _load_inference_server_data(self) -> str:
        # Allow direct URL in inference_server_id
        if self.inference_server_id.startswith(("http://", "https://")):
            return self.inference_server_id

        if not self.inference_server_registry_url:
            raise CodeGenerationError("Missing inference_server_url in aios_url_map")

        registry_client = InferenceServerRegistryClient(self.inference_server_registry_url)
        inference_server_data = registry_client.get_inference_server(self.inference_server_id)
        if not inference_server_data:
            raise CodeGenerationError(f"Inference server not found: {self.inference_server_id}")

        urls = inference_server_data.get("inference_server_urls") or {}
        url = urls.get("rest") or urls.get("http") or urls.get("https")
        if not url:
            raise CodeGenerationError(f"No REST/HTTP URL found for inference server: {self.inference_server_id}")
        return url

    def _load_block_data(self) -> Dict[str, Any]:
        if not self.blocks_db_url:
            return {}
        block_client = BlocksClient(self.blocks_db_url)
        block_data = block_client.get_block_by_id(self.model)
        if not block_data:
            raise CodeGenerationError(f"failed to query blocks data for model '{self.model}': {block_data}")
        return block_data


    def generate_code(
        self,
        *,
        prompt: str,
        temperature: float = 0.1,
        top_p: float = 0.95,
        max_tokens: int = 4096,
        system_message: Optional[str] = None,
        seq_no: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        data: Dict[str, Any] = {
            "mode": "chat",
            "gen_params": {
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
            },
            "message": prompt,
            "system_message": self._effective_system_message(system_message),
        }

        try:
            raw = self.block_inference.infer(
                model=self.model,
                session_id=self.session_id,
                seq_no=seq_no if seq_no is not None else self._now_ms(),
                data=data,
                graph={},                 # your sample uses an empty graph
                selection_query={},       # and an empty selection_query
                extra_headers=extra_headers,
            )
        except Exception as e:
            self.logger.exception("AIOSCodeGeneratorAPI: infer request failed")
            raise CodeGenerationError(str(e)) from e

        try:
            reply = raw["data"]["reply"]
        except Exception:
            self.logger.error("AIOSCodeGeneratorAPI: response missing data.reply: %r", raw)
            raise CodeGenerationError("No code found in response (missing data.reply)")

        if not isinstance(reply, str) or not reply.strip():
            raise CodeGenerationError("Empty code text in response")

        return self._strip_markdown_fences(reply)


    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)