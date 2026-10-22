import random
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union


from .vdag.controller import vDAGControllerRegistryClient
from .vdag.rest import vDAGInference             
from .vdag.rpc import vDAGInferenceClient   


class ResultWaiter:
   
    def __init__(self) -> None:
        from queue import Queue
        self._q: "Queue" = Queue(maxsize=1)
        self._done = threading.Event()

    def set_result(self, value: Any) -> None:
        if not self._done.is_set():
            self._q.put(("result", value))
            self._done.set()

    def set_exception(self, exc: BaseException) -> None:
        if not self._done.is_set():
            self._q.put(("exception", exc))
            self._done.set()

    def ready(self) -> bool:
        return self._done.is_set()

    def wait(self, timeout: Optional[float] = None) -> Any:
        if not self._done.wait(timeout=timeout):
            raise TimeoutError("Result not ready within timeout")
        kind, payload = self._q.get_nowait()
        if kind == "exception":
            raise payload
        return payload


class vDAGInferenceSystem:
    
    def __init__(
        self,
        *,
        registry_base_url: str,
        vdag_uri: str,
        mode: str = "auto",  # "grpc" | "rest" | "auto"
        block_data: Optional[Dict[str, Any]] = None,
        default_headers: Optional[Dict[str, str]] = None,
    ):
        self.vdag_uri = vdag_uri
        self.mode = (mode or "auto").lower()
        self.block_data = block_data or {}

        # metrics (rolling only)
        self._lock = threading.Lock()
        self.metrics: Dict[str, float] = {
            "count": 0,
            "last_latency": 0.0,
            "min_latency": float("inf"),
            "max_latency": 0.0,
            "avg_latency": 0.0,
        }

        # 1) fetch all controllers, pick one randomly
        self._registry = vDAGControllerRegistryClient(registry_base_url, default_headers=default_headers)
        controllers = self._registry.list_vdag_controllers_by_vdag_uri(self.vdag_uri)  # List[dict]
        if not controllers:
            raise RuntimeError(f"No vDAG controllers found for URI '{self.vdag_uri}'")

        self.controller: Dict[str, Any] = random.choice(controllers)

        # 2) derive endpoints from the chosen controller (defensive extraction)
        cfg = self.controller.get("config") or {}
        urls = cfg.get("urls") or {}  # convention: config.urls.{rest,grpc}
        public_url = self.controller.get("public_url") or ""

        # REST base URL priority: urls.rest -> urls.http -> urls.https -> public_url
        self._rest_base_url = urls.get("rest") or urls.get("http") or urls.get("https") or public_url or None

        # gRPC address priority: urls.grpc -> config.grpc_address -> config.grpc_url
        self._grpc_address = urls.get("grpc") or cfg.get("grpc_address") or cfg.get("grpc_url") or None

        # 3) build clients (reuse your modules)
        self._rest = vDAGInference(self._rest_base_url) if self._rest_base_url else None
        self._grpc = vDAGInferenceClient(self._grpc_address) if self._grpc_address else None

        # finalize mode at construction
        if self.mode == "auto":
            if self._grpc:
                self.mode = "grpc"
            elif self._rest:
                self.mode = "rest"
            else:
                raise RuntimeError("No available transport on chosen controller (neither gRPC nor REST)")
        elif self.mode == "grpc":
            if not self._grpc:
                raise RuntimeError("gRPC mode requested but chosen controller has no gRPC endpoint")
        elif self.mode == "rest":
            if not self._rest:
                raise RuntimeError("REST mode requested but chosen controller has no REST endpoint")
        else:
            raise ValueError("mode must be one of: 'grpc', 'rest', 'auto'")

    def infer(
        self,
        *,
        session_id: str,
        seq_no: Union[int, str],
        data: Any,
        files: Optional[List[Union[str, bytes, Dict[str, Any]]]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,  # only used by gRPC client (optional)
        ts: Optional[float] = None,                     # only used by gRPC client (optional)
    ) -> Dict[str, Any]:
        start = time.time()
        try:
            if self.mode == "grpc":
                # gRPC vDAG client signature:
                # infer(session_id, seq_no, data, files=None, frame_ptr=None, ts=None, metadata=None)
                return self._grpc.infer(
                    session_id=session_id,
                    seq_no=seq_no,
                    data=data,
                    files=files,
                    frame_ptr=frame_ptr,
                    ts=ts,
                )
          
            return self._rest.infer(
                session_id=session_id,
                seq_no=seq_no,
                data=data,
                files=files,
            )
        finally:
            self._record_latency(time.time() - start)

    def chat_completions(
        self,
        *,
        messages: List[Dict[str, Any]],
        session_id: Optional[str] = None,
        seq_no: Optional[int] = None,
    ) -> Dict[str, Any]:
        start = time.time()
        try:
            if self.mode == "grpc":
                return self._grpc.chat_completions(
                    messages=messages,
                    session_id=session_id,
                    seq_no=seq_no,
                )
            return self._rest.chat_completions(
                messages=messages,
                session_id=session_id,
                seq_no=seq_no,
            )
        finally:
            self._record_latency(time.time() - start)

    def completions(
        self,
        *,
        prompt: Union[str, List[str]],
        session_id: Optional[str] = None,
        seq_no: Optional[int] = None,
    ) -> Dict[str, Any]:
        start = time.time()
        try:
            if self.mode == "grpc":
                return self._grpc.completions(
                    prompt=prompt,
                    session_id=session_id,
                    seq_no=seq_no,
                )
            return self._rest.completions(
                prompt=prompt,
                session_id=session_id,
                seq_no=seq_no,
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
        files: Optional[List[Tuple[str, Union[str, bytes], Optional[Dict[str, Any]]]]] = None,
    ) -> Dict[str, Any]:
        if self.mode != "rest":
            raise RuntimeError("Multipart inference is only supported in REST mode for vDAG")
        start = time.time()
        try:
            return self._rest.infer_multipart(
                session_id=session_id,
                seq_no=seq_no,
                data=data,
                ts=ts,
                frame_ptr=frame_ptr,
                files=files,
            )
        finally:
            self._record_latency(time.time() - start)


    def async_infer(
        self,
        *,
        session_id: str,
        seq_no: Union[int, str],
        data: Any,
        files: Optional[List[Union[str, bytes, Dict[str, Any]]]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        ts: Optional[float] = None,
    ) -> ResultWaiter:
        rw = ResultWaiter()

        def _worker():
            try:
                res = self.infer(
                    session_id=session_id,
                    seq_no=seq_no,
                    data=data,
                    files=files,
                    frame_ptr=frame_ptr,
                    ts=ts,
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
    ) -> ResultWaiter:
        rw = ResultWaiter()

        def _worker():
            try:
                res = self.chat_completions(
                    messages=messages,
                    session_id=session_id,
                    seq_no=seq_no,
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
    ) -> ResultWaiter:
        rw = ResultWaiter()

        def _worker():
            try:
                res = self.completions(
                    prompt=prompt,
                    session_id=session_id,
                    seq_no=seq_no,
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
        files: Optional[List[Tuple[str, Union[str, bytes], Optional[Dict[str, Any]]]]] = None,
    ) -> ResultWaiter:
        rw = ResultWaiter()

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


    def get_metrics(self) -> Dict[str, float]:
        with self._lock:
            return dict(self.metrics)

    def _record_latency(self, latency: float) -> None:
        with self._lock:
            c = int(self.metrics["count"]) + 1
            self.metrics["count"] = c
            self.metrics["last_latency"] = latency
            self.metrics["min_latency"] = min(self.metrics["min_latency"], latency)
            self.metrics["max_latency"] = max(self.metrics["max_latency"], latency)
            prev_avg = self.metrics["avg_latency"]
            self.metrics["avg_latency"] = prev_avg + (latency - prev_avg) * (1.0 / c)
