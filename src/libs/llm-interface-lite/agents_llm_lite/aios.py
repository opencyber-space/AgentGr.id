from __future__ import annotations

import logging
import uuid
import time
from typing import Any, Dict, Optional, Callable

from .block.rest import RESTBlockInference
from .block.block_client import BlocksClient
from .block.inference_server import InferenceServerRegistryClient
# Import your earlier BaseInference here
from .custom import BaseInference  # make sure this points to the class you added before


class InferenceError(RuntimeError):
    pass


class RESTInference(BaseInference):
    """
    Plain inference runner over your RESTBlockInference client.
    Caller supplies a `callback(raw) -> str` to extract the desired text.
    """

    def __init__(
        self,
        *,
        client: "RESTBlockInference",
        model: str,
        session_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        default_system_message: str = "You are a helpful assistant that provides code examples.",
    ) -> None:
        super().__init__(
            model=model,
            session_id=session_id or f"infer-{uuid.uuid4()}",
            logger=logger or logging.getLogger(self.__class__.__name__),
            default_system_message=default_system_message,
        )
        self.client = client

    def infer(
        self,
        *,
        prompt: str,
        callback: Callable[[Any], str],
        temperature: float = 0.1,
        top_p: float = 0.95,
        max_tokens: int = 4096,
        system_message: Optional[str] = None,
        seq_no: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        **_: Any,
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
            raw = self.client.infer(
                model=self.model,
                session_id=self.session_id,
                seq_no=seq_no if seq_no is not None else self._now_ms(),
                data=data,
                graph={},
                selection_query={},
                extra_headers=extra_headers,
            )
            content = callback(raw)
        except Exception as e:
            self.logger.exception("RESTInference: infer request failed")
            raise InferenceError(str(e)) from e

        if not isinstance(content, str) or not content.strip():
            self.logger.error("RESTInference: callback returned empty/invalid content. raw=%r", raw)
            raise InferenceError("Empty content from inference response")

        return self._strip_markdown_fences(content)

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)


class AIOSInferenceAPI(BaseInference):
    """
    AIOS-backed inference that discovers the REST inference server and calls it.
    Caller supplies a `callback(raw) -> str` to extract the desired text.
    """

    def __init__(
        self,
        *,
        model: str,
        inference_server_id: str,
        aios_url_map: Dict[str, str] = {},
        system_message: str = "",
        session_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(
            model=model,
            session_id=session_id or f"infer-{uuid.uuid4()}",
            logger=logger or logging.getLogger(self.__class__.__name__),
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
        if self.inference_server_id and self.inference_server_id.startswith(("http://", "https://")):
            return self.inference_server_id

        if not self.inference_server_registry_url:
            raise InferenceError("Missing inference_server_url in aios_url_map")

        registry_client = InferenceServerRegistryClient(self.inference_server_registry_url)
        inference_server_data = registry_client.get_inference_server(self.inference_server_id)
        if not inference_server_data:
            raise InferenceError(f"Inference server not found: {self.inference_server_id}")

        urls = inference_server_data.get("inference_server_urls") or {}
        url = urls.get("rest") or urls.get("http") or urls.get("https")
        if not url:
            raise InferenceError(
                f"No REST/HTTP URL found for inference server: {self.inference_server_id}"
            )
        return url

    def _load_block_data(self) -> Dict[str, Any]:
        if not self.blocks_db_url:
            return {}
        block_client = BlocksClient(self.blocks_db_url)
        block_data = block_client.get_block_by_id(self.model)
        if not block_data:
            raise InferenceError(
                f"failed to query blocks data for model '{self.model}': {block_data}"
            )
        return block_data

    # ----------------- Inference -----------------

    def infer(
        self,
        *,
        prompt: str,
        callback: Callable[[Any], str],
        temperature: float = 0.1,
        top_p: float = 0.95,
        max_tokens: int = 4096,
        system_message: Optional[str] = None,
        seq_no: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        **_: Any,
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
                graph={},           
                selection_query={},
                extra_headers=extra_headers,
            )
            content = callback(raw)
        except Exception as e:
            self.logger.exception("AIOSInferenceAPI: infer request failed")
            raise InferenceError(str(e)) from e

        if not isinstance(content, str) or not content.strip():
            self.logger.error("AIOSInferenceAPI: callback returned empty/invalid content. raw=%r", raw)
            raise InferenceError("Empty content from inference response")

        return self._strip_markdown_fences(content)

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
