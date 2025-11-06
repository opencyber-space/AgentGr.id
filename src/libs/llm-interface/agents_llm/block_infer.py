import time
import threading
from typing import Any, Dict, List, Optional, Tuple, Union
import json

from .block.inference_server import InferenceServerRegistryClient
from .block.rest import RESTBlockInference
from .block.rpc import GRPCBlockInferenceClient

from .blocks import BlocksClient
from .policy_sandbox import LocalPolicyEvaluator


class PolicyEvaluator:

    def __init__(self, block_data, name="agents_pre_processing") -> None:

        policies = self.block_data.get('policies', {})
        self.block_data = block_data

        if name in policies:
            policy_settings = policies[name].get(
                'settings', {})
            policy_parameters = policies[name].get(
                'parameters', {})
            policy_rule_uri = policies[name].get("policyRuleURI", "")

           
            self.policy = LocalPolicyEvaluator(
                policy_rule_uri,
                parameters=policy_parameters,
                settings=policy_settings
            )
        else:
            self.policy = None

    def execute(self, data, mode):
        if not self.policy:
            return data
        
        return self.policy.execute_policy_rule({
            "input": data,
            "mode": mode,
            "block_data": self.block_data
        })


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


class BlockInferenceSystem:

    def __init__(
        self,
        *,
        network_host: str,
        inference_server_id: str,
        model: str,
        block_data: Optional[Dict[str, Any]] = None,
        mode: str = "auto",  # "grpc" | "rest" | "auto"
        default_headers: Optional[Dict[str, str]] = None,
        urls={}
    ):
        self.model = model
        self.block_data = block_data or {}
        self.mode = (mode or "auto").lower()

        self._rest_base_url = None
        self._grpc_address = None

        # metrics
        self._lock = threading.Lock()
        self.metrics: Dict[str, float] = {
            "count": 0,
            "last_latency": 0.0,
            "min_latency": float("inf"),
            "max_latency": 0.0,
            "avg_latency": 0.0,
        }

        if inference_server_id != "":
            # 1) fetch + save inference server record
            registry_base_url = f"http://{network_host}:30105"
            self._registry = InferenceServerRegistryClient(
                registry_base_url, default_headers=default_headers)
            self.inference_server = self._registry.get_inference_server(
                inference_server_id)  # dict

            # 2) derive endpoints
            urls = self.inference_server.get("inference_server_urls") or {}
            public_url = self.inference_server.get(
                "inference_server_public_url") or ""

            self._rest_base_url = urls.get("rest") or urls.get(
                "http") or urls.get("https") or public_url
            self._grpc_address = urls.get("grpc") or urls.get(
                "grpc_address") or urls.get("grpc_url")

        else:

            if not urls:
                raise Exception("No inference server ID or URLs provided")

            inference_server_url_rest = urls.get('rest')
            inference_server_url_grpc = urls.get('grpc')

            if mode == "auto" and inference_server_url_rest != "":
                self._rest_base_url = inference_server_url_rest
            elif mode == "auto" and inference_server_url_grpc != "":
                self._grpc_address = inference_server_url_grpc

            elif mode == "grpc":
                if inference_server_url_grpc == "":
                    raise Exception("gRPC address not provided")

                self._grpc_address = inference_server_url_grpc
            elif mode == "rest":
                if inference_server_url_rest == "":
                    raise Exception("REST address not provided")

                self._rest_base_url = inference_server_url_rest

        # 3) instantiate existing clients
        self._rest = RESTBlockInference(
            self._rest_base_url) if self._rest_base_url else None
        self._grpc = GRPCBlockInferenceClient(
            self._grpc_address) if self._grpc_address else None

        # finalize mode at construction
        if self.mode == "auto":
            if self._grpc:
                self.mode = "grpc"
            elif self._rest:
                self.mode = "rest"
            else:
                raise RuntimeError(
                    "No available transport (neither gRPC nor REST)")
        elif self.mode == "grpc":
            if not self._grpc:
                raise RuntimeError(
                    "gRPC mode requested but no gRPC endpoint available")
        elif self.mode == "rest":
            if not self._rest:
                raise RuntimeError(
                    "REST mode requested but no REST endpoint available")
        else:
            raise ValueError("mode must be one of: 'grpc', 'rest', 'auto'")

        # obtain block data and initialize pre and post processing policies:
        block_registry_url = f"http://{network_host}:30100"
        block_data = BlocksClient(block_registry_url).get_block_by_id(model)

        self.block_data = block_data

        # gather pre and post processing policy info:
        self.pre_processor = PolicyEvaluator(self.block_data, name="agents_pre_processing")
        self.post_processor = PolicyEvaluator(self.block_data, name="agents_post_processing")

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
        start = time.time()


        data = self.pre_processor.execute(data, mode="raw_infer")

        data = json.dumps(data)
        try:
            if self.mode == "grpc":
                resp =  self._grpc.infer(
                    model=self.model,
                    session_id=session_id,
                    seq_no=seq_no,
                    data=data,
                    files=files,
                    selection_query=selection_query,
                    graph=graph,
                    frame_ptr=frame_ptr,
                    output_ptr=output_ptr,
                )

                return self.post_processor.execute(resp, mode="raw_infer")

            # REST
            resp = self._rest.infer(
                model=self.model,
                session_id=session_id,
                seq_no=seq_no,
                data=data,
                files=files,
                selection_query=selection_query,
                graph=graph,
            )

            return self.post_processor.execute(resp, mode="raw_infer")

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
        data: dict,
    ) -> Dict[str, Any]:
        start = time.time()

        if messages:
            data["messages"] = messages

        data = self.pre_processor.execute(data, mode="chat_completions")

        try:
            if self.mode == "grpc":
                resp =  self._grpc.chat_completions(
                    model=self.model,
                    messages=data,
                    session_id=session_id,
                    seq_no=seq_no,
                    selection_query=selection_query,
                    graph=graph,
                    frame_ptr=frame_ptr,
                    output_ptr=output_ptr,
                )

                return self.post_processor.execute(resp, mode="chat_completions")

            resp = self._rest.chat_completions(
                model=self.model,
                messages=data,
                session_id=session_id,
                seq_no=seq_no,
                selection_query=selection_query,
                graph=graph,
            )

            return self.post_processor.execute(resp, mode="chat_completions")

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
        data=None
    ) -> Dict[str, Any]:
        start = time.time()

        if prompt:
            data['prompt'] = prompt

        data = self.pre_processor.execute(data, mode="completions")

        data = json.dumps(data)
        try:
            if self.mode == "grpc":
                resp =  self._grpc.completions(
                    model=self.model,
                    prompt=prompt,
                    session_id=session_id,
                    seq_no=seq_no,
                    selection_query=selection_query,
                    graph=graph,
                    frame_ptr=frame_ptr,
                    output_ptr=output_ptr,
                )

                return self.post_processor.execute(resp, mode="completions")

            resp =  self._rest.completions(
                model=self.model,
                prompt=prompt,
                session_id=session_id,
                seq_no=seq_no,
                selection_query=selection_query,
                graph=graph,
            )

            return self.post_processor.execute(resp, mode="completions")

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
        if self.mode != "rest":
            raise RuntimeError(
                "Multipart inference is only supported in REST mode")
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
        selection_query: Optional[Dict[str, Any]] = None,
        graph: Optional[Dict[str, Any]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        output_ptr: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> ResultWaiter:
        rw = ResultWaiter()

        data = json.dumps(data)

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
        rw = ResultWaiter()

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
        data=None
    ) -> ResultWaiter:
        rw = ResultWaiter()

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
                    data=data
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
            self.metrics["min_latency"] = min(
                self.metrics["min_latency"], latency)
            self.metrics["max_latency"] = max(
                self.metrics["max_latency"], latency)
            prev_avg = self.metrics["avg_latency"]
            self.metrics["avg_latency"] = prev_avg + \
                (latency - prev_avg) * (1.0 / c)
