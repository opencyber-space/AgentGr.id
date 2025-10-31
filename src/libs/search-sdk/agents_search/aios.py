import logging
import uuid
import time
import json
import re
from typing import Any, Dict, List, Optional, Sequence

from .block.rest import RESTBlockInference
from .block.block_client import BlocksClient
from .block.inference_server import InferenceServerRegistryClient
from .custom import BaseSearchSelector


class SelectionError(RuntimeError):
    pass


# ---------- Core selector (LLM-driven) ----------
class SearchSelector:
    """
    Use an LLM to select exactly one item from a provided list and return its ID.
    Items can be dictionaries (recommended) or any object convertible to a dict.
    """

    def __init__(
        self,
        *,
        client: "RESTBlockInference",
        model: str,
        session_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        default_system_message: str = (
            "You are a careful assistant that selects exactly ONE item from a list.\n"
            "You MUST output strict JSON with keys: {\"selected_id\": string, \"reason\": string}.\n"
            "Only choose an ID that exists in the provided items."
        ),
    ) -> None:
        self.client = client
        self.model = model
        self.session_id = session_id or f"search-{uuid.uuid4()}"
        self.logger = logger or logging.getLogger(__name__)
        self.default_system_message = default_system_message

    # ------------- Public API -------------

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
        seq_no: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Ask the model to select one item ID from `items`.

        Returns:
            selected_id (str)

        Raises:
            SelectionError on any failure.
        """
        if not items:
            raise SelectionError("No items provided for selection.")

        # Pre-validate and render a compact view of items for the prompt
        normalized = self._normalize_items(items, id_key=id_key)
        prompt = self._build_prompt(normalized, id_key=id_key, query=query, fields_to_show=fields_to_show)

        data: Dict[str, Any] = {
            "mode": "chat",
            "gen_params": {"temperature": temperature, "top_p": top_p, "max_tokens": max_tokens},
            "message": prompt,
            "system_message": system_message or self.default_system_message,
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
        except Exception as e:
            self.logger.exception("Search selection request failed")
            raise SelectionError(str(e)) from e

        text = self._extract_reply_text(raw)
        parsed = self._extract_json(text)

        # Validate schema
        if not isinstance(parsed, dict) or "selected_id" not in parsed:
            self.logger.error("Model output missing 'selected_id': %r", parsed)
            raise SelectionError("Model did not return required key 'selected_id'.")

        selected_id = str(parsed["selected_id"]).strip()
        if not selected_id:
            raise SelectionError("Model returned an empty 'selected_id'.")

        # Ensure it is one of the provided IDs
        valid_ids = {str(it[id_key]) for it in normalized}
        if selected_id not in valid_ids:
            self.logger.error("Selected ID not in provided set. selected=%s valid=%s", selected_id, list(valid_ids)[:20])
            raise SelectionError(f"Selected ID '{selected_id}' not found in the provided items.")

        return selected_id

    # ------------- Helpers -------------

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    def _normalize_items(self, items: Sequence[Dict[str, Any]], *, id_key: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                try:
                    it = dict(it)  # last-ditch attempt
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
        # Render items compactly; limit large fields, show selected keys if provided
        lines = []
        for it in items:
            view = {k: it.get(k) for k in ([id_key] + (fields_to_show or []))}
            # Fallback: if no fields requested, include a short auto view
            if not fields_to_show:
                # Heuristic: show a few non-ID keys
                extra = {k: v for k, v in it.items() if k != id_key}
                keys = list(extra.keys())[:4]
                for k in keys:
                    view[k] = extra[k]
            # Truncate long strings for readability
            compact = {}
            for k, v in view.items():
                s = str(v)
                compact[k] = (s[:300] + "…") if len(s) > 300 else s
            lines.append(f"- {id_key}={it[id_key]} | " + ", ".join(f"{k}={compact[k]}" for k in compact))

        instructions = [
            "You are given a list of items. Your job is to pick the SINGLE best match and return its ID.",
            "Rules:",
            "1) Choose ONLY an ID present in the list.",
            "2) Output strict JSON ONLY, no prose.",
            '   Example: {"selected_id":"<ID>", "reason":"<short rationale>"}',
            "3) If multiple are similar, prefer the most specific or most complete match.",
        ]
        if query:
            instructions.append(f"\nUser query / selection hint:\n{query}")

        return "\n".join(instructions) + "\n\nItems:\n" + "\n".join(lines) + "\n\nReturn JSON now."

    def _extract_reply_text(self, raw: Dict[str, Any]) -> str:
        try:
            reply = raw["data"]["reply"]
        except Exception:
            self.logger.error("Response did not contain expected 'data.reply': %r", raw)
            raise SelectionError("No reply found in response.")
        if not isinstance(reply, str) or not reply.strip():
            raise SelectionError("Empty reply in response.")
        return reply.strip()

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """
        Robustly parse JSON from model output.
        - If fenced in ```json ... ```, strip fences.
        - If raw JSON present, parse directly.
        - Else, try to locate the largest {...} block.
        """
        s = text.strip()
        # Strip Markdown fences
        if s.startswith("```"):
            lines = s.splitlines()
            # remove first and last fence
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            s = "\n".join(lines).strip()

        # Direct parse
        try:
            return json.loads(s)
        except Exception:
            pass

        # Try to find JSON object substring
        match = self._largest_json_object(s)
        if match:
            try:
                return json.loads(match)
            except Exception:
                pass

        self.logger.error("Failed to parse JSON from model output: %r", text)
        raise SelectionError("Model did not return valid JSON.")

    @staticmethod
    def _largest_json_object(s: str) -> Optional[str]:
        """
        Find the largest balanced {...} substring (simple heuristic).
        """
        # Greedy: take first '{' to last '}' if any
        first = s.find("{")
        last = s.rfind("}")
        if first != -1 and last != -1 and last > first:
            return s[first : last + 1]
        # Fallback: try a stricter regex for an object
        m = re.search(r"\{(?:[^{}]|(?R))*\}", s)  # may not work in all engines; keep simple
        return m.group(0) if m else None


# ---------- AIOS wrapper (mirrors your AIOSCodeGeneratorAPI pattern) ----------
class AIOSSearchSelectorAPI(BaseSearchSelector):
    """
    High-level selector using AIOS discovery and RESTBlockInference.
    """

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
            default_system_message=(
                system_message
                or "You are a careful assistant that selects exactly ONE item from a list and returns strict JSON."
            ),
        )
        self.inference_server_id: str = inference_server_id
        self.inference_server_registry_url = aios_url_map.get("inference_server_url")
        self.blocks_db_url = aios_url_map.get("blocks_db_url")

        # Load metadata/URLs
        self.block_data = self._load_block_data()
        self.inference_server_url = self._load_inference_server_data()

        # REST client to the target server
        self.block_inference = RESTBlockInference(self.inference_server_url)

        # Compose a SearchSelector that uses the discovered client
        self._selector = SearchSelector(
            client=self.block_inference,
            model=self.model,
            session_id=self.session_id,
            logger=self.logger,
            default_system_message=self.default_system_message,
        )

    # ----------------- Discovery helpers (same pattern as your code) -----------------

    def _load_inference_server_data(self) -> str:
        if self.inference_server_id.startswith(("http://", "https://")):
            return self.inference_server_id

        if not self.inference_server_registry_url:
            raise SelectionError("Missing inference_server_url in aios_url_map")

        registry_client = InferenceServerRegistryClient(self.inference_server_registry_url)
        inference_server_data = registry_client.get_inference_server(self.inference_server_id)
        if not inference_server_data:
            raise SelectionError(f"Inference server not found: {self.inference_server_id}")

        urls = inference_server_data.get("inference_server_urls") or {}
        url = urls.get("rest") or urls.get("http") or urls.get("https")
        if not url:
            raise SelectionError(f"No REST/HTTP URL found for inference server: {self.inference_server_id}")
        return url

    def _load_block_data(self) -> Dict[str, Any]:
        if not self.blocks_db_url:
            return {}
        block_client = BlocksClient(self.blocks_db_url)
        block_data = block_client.get_block_by_id(self.model)
        if not block_data:
            raise SelectionError(f"failed to query blocks data for model '{self.model}': {block_data}")
        return block_data

    # ----------------- Public API -----------------

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
        seq_no: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        system_message: Optional[str] = None,
    ) -> str:
      
        return self._selector.select_item(
            items=items,
            id_key=id_key,
            query=query,
            fields_to_show=fields_to_show,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            system_message=system_message or self.default_system_message,
            seq_no=seq_no,
            extra_headers=extra_headers,
        )
