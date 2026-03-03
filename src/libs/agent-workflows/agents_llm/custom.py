from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union
import os
import pprint
from openai import OpenAI, APIConnectionError, BadRequestError, RateLimitError

from .block_infer import ResultWaiter


class AbstractBlockInferenceSystem(ABC):

    def __init__(
        self,
        *,
        model: str,
        block_data: Optional[Dict[str, Any]] = None,
        mode: str = "auto",
    ):
        self.model = model
        self.block_data = block_data or {}
        self.mode = (mode or "auto").lower()

        # Thread-safe metrics
        self._lock = threading.Lock()
        self._metrics: Dict[str, float] = {
            "count": 0,
            "last_latency": 0.0,
            "min_latency": float("inf"),
            "max_latency": 0.0,
            "avg_latency": 0.0,
        }

        self._finalize_mode()

    def infer(
        self,
        *,
        session_id: str,
        seq_no: Union[int, str],
        data: Any,
        files: Optional[List[Union[str, bytes, Dict[str, Any]]]] = None,
        selection_query: Optional[Dict[str, Any]] = None,
        graph: Optional[Dict[str, Any]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        output_ptr: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        self._check_mode("infer")
        start = time.time()
        try:
            return self._do_infer(
                session_id=session_id,
                seq_no=seq_no,
                data=data,
                files=files,
                selection_query=selection_query,
                graph=graph,
                frame_ptr=frame_ptr,
                output_ptr=output_ptr,
            )
        finally:
            self._record_latency(time.time() - start)

    def chat_completions(
        self,
        *,
        messages: List[Dict[str, Any]],
        session_id: Optional[str] = None,
        seq_no: Optional[int] = None,
        selection_query: Optional[Dict[str, Any]] = None,
        graph: Optional[Dict[str, Any]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        output_ptr: Optional[Union[str, Dict[str, Any]]] = None,
        data: Dict = None
    ) -> Dict[str, Any]:
        self._check_mode("chat_completions")
        start = time.time()

        print(f'chat completions: {messages}')

        try:
            return self._do_chat_completions(
                messages=messages,
                session_id=session_id,
                seq_no=seq_no,
                selection_query=selection_query,
                graph=graph,
                frame_ptr=frame_ptr,
                output_ptr=output_ptr,
                data=data,
            )
        except Exception as e:
            print('exception', e)
        finally:
            self._record_latency(time.time() - start)

    def completions(
        self,
        *,
        prompt: Union[str, List[str]],
        session_id: Optional[str] = None,
        seq_no: Optional[int] = None,
        selection_query: Optional[Dict[str, Any]] = None,
        graph: Optional[Dict[str, Any]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        output_ptr: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        self._check_mode("completions")
        start = time.time()
        try:
            return self._do_completions(
                prompt=prompt,
                session_id=session_id,
                seq_no=seq_no,
                selection_query=selection_query,
                graph=graph,
                frame_ptr=frame_ptr,
                output_ptr=output_ptr,
            )
        finally:
            self._record_latency(time.time() - start)

    def infer_multipart(
        self,
        *,
        session_id: str,
        seq_no: int,
        data: Union[str, Dict[str, Any]],
        ts: Optional[float] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        files: Optional[List[Tuple[str, Union[str, bytes],
                                   Optional[Dict[str, Any]]]]] = None,
    ) -> Dict[str, Any]:
        # e.g., subclass may enforce REST-only
        self._check_mode("infer_multipart")
        start = time.time()
        try:
            return self._do_infer_multipart(
                session_id=session_id,
                seq_no=seq_no,
                data=data,
                ts=ts,
                frame_ptr=frame_ptr,
                files=files,
            )
        finally:
            self._record_latency(time.time() - start)

    # ---------- Public asynchronous wrappers (return ResultWaiter) ----------

    def async_infer(
        self,
        *,
        session_id: str,
        seq_no: Union[int, str],
        data: Any,
        files: Optional[List[Union[str, bytes, Dict[str, Any]]]] = None,
        selection_query: Optional[Dict[str, Any]] = None,
        graph: Optional[Dict[str, Any]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        output_ptr: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> ResultWaiter:
        rw = self._new_result_waiter()

        def _worker():
            try:
                res = self.infer(
                    session_id=session_id,
                    seq_no=seq_no,
                    data=data,
                    files=files,
                    selection_query=selection_query,
                    graph=graph,
                    frame_ptr=frame_ptr,
                    output_ptr=output_ptr,
                )


                rw.set_result(res)
            except BaseException as e:
                rw.set_exception(e)

        threading.Thread(target=_worker, daemon=True).start()
        return rw

    def async_chat_completions(
        self,
        *,
        messages: List[Dict[str, Any]],
        session_id: Optional[str] = None,
        seq_no: Optional[int] = None,
        selection_query: Optional[Dict[str, Any]] = None,
        graph: Optional[Dict[str, Any]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        output_ptr: Optional[Union[str, Dict[str, Any]]] = None,
        data=None,
    ) -> ResultWaiter:
        rw = self._new_result_waiter()

        print('got data', data)
        print('got messages', messages)

        def _worker():
            try:
                res = self.chat_completions(
                    messages=messages,
                    session_id=session_id,
                    seq_no=seq_no,
                    selection_query=selection_query,
                    graph=graph,
                    frame_ptr=frame_ptr,
                    output_ptr=output_ptr,
                    data=data
                )

                rw.set_result(res)
            except BaseException as e:
                rw.set_exception(e)

        threading.Thread(target=_worker, daemon=True).start()
        return rw

    def async_completions(
        self,
        *,
        prompt: Union[str, List[str]],
        session_id: Optional[str] = None,
        seq_no: Optional[int] = None,
        selection_query: Optional[Dict[str, Any]] = None,
        graph: Optional[Dict[str, Any]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        output_ptr: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> ResultWaiter:
        rw = self._new_result_waiter()

        def _worker():
            try:
                res = self.completions(
                    prompt=prompt,
                    session_id=session_id,
                    seq_no=seq_no,
                    selection_query=selection_query,
                    graph=graph,
                    frame_ptr=frame_ptr,
                    output_ptr=output_ptr,
                )
                rw.set_result(res)
            except BaseException as e:
                rw.set_exception(e)

        threading.Thread(target=_worker, daemon=True).start()
        return rw

    def async_infer_multipart(
        self,
        *,
        session_id: str,
        seq_no: int,
        data: Union[str, Dict[str, Any]],
        ts: Optional[float] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        files: Optional[List[Tuple[str, Union[str, bytes],
                                   Optional[Dict[str, Any]]]]] = None,
    ) -> ResultWaiter:
        rw = self._new_result_waiter()

        def _worker():
            try:
                res = self.infer_multipart(
                    session_id=session_id,
                    seq_no=seq_no,
                    data=data,
                    ts=ts,
                    frame_ptr=frame_ptr,
                    files=files,
                )
                rw.set_result(res)
            except BaseException as e:
                rw.set_exception(e)

        threading.Thread(target=_worker, daemon=True).start()
        return rw

    # ---------- Metrics ----------

    def get_metrics(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._metrics)

    # ---------- Hooks for subclasses ----------

    def _finalize_mode(self) -> None:
        """
        Optional: subclasses can resolve 'auto' to 'grpc'/'rest', validate endpoints, etc.
        """
        pass

    def _check_mode(self, operation: str) -> None:
        """
        Optional: enforce transport constraints.
        Example (REST-only multipart):
            if operation == "infer_multipart" and self.mode != "rest":
                raise RuntimeError("Multipart inference is only supported in REST mode")
        """
        pass

    def _new_result_waiter(self) -> ResultWaiter:
        """
        Factory for async waiters. Subclasses can override to return their own ResultWaiter.
        The object must implement set_result(value) and set_exception(exc).
        """
        return ResultWaiter()

    # ---------- Abstract transport-specific implementations ----------

    @abstractmethod
    def _do_infer(
        self,
        *,
        session_id: str,
        seq_no: Union[int, str],
        data: Any,
        files: Optional[List[Union[str, bytes, Dict[str, Any]]]],
        selection_query: Optional[Dict[str, Any]],
        graph: Optional[Dict[str, Any]],
        frame_ptr: Optional[Union[str, bytes]],
        output_ptr: Optional[Union[str, Dict[str, Any]]],
    ) -> Dict[str, Any]:
        ...

    @abstractmethod
    def _do_chat_completions(
        self,
        *,
        messages: List[Dict[str, Any]],
        session_id: Optional[str],
        seq_no: Optional[int],
        selection_query: Optional[Dict[str, Any]],
        graph: Optional[Dict[str, Any]],
        frame_ptr: Optional[Union[str, bytes]],
        output_ptr: Optional[Union[str, Dict[str, Any]]],
        data={}
    ) -> Dict[str, Any]:
        ...

    @abstractmethod
    def _do_completions(
        self,
        *,
        prompt: Union[str, List[str]],
        session_id: Optional[str],
        seq_no: Optional[int],
        selection_query: Optional[Dict[str, Any]],
        graph: Optional[Dict[str, Any]],
        frame_ptr: Optional[Union[str, bytes]],
        output_ptr: Optional[Union[str, Dict[str, Any]]],
    ) -> Dict[str, Any]:
        ...

    @abstractmethod
    def _do_infer_multipart(
        self,
        *,
        session_id: str,
        seq_no: int,
        data: Union[str, Dict[str, Any]],
        ts: Optional[float],
        frame_ptr: Optional[Union[str, bytes]],
        files: Optional[List[Tuple[str, Union[str, bytes], Optional[Dict[str, Any]]]]],
    ) -> Dict[str, Any]:
        ...

    # ---------- Internals ----------

    def _record_latency(self, latency: float) -> None:
        with self._lock:
            c = int(self._metrics["count"]) + 1
            self._metrics["count"] = c
            self._metrics["last_latency"] = latency
            self._metrics["min_latency"] = min(
                self._metrics["min_latency"], latency)
            self._metrics["max_latency"] = max(
                self._metrics["max_latency"], latency)
            prev_avg = self._metrics["avg_latency"]
            self._metrics["avg_latency"] = prev_avg + \
                (latency - prev_avg) * (1.0 / c)


class OpenAIBlockInferenceSystem(AbstractBlockInferenceSystem):
   

    # Only forward these keys to OpenAI to avoid 4xx for unknown fields
    _CHAT_KEYS = {
        "messages", "temperature", "top_p", "max_tokens", "n", "stop",
        "presence_penalty", "frequency_penalty", "logit_bias", "user",
        "tools", "tool_choice", "response_format", "seed", "metadata"
    }
    _TEXT_KEYS = {
        "prompt", "temperature", "top_p", "max_tokens", "n", "stop",
        "presence_penalty", "frequency_penalty", "logit_bias", "user", "seed", "metadata"
    }

    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,  
        organization: Optional[str] = None,
        project: Optional[str] = None,
        block_data: Optional[Dict[str, Any]] = None,
        mode: str = "auto",
        default_system_prompt: Optional[str] = None,
    ):
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self._api_key:
            raise ValueError(
                "OpenAI API key is required (set OPENAI_API_KEY or pass api_key=).")

        self._default_system_prompt = default_system_prompt

        # Create client
        self.client = OpenAI(
            api_key=self._api_key,
            base_url=base_url,
            organization=organization,
            project=project,
        )

        super().__init__(model=model, block_data=block_data, mode=mode)

    # ---------- Hooks ----------

    def _finalize_mode(self) -> None:
        # OpenAI SDK is REST-only here
        self.mode = "rest"

    def _check_mode(self, operation: str) -> None:
        if operation == "infer_multipart":
            raise RuntimeError(
                "Multipart inference is not supported for OpenAI.")

    # ---------- Helpers ----------

    def _is_chat_payload(self, data: Dict[str, Any]) -> bool:
        return isinstance(data.get("messages"), list)

    def _maybe_with_system(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        #if self._default_system_prompt and (not messages or messages[0].get("role") != "system"):
        #    return [{"role": "system", "content": self._default_system_prompt}] + messages
        return messages

    def _prep_chat_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:

        print('data for chat payload', data)
        payload = {k: v for k, v in data.items() if k in self._CHAT_KEYS}
        payload["model"] = self.model
        return payload

    def _prep_text_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = {k: v for k, v in data.items() if k in self._TEXT_KEYS}
        payload["model"] = self.model
        return payload

    # ---------- Core dispatchers (use ONLY `data` for variable fields) ----------

    def _do_infer(
        self,
        *,
        session_id: str,
        seq_no: Union[int, str],
        data: Any,
        files: Optional[List[Union[str, bytes, Dict[str, Any]]]],
        selection_query: Optional[Dict[str, Any]],
        graph: Optional[Dict[str, Any]],
        frame_ptr: Optional[Union[str, bytes]],
        output_ptr: Optional[Union[str, Dict[str, Any]]],
    ) -> Dict[str, Any]:
       
        try:
            # messages path (dict)
            if isinstance(data, dict) and "messages" in data and isinstance(data["messages"], list):
                return self._invoke_chat(data=data, session_id=session_id, seq_no=seq_no)

            # messages path (list of role/content dicts)
            if isinstance(data, list) and data and isinstance(data[0], dict) and "role" in data[0]:
                return self._invoke_chat(data={"messages": data}, session_id=session_id, seq_no=seq_no)

            # completions path (dict with prompt or raw prompt)
            if isinstance(data, dict) and "prompt" in data:
                return self._invoke_text(data=data, session_id=session_id, seq_no=seq_no)

            if isinstance(data, (str, list)):
                return self._invoke_text(data={"prompt": data}, session_id=session_id, seq_no=seq_no)

            raise BadRequestError(
                "`data` must include 'messages' (chat) or 'prompt' (text).")

        except (APIConnectionError, RateLimitError, BadRequestError):
            raise  

    def _invoke_chat(self, *, data: Dict[str, Any], session_id: Union[str, None], seq_no: Union[int, str, None]) -> Dict[str, Any]:
        payload = self._prep_chat_payload(data)
        payload['model'] = self.model

        resp = self.client.chat.completions.create(**payload)

        return {
            "id": resp.id,
            "object": resp.object,
            "created": resp.created,
            "model": resp.model,
            "choices": [c.dict() if hasattr(c, "dict") else c for c in resp.choices],
            "usage": resp.usage.dict() if hasattr(resp.usage, "dict") else getattr(resp, "usage", None),
            "session_id": session_id,
            "seq_no": int(seq_no) if isinstance(seq_no, str) and seq_no.isdigit() else seq_no,
        }

    def _invoke_text(self, *, data: Dict[str, Any], session_id: Union[str, None], seq_no: Union[int, str, None]) -> Dict[str, Any]:
        payload = self._prep_text_payload(data)
        try:
            resp = self.client.completions.create(**payload)
            return {
                "id": resp.id,
                "object": resp.object,
                "created": resp.created,
                "model": resp.model,
                "choices": [c.dict() if hasattr(c, "dict") else c for c in resp.choices],
                "usage": resp.usage.dict() if hasattr(resp.usage, "dict") else getattr(resp, "usage", None),
                "session_id": session_id,
                "seq_no": int(seq_no) if isinstance(seq_no, str) and seq_no.isdigit() else seq_no,
            }
        except BadRequestError as e:
            # Fallback to chat if the model doesn't support /v1/completions
            if "does not exist" in str(e).lower() or "not support" in str(e).lower():
                chat_payload = {
                    "messages": self._maybe_with_system([
                        {"role": "user", "content": payload.get("prompt") if not isinstance(payload.get("prompt"), list)
                         else "\n\n".join(payload.get("prompt", []))}
                    ])
                }
                # carry over tunables like temperature/max_tokens if present
                for k in ("temperature", "top_p", "max_tokens", "n", "stop",
                          "presence_penalty", "frequency_penalty", "logit_bias", "user", "seed", "metadata"):
                    if k in payload:
                        chat_payload[k] = payload[k]
                chat_payload["model"] = self.model
                chat_resp = self.client.chat.completions.create(**chat_payload)
                return {
                    "id": chat_resp.id,
                    "object": chat_resp.object,
                    "created": chat_resp.created,
                    "model": chat_resp.model,
                    "choices": [c.dict() if hasattr(c, "dict") else c for c in chat_resp.choices],
                    "usage": chat_resp.usage.dict() if hasattr(chat_resp.usage, "dict") else getattr(chat_resp, "usage", None),
                    "session_id": session_id,
                    "seq_no": int(seq_no) if isinstance(seq_no, str) and seq_no.isdigit() else seq_no,
                    "_fallback": "chat_completions",
                }
            raise

    def _do_chat_completions(
        self,
        *,
        messages: List[Dict[str, Any]],
        session_id: Optional[str],
        seq_no: Optional[int],
        selection_query: Optional[Dict[str, Any]],
        graph: Optional[Dict[str, Any]],
        frame_ptr: Optional[Union[str, bytes]],
        output_ptr: Optional[Union[str, Dict[str, Any]]],
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        data["messages"] = messages
        return self._invoke_chat(data=data, session_id=session_id, seq_no=seq_no)

    def _do_completions(
        self,
        *,
        prompt: Union[str, List[str]],
        session_id: Optional[str],
        seq_no: Optional[int],
        selection_query: Optional[Dict[str, Any]],
        graph: Optional[Dict[str, Any]],
        frame_ptr: Optional[Union[str, bytes]],
        output_ptr: Optional[Union[str, Dict[str, Any]]],
        # allow passing extra variable params here too
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        call_data = {"prompt": prompt}
        if isinstance(data, dict):
            call_data.update(data)  # merge any variable tunables from data
        return self._invoke_text(data=call_data, session_id=session_id, seq_no=seq_no)

    def _do_infer_multipart(
        self,
        *,
        session_id: str,
        seq_no: int,
        data: Union[str, Dict[str, Any]],
        ts: Optional[float],
        frame_ptr: Optional[Union[str, bytes]],
        files: Optional[List[Tuple[str, Union[str, bytes], Optional[Dict[str, Any]]]]],
    ) -> Dict[str, Any]:
        raise RuntimeError("Multipart inference is not supported for OpenAI.")
