from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional
from openai import OpenAI


class InferenceError(RuntimeError):
    pass


class BaseInference(ABC):
    def __init__(
        self,
        *,
        model: str,
        session_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        default_system_message: str = "You are a helpful assistant that perform required task examples.",
    ) -> None:
        self.model = model
        self.session_id = session_id or f"infer-{uuid.uuid4()}"
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.default_system_message = default_system_message

    @abstractmethod
    def infer(
        self,
        *,
        prompt: str,
        callback: Callable[[Any], str],
        temperature: float = 0.1,
        top_p: float = 0.95,
        max_tokens: int = 4096,
        system_message: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        
        raise NotImplementedError

    # ---- optional helpers ----
    def _strip_markdown_fences(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        s = text.strip()
        if not s.startswith("```"):
            return text
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)

    def _effective_system_message(self, override: Optional[str]) -> str:
        return override or self.default_system_message


class OpenAIInference(BaseInference):
    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        client: Optional[OpenAI] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model=model, **kwargs)
        self.client = client or OpenAI()

    def infer(
        self,
        *,
        prompt: str,
        callback: Callable[[Any], str],
        temperature: float = 0.1,
        top_p: float = 0.95,
        max_tokens: int = 4096,
        system_message: Optional[str] = None,
        **_: Any,
    ) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._effective_system_message(system_message)},
                    {"role": "user", "content": prompt},
                ],
                # temperature=temperature,
                # top_p=top_p,
                max_completion_tokens=max_tokens,
            )
            content = callback(resp)
        except Exception as e:
            self.logger.exception("OpenAI inference failed")
            raise InferenceError(str(e)) from e

        if not content or not isinstance(content, str) or not content.strip():
            raise InferenceError("Empty content from OpenAI")

        return self._strip_markdown_fences(content)
