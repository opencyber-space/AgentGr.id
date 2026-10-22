from __future__ import annotations

import json
import logging
import re
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence

from openai import OpenAI


class SelectionError(RuntimeError):
    pass


class BaseSearchSelector(ABC):
    """
    Abstract base for LLM-driven item selection (returns a single item ID).
    """

    def __init__(
        self,
        *,
        model: str,
        session_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        default_system_message: str = (
            "You are a careful assistant that selects exactly ONE item from a provided list.\n"
            "Return STRICT JSON with keys: {\"selected_id\": string, \"reason\": string}.\n"
            "Only choose an ID that exists in the provided list."
        ),
    ) -> None:
        self.model = model
        self.session_id = session_id or f"search-{uuid.uuid4()}"
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.default_system_message = default_system_message

    @abstractmethod
    def select_item(
        self,
        *,
        items: Sequence[Dict[str, Any]],
        id_key: str = "id",
        query: Optional[str] = None,
        fields_to_show: Optional[List[str]] = None,
        temperature: float = 0.0,
        top_p: float = 0.95,
        max_tokens: int = 512,
        system_message: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Return the chosen item ID.
        """
        raise NotImplementedError

    # --------- Helpers for implementors ---------

    def _effective_system_message(self, override: Optional[str]) -> str:
        return override or self.default_system_message

    def _normalize_items(self, items: Sequence[Dict[str, Any]], *, id_key: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                try:
                    it = dict(it)
                except Exception:
                    raise SelectionError(f"Item at index {i} is not a dict and cannot be converted.")
            if id_key not in it:
                raise SelectionError(f"Item at index {i} missing required id key '{id_key}'.")
            out.append(it)
        return out

    def _build_prompt(
        self,
        items: List[Dict[str, Any]],
        *,
        id_key: str,
        query: Optional[str],
        fields_to_show: Optional[List[str]],
    ) -> str:
        lines = []
        for it in items:
            view = {id_key: it.get(id_key)}
            if fields_to_show:
                for k in fields_to_show:
                    if k != id_key and k in it:
                        v = str(it[k])
                        view[k] = (v[:300] + "…") if len(v) > 300 else v
            else:
                # Heuristic: add a few non-ID fields
                added = 0
                for k, v in it.items():
                    if k == id_key:
                        continue
                    view[k] = (str(v)[:300] + "…") if len(str(v)) > 300 else v
                    added += 1
                    if added >= 4:
                        break

            pretty = ", ".join(f"{k}={view[k]}" for k in view)
            lines.append(f"- {pretty}")

        rules = [
            "You are given a list of items. Pick the SINGLE best match and return its ID.",
            "Rules:",
            "1) Choose ONLY an ID that exists in the list.",
            "2) Output STRICT JSON ONLY, no prose.",
            '   Example: {"selected_id":"<ID>", "reason":"<short rationale>"}',
            "3) If multiple are similar, prefer the most specific or most complete match.",
        ]
        if query:
            rules.append(f"\nUser query / selection hint:\n{query}")

        return "\n".join(rules) + "\n\nItems:\n" + "\n".join(lines) + "\n\nReturn JSON now."

    def _extract_json(self, text: str) -> Dict[str, Any]:
        s = (text or "").strip()
        if not s:
            raise SelectionError("Empty reply from model.")

        # strip ```json fences if present
        if s.startswith("```"):
            lines = s.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            s = "\n".join(lines).strip()

        # try direct parse
        try:
            return json.loads(s)
        except Exception:
            pass

        # fallback: grab largest {...}
        first, last = s.find("{"), s.rfind("}")
        if first != -1 and last != -1 and last > first:
            try:
                return json.loads(s[first : last + 1])
            except Exception:
                pass

        # last resort: simple object regex
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass

        raise SelectionError("Model did not return valid JSON.")

    def _validate_selected_id(self, parsed: Dict[str, Any], valid_ids: set) -> str:
        if not isinstance(parsed, dict) or "selected_id" not in parsed:
            raise SelectionError("Model output missing 'selected_id'.")
        selected_id = str(parsed["selected_id"]).strip()
        if not selected_id:
            raise SelectionError("Model returned an empty 'selected_id'.")
        if selected_id not in valid_ids:
            raise SelectionError(f"Selected ID '{selected_id}' not found in the provided items.")
        return selected_id


class OpenAISearchSelector(BaseSearchSelector):
    """
    Concrete selector using OpenAI Chat Completions (mirrors your OpenAICodeGenerator style).
    """

    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        client: Optional[OpenAI] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model=model, **kwargs)
        self.client = client or OpenAI()

    def select_item(
        self,
        *,
        items: Sequence[Dict[str, Any]],
        id_key: str = "id",
        query: Optional[str] = None,
        fields_to_show: Optional[List[str]] = None,
        temperature: float = 0.0,
        top_p: float = 0.95,
        max_tokens: int = 512,
        system_message: Optional[str] = None,
        **_: Any,
    ) -> str:
        # Normalize + prompt
        normalized = self._normalize_items(items, id_key=id_key)
        prompt = self._build_prompt(
            normalized, id_key=id_key, query=query, fields_to_show=fields_to_show
        )
        valid_ids = {str(it[id_key]) for it in normalized}

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._effective_system_message(system_message)},
                    {"role": "user", "content": prompt},
                ],
               
                max_completion_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
        except Exception as e:
            self.logger.exception("OpenAI selection failed")
            raise SelectionError(str(e)) from e

        parsed = self._extract_json(content)
        return self._validate_selected_id(parsed, valid_ids)
