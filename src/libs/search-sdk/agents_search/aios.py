import logging
import uuid
import time
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .block.rest import RESTBlockInference
from .block.block_client import BlocksClient
from .block.inference_server import InferenceServerRegistryClient
from .custom import BaseSearchSelector, BaseSearchRanker


class SelectionError(RuntimeError):
    pass


# ---------- Core selector (LLM-driven) ----------
class SearchSelector:
    

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
        
        if not items:
            raise SelectionError("No items provided for selection.")

        # Pre-validate and render a compact view of items for the prompt
        normalized = self._normalize_items(items, id_key=id_key)
        prompt = self._build_prompt(normalized, id_key=id_key, query=query, fields_to_show=fields_to_show)

        logging.info(f"[Prompt] {prompt}")

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



class RankingError(Exception):
    pass


class SearchRanker:
    

    def __init__(
        self,
        *,
        client: "RESTBlockInference",
        model: str,
        session_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        default_system_message: str = (
            "Use valid IDs always provided from the list, don't invent your own IDs"
            "You are a careful assistant that *scores and ranks* a list of items by "
            "relevance to the user query.\n"
            "You MUST output strict JSON in ONE of the following formats:\n"
            "1) An array of objects:\n"
            "   [\n"
            '     {"id": "<ID>", "score": <number between 0 and 1>},\n'
            "     ...\n"
            "   ]\n"
            "   - Include EVERY item exactly once.\n"
            "   - The array MUST be sorted by score in descending order.\n"
            "\n"
            "OR\n"
            "\n"
            "2) A JSON object of id → score mappings:\n"
            "   {\n"
            '     "<ID1>": <number between 0 and 1>,\n'
            '     "<ID2>": <number between 0 and 1>,\n'
            "     ...\n"
            "   }\n"
            "   - Include EVERY item exactly once.\n"
            "   - Higher score = more relevant.\n"
            "\n"
            "Do not output anything except the JSON."
        ),
    ) -> None:
        self.client = client
        self.model = model
        self.session_id = session_id or f"search-rank-{uuid.uuid4()}"
        self.logger = logger or logging.getLogger(__name__)
        self.default_system_message = default_system_message

    # ------------- Public API -------------

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
        seq_no: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        **_: Any,
    ) -> List[Tuple[str, float]]:
        if not items:
            raise RankingError("No items provided for ranking.")

        # 1) normalize
        normalized = self._normalize_items(items, id_key=id_key)

        # 2) IMPORTANT: keep BOTH list (for order) and set (for membership)
        id_order: List[str] = [str(it[id_key]) for it in normalized]  # list, indexable
        id_set = set(id_order)                                        # set, for fast lookup

        # 3) build prompt
        prompt = self._build_prompt(
            normalized,
            id_key=id_key,
            query=query,
            fields_to_show=fields_to_show,
        )

        logging.info(f"[Prompt] {prompt}")

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

        # 4) call inference
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
            self.logger.exception("Search ranking request failed")
            raise RankingError(str(e)) from e

        # 5) parse response
        text = self._extract_reply_text(raw)
        parsed = self._extract_json(text)

        scores = self._parse_scores(parsed, id_order)

        # and pass the SET to finalize
        ranked = self._finalize_and_sort(scores, id_set)
        return ranked


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
                    raise RankingError(f"Item at index {i} is not a dict and cannot be converted.")
            if id_key not in it:
                raise RankingError(f"Item at index {i} missing required id key '{id_key}'.")
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
        """
        Build a ranking-specific prompt (different from selector).
        """
        lines: List[str] = []
        for it in items:
            view = {id_key: it.get(id_key)}
            if fields_to_show:
                # Only the requested fields + id
                for k in fields_to_show:
                    if k != id_key and k in it:
                        v = str(it[k])
                        view[k] = (v[:300] + "…") if len(v) > 300 else v
            else:
                # Heuristic: include a few non-ID keys
                extra = {k: v for k, v in it.items() if k != id_key}
                keys = list(extra.keys())[:4]
                for k in keys:
                    v = str(extra[k])
                    view[k] = (v[:300] + "…") if len(v) > 300 else v

            compact = ", ".join(f"{k}={view[k]}" for k in view)
            lines.append(f"- {id_key}={it[id_key]} | {compact}")

        instructions = [
            "You are given a list of items. (Agent)",
            "Each item has an ID and a text representation with description, tags, and persona.",
            "",
            "Your job is to assign a relevance score in [0, 1] to EVERY item.",
            "",
            "Relevance definition:",
            "- Base relevance on how well the item's description, tags, and persona MATCH the user query.",
            "  when the query clearly indicates a specific domain.",
            "",
            "Rules:",
            "- Higher score = more relevant to the user query.",
            "- You MUST provide a score for every single ID in the list.",
            "- Use the EXACT item IDs from the list as keys (e.g., 'tech-agent', 'router-agent').",
            "- Do NOT use numeric keys like '1', '2', etc.",
            "- Output strict JSON ONLY, no prose.",
            "- Follow the output format described in the system message.",
        ]

        if query:
            instructions.append(f"\nUser query / ranking hint:\n{query}")

        return "\n".join(instructions) + "\n\nItems:\n" + "\n".join(lines) + "\n\nReturn JSON now."

    def _extract_reply_text(self, raw: Dict[str, Any]) -> str:
        try:
            reply = raw["data"]["reply"]
        except Exception:
            self.logger.error("Response did not contain expected 'data.reply': %r", raw)
            raise RankingError("No reply found in response.")
        if not isinstance(reply, str) or not reply.strip():
            raise RankingError("Empty reply in response.")
        return reply.strip()

    def _extract_json(self, text: str) -> Any:
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
        raise RankingError("Model did not return valid JSON.")

    @staticmethod
    def _largest_json_object(s: str) -> Optional[str]:
        """
        Find the largest balanced {...} substring (simple heuristic).
        """
        first = s.find("{")
        last = s.rfind("}")
        if first != -1 and last != -1 and last > first:
            return s[first : last + 1]
        # Keep the same style as your selector (even if regex engine may differ)
        m = re.search(r"\{(?:[^{}]|(?R))*\}", s)
        return m.group(0) if m else None

    # ---------- Ranking JSON parsing ----------

    def _parse_scores(self, parsed: Any, id_order: List[str]) -> Dict[str, float]:
        """
        Convert the model JSON into a mapping of id -> score.

        Supports two cases:

        1) Proper ID keys:
           - [{"id": "<ID>", "score": <number>}, ...]
           - {"<ID1>": <number>, "<ID2>": <number>, ...}

        2) Ordinal numeric keys:
           - {"1": 0.9, "2": 0.8, ...}
             where "1" means "first item in the prompt", etc.
        """
        id_set = set(id_order)
        scores: Dict[str, float] = {}

        # --- Case 2: numeric ordinals as keys (what you're seeing now) ---
        if isinstance(parsed, dict) and parsed and all(str(k).isdigit() for k in parsed.keys()):
            self.logger.debug("Parsed ranking output uses ordinal numeric keys; mapping to ID order.")
            try:
                # Sort by numeric key: "1", "2", "3", ...
                ordered_pairs = sorted(
                    parsed.items(),
                    key=lambda kv: int(str(kv[0]))
                )
            except Exception:
                # If something weird happens, fall back to normal path
                ordered_pairs = list(parsed.items())

            for idx, (_, score_raw) in enumerate(ordered_pairs):
                if idx >= len(id_order):
                    break
                sid = id_order[idx]
                try:
                    score = float(score_raw)
                except (TypeError, ValueError):
                    score = 0.0
                scores[sid] = score

            if not scores:
                raise RankingError("No valid scores produced from ordinal-key ranking output.")

            return scores

        # --- Case 1a: list of {id, score} ---
        if isinstance(parsed, list):
            for obj in parsed:
                if not isinstance(obj, dict):
                    continue
                sid = str(obj.get("id", "")).strip()
                if not sid or sid not in id_set:
                    continue
                try:
                    score = float(obj.get("score", 0.0))
                except (TypeError, ValueError):
                    score = 0.0
                scores[sid] = score

        # --- Case 1b: dict of id -> score ---
        elif isinstance(parsed, dict):
            # Guard against selector-style output
            if "selected_id" in parsed:
                raise RankingError(
                    "Model returned selection-style JSON (selected_id). "
                    "SearchRanker expects scores for all IDs."
                )

            for sid_raw, score_raw in parsed.items():
                sid = str(sid_raw).strip()
                if sid not in id_set:
                    continue
                try:
                    score = float(score_raw)
                except (TypeError, ValueError):
                    score = 0.0
                scores[sid] = score

        else:
            self.logger.error("Unexpected ranking JSON type: %r", type(parsed))
            raise RankingError("Model did not return a valid ranking JSON structure.")

        if not scores:
            raise RankingError("No valid scores produced for any items.")

        return scores

    def _finalize_and_sort(
        self,
        scores: Dict[str, float],
        valid_ids: set,
    ) -> List[Tuple[str, float]]:
        """
        Ensure every valid ID has a score, clamp scores into [0, 1], and sort DESC.
        """
        # Ensure every ID is present
        for vid in valid_ids:
            if vid not in scores:
                scores[vid] = 0.0

        normalized_scores: Dict[str, float] = {}
        for sid, sc in scores.items():
            try:
                v = float(sc)
            except (TypeError, ValueError):
                v = 0.0
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


class AIOSSearchRankerAPI(BaseSearchRanker):

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
                or (
                    "You are a careful assistant that scores and ranks a list of items by "
                    "relevance to the query, and returns strict JSON with scores for each ID."
                )
            ),
        )
        self.inference_server_id: str = inference_server_id
        self.inference_server_registry_url = aios_url_map.get("inference_server_url")
        self.blocks_db_url = aios_url_map.get("blocks_db_url")

        # Load metadata/URLs
        self.block_data = self._load_block_data()
        self.inference_server_url = self._load_inference_server_data()

        self.block_inference = RESTBlockInference(self.inference_server_url)

        self._ranker = SearchRanker(
            client=self.block_inference,
            model=self.model,
            session_id=self.session_id,
            logger=self.logger,
            default_system_message=self.default_system_message,
        )


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
        seq_no: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        system_message: Optional[str] = None,
    ) -> List[Tuple[str, float]]:
       
        return self._ranker.rank_items(
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