from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Protocol, List, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class SearchableEntity(Protocol):
    id: Any
    def get_searchable_representation(self) -> str: ...


@dataclass
class SelectionResult:
    selected_id: str
    raw_json: Dict[str, Any]


class SelectionEngine:

    DEFAULT_QUERY = (
        "Select the single best-matching entity for the user's query from the list below."
    )

    def __init__(self, *, client, name: Optional[str] = None, base_query: Optional[str] = None) -> None:
        self.client = client
        self.name = name
        self.base_query = (base_query or self.DEFAULT_QUERY).strip()

    # ---------- Public API ----------

    def select(
        self,
        *,
        entities: Iterable[SearchableEntity],
        user_query: str,
        session_id: str,
        override_query: Optional[str] = None,
        # variable per-request params (temperature, max_tokens, tools, etc.)
        extra_data: Optional[Dict[str, Any]] = None,
        # ignored here; included for symmetry with async
        timeout: Optional[float] = None,
    ) -> SelectionResult:

        data, messages = self._build_data_payload(
            entities=entities,
            user_query=user_query,
            override_query=override_query,
            extra_data=extra_data,
        )

        # Call minimal AIGridClient API: only session_id + data (+ name)
        resp = self.client.chat_completions(
            session_id=session_id, messages=messages, data=data, name=self.name)

        text = self._extract_text_from_response(resp)
        parsed = self._parse_json_id(text)

        self._validate_selected_id(parsed, entities)
        return SelectionResult(selected_id=str(parsed["id"]), raw_json=parsed)

    def select_async(
        self,
        *,
        entities: Iterable[SearchableEntity],
        user_query: str,
        session_id: str,
        override_query: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> SelectionResult:

        data = self._build_data_payload(
            entities=entities,
            user_query=user_query,
            override_query=override_query,
            extra_data=extra_data,
        )

        logger.error(f"[data] {data}")

        waiter = self.client.c(session_id=session_id,
                               data=data, name=self.name)
        resp = waiter.wait(timeout=timeout)

        text = self._extract_text_from_response(resp)
        parsed = self._parse_json_id(text)

        self._validate_selected_id(parsed, entities)
        return SelectionResult(selected_id=str(parsed["id"]), raw_json=parsed)

    # ---------- Internals ----------

    def _build_data_payload(
        self,
        *,
        entities: Iterable[SearchableEntity],
        user_query: str,
        override_query: Optional[str],
        extra_data: Optional[Dict[str, Any]],
    ):
        ent_lines: List[str] = []
        for e in entities:
            ent_lines.append(
                f"- id: {e.id}\n  rep: {e.get_searchable_representation()}")
        if not ent_lines:
            raise ValueError("No entities provided to SelectionEngine.")

        selection_goal = (override_query or self.base_query).strip()

        # Strict JSON-only instructions
        system_msg = (
            "You are a selection engine. Respond with a single JSON object ONLY, exactly in this form:\n"
            '{"id":"<entity_id>"}\n'
            "No extra text, no markdown, no code fences, no comments."
        )
        user_msg = (
            f"{selection_goal}\n\n"
            f"User query:\n{user_query}\n\n"
            "Candidates:\n" + "\n".join(ent_lines) + "\n\n"
            'Output format (MUST be exact): {"id":"<entity_id>"}'
        )

        payload: Dict[str, Any] = {
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            "max_tokens": 32,
        }

        if extra_data:
            payload.update(extra_data)

        logger.info(f"payload: {payload}")

        return payload, [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

    @staticmethod
    def _extract_text_from_response(resp: Dict[str, Any]) -> str:

        if isinstance(resp, str):
            return resp.strip()
        if not resp:
            return ""

        # Chat shape
        try:
            return resp["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

        # Text shape
        try:
            return resp["choices"][0]["text"].strip()
        except Exception:
            pass

        for k in ("text", "output", "content"):
            v = resp.get(k)
            if isinstance(v, str):
                return v.strip()

        return str(resp).strip()

    @staticmethod
    def _parse_json_id(text: str) -> Dict[str, Any]:
        """Parse a single JSON object with an 'id' field. Tolerates stray code fences or extra text."""
        if not text:
            raise ValueError("Empty response; expected JSON like {'id':'...'}")

        t = text.strip()
        if t.startswith("```"):
            t = t.strip("`")

        if not (t.startswith("{") and t.endswith("}")):
            try:
                start = t.index("{")
                end = t.rindex("}") + 1
                t = t[start:end]
            except ValueError:
                raise ValueError(
                    f"Model did not return JSON. Got: {text[:200]}")

        data = json.loads(t)
        if not isinstance(data, dict) or "id" not in data:
            raise ValueError(
                f"JSON must be an object with an 'id' key. Got: {data!r}")

        data["id"] = str(data["id"])
        return data

    @staticmethod
    def _validate_selected_id(parsed: Dict[str, Any], entities: Iterable[SearchableEntity]) -> None:
        candidate_ids = {str(e.id) for e in entities}
        sid = str(parsed["id"])
        if sid not in candidate_ids:
            raise ValueError(
                f"Selected id '{sid}' is not among provided candidates: {sorted(candidate_ids)}")
