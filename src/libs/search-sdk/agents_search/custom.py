from __future__ import annotations

import json
import logging
import re
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence, Tuple

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


class SelectionError(RuntimeError):
    pass


class RankingError(SelectionError):
    """
    Raised when ranking fails or model output is invalid.
    """
    pass


class BaseSearchRanker(ABC):
    """
    Abstract base for LLM-driven item ranking (returns a sorted list of (id, score)).
    """

    def __init__(
        self,
        *,
        model: str,
        session_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        default_system_message: str = (
            "You are a careful assistant that scores and ranks a list of items.\n"
            "You MUST assign a relevance score between 0 and 1 to EVERY item.\n"
            "Return STRICT JSON that is either:\n"
            "1) An array of objects:\n"
            "   [\n"
            "     {\"id\": string, \"score\": number},\n"
            "     ...\n"
            "   ]\n"
            "   - Every item appears exactly once.\n"
            "   - The array MUST be sorted by score in descending order.\n"
            "OR\n"
            "2) An object mapping IDs to scores:\n"
            "   {\n"
            "     \"<id1>\": number,\n"
            "     \"<id2>\": number,\n"
            "     ...\n"
            "   ]\n"
            "Do not output anything except the JSON."
        ),
    ) -> None:
        self.model = model
        self.session_id = session_id or f"search-rank-{uuid.uuid4()}"
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.default_system_message = default_system_message

    @abstractmethod
    def rank_items(
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
    ) -> List[Tuple[str, float]]:
        """
        Rank items by relevance to the query.

        Returns:
            List of (id, score) tuples sorted by score DESC.
            Every input item must appear exactly once.
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
                    raise RankingError(f"Item at index {i} is not a dict and cannot be converted.")
            if id_key not in it:
                raise RankingError(f"Item at index {i} missing required id key '{id_key}'.")
            out.append(it)
        return out

    def _build_ranking_prompt(
        self,
        items: List[Dict[str, Any]],
        *,
        id_key: str,
        query: Optional[str],
        fields_to_show: Optional[List[str]],
    ) -> str:
        """
        Build a human-readable description of items plus instructions to score/rank them.
        """
        lines: List[str] = []
        for it in items:
            view = {id_key: it.get(id_key)}
            if fields_to_show:
                for k in fields_to_show:
                    if k != id_key and k in it:
                        v = str(it[k])
                        view[k] = (v[:300] + "…") if len(v) > 300 else v
            else:
                # Heuristic: include a few non-ID fields
                added = 0
                for k, v in it.items():
                    if k == id_key:
                        continue
                    v_str = str(v)
                    view[k] = (v_str[:300] + "…") if len(v_str) > 300 else v_str
                    added += 1
                    if added >= 4:
                        break

            pretty = ", ".join(f"{k}={view[k]}" for k in view)
            lines.append(f"- {pretty}")

        rules = [
            "You are given a list of items.",
            "Your task:",
            "- Assign a relevance score in [0, 1] to EVERY item.",
            "- Higher score means more relevant.",
            "- Then return STRICT JSON (as specified by the system message) with scores for each ID.",
        ]
        if query:
            rules.append(f"\nUser query / relevance hint:\n{query}")

        return "\n".join(rules) + "\n\nItems:\n" + "\n".join(lines) + "\n\nReturn JSON now."

    def _extract_json(self, text: str) -> Any:
        s = (text or "").strip()
        if not s:
            raise RankingError("Empty reply from model.")

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

        raise RankingError("Model did not return valid JSON.")

    def _parse_scores(
        self,
        parsed: Any,
        valid_ids: set,
    ) -> Dict[str, float]:
        """
        Convert the model JSON into a mapping of id -> score, ignoring hallucinated IDs.
        """
        scores: Dict[str, float] = {}

        try:
            if isinstance(parsed, list):
                # Expect list of {id, score}
                for obj in parsed:
                    if not isinstance(obj, dict):
                        continue
                    sid = str(obj.get("id", "")).strip()
                    if not sid or sid not in valid_ids:
                        continue
                    try:
                        score = float(obj.get("score", 0.0))
                    except (TypeError, ValueError):
                        score = 0.0
                    scores[sid] = score

            elif isinstance(parsed, dict):
                # Expect mapping id -> score
                for sid_raw, score_raw in parsed.items():
                    sid = str(sid_raw).strip()
                    if sid not in valid_ids:
                        continue
                    try:
                        score = float(score_raw)
                    except (TypeError, ValueError):
                        score = 0.0
                    scores[sid] = score
            else:
                raise RankingError(f"Unexpected ranking JSON type: {type(parsed)}")
        except Exception as e:
            raise RankingError(f"Failed to parse ranking output: {e}") from e

        if not scores:
            raise RankingError("No valid scores produced for any items.")

        return scores

    def _finalize_ranking(
        self,
        scores: Dict[str, float],
        valid_ids: set,
    ) -> List[Tuple[str, float]]:
        """
        Ensure every valid ID has a score, clamp to [0, 1], then sort DESC.
        """
        # Ensure every valid ID is present
        for vid in valid_ids:
            if vid not in scores:
                scores[vid] = 0.0

        normalized_scores: Dict[str, float] = {}
        for sid, sc in scores.items():
            try:
                v = float(sc)
            except (TypeError, ValueError):
                v = 0.0
            # Soft clamp
            if v < 0.0:
                v = 0.0
            if v > 1.0:
                v = 1.0
            normalized_scores[sid] = v

        ranked: List[Tuple[str, float]] = sorted(
            normalized_scores.items(),
            key=lambda kv: kv[1],
            reverse=True,
        )
        return ranked


class OpenAISearchRanker(BaseSearchRanker):
    """
    Concrete ranker using OpenAI Chat Completions (mirrors your OpenAISearchSelector style).
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

    def rank_items(
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
    ) -> List[Tuple[str, float]]:
        # Normalize + prompt
        normalized = self._normalize_items(items, id_key=id_key)
        prompt = self._build_ranking_prompt(
            normalized,
            id_key=id_key,
            query=query,
            fields_to_show=fields_to_show,
        )
        valid_ids = {str(it[id_key]) for it in normalized}

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._effective_system_message(system_message)},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                top_p=top_p,
                max_completion_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
        except Exception as e:
            self.logger.exception("OpenAI ranking failed")
            raise RankingError(str(e)) from e

        parsed = self._extract_json(content)
        scores = self._parse_scores(parsed, valid_ids)
        return self._finalize_ranking(scores, valid_ids)