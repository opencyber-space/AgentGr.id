import json
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import grpc

from . import service_pb2
from . import service_pb2_grpc


class GRPCBlockInferenceError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class GRPCBlockInferenceClient:

    # Try these RPC names in order; the first one present on the stub is used.
    _LIKELY_RPC_NAMES = ("Infer", "Process", "ProcessRequest", "Run", "Execute")

    def __init__(
        self,
        address: str = "127.0.0.1:50051",
        *,
        secure: bool = False,
        root_certificates: Optional[bytes] = None,
        call_metadata: Optional[List[Tuple[str, str]]] = None,
        channel_options: Optional[List[Tuple[str, Union[str, int]]]] = None,
    ):
     
        self.address = address
        self.call_metadata = call_metadata or []
        self.channel_options = channel_options or []

        if secure:
            creds = grpc.ssl_channel_credentials(root_certificates=root_certificates)
            self.channel = grpc.secure_channel(address, creds, options=self.channel_options)
        else:
            self.channel = grpc.insecure_channel(address, options=self.channel_options)

        self.stub = service_pb2_grpc.BlockInferenceServiceStub(self.channel)
        self._rpc = self._resolve_rpc(self.stub)

 
    def infer(
        self,
        *,
        model: str,
        session_id: str,
        seq_no: Union[int, str],
        data: Any,
        files: Optional[Iterable[Union[str, bytes, Dict[str, Any]]]] = None,
        selection_query: Optional[Dict[str, Any]] = None,
        graph: Optional[Dict[str, Any]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        output_ptr: Optional[Union[str, Dict[str, Any]]] = None,
        metadata: Optional[List[Tuple[str, str]]] = None,
    ) -> Dict[str, Any]:
       
        pkt = self._make_packet(
            block_id=model,
            session_id=session_id,
            seq_no=seq_no,
            data=data,
            selection_query=selection_query,
            output_ptr=output_ptr if output_ptr is not None else (graph if graph is not None else None),
            frame_ptr=frame_ptr,
            files=files,
        )
        return self._call(pkt, metadata=metadata)

    def chat_completions(
        self,
        *,
        messages: List[Dict[str, Any]],
        model: str,
        session_id: Optional[str] = None,
        seq_no: Optional[int] = None,
        selection_query: Optional[Dict[str, Any]] = None,
        graph: Optional[Dict[str, Any]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        output_ptr: Optional[Union[str, Dict[str, Any]]] = None,
        metadata: Optional[List[Tuple[str, str]]] = None,
    ) -> Dict[str, Any]:
       
        pkt = self._make_packet(
            block_id=model,
            session_id=session_id or str(uuid.uuid4()),
            seq_no=seq_no if seq_no is not None else self._now_ms(),
            data=messages,
            selection_query=selection_query,
            output_ptr=output_ptr if output_ptr is not None else (graph if graph is not None else None),
            frame_ptr=frame_ptr,
            files=None,
        )
        return self._call(pkt, metadata=metadata)

    def completions(
        self,
        *,
        prompt: Union[str, List[str]],
        model: str,
        session_id: Optional[str] = None,
        seq_no: Optional[int] = None,
        selection_query: Optional[Dict[str, Any]] = None,
        graph: Optional[Dict[str, Any]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        output_ptr: Optional[Union[str, Dict[str, Any]]] = None,
        metadata: Optional[List[Tuple[str, str]]] = None,
    ) -> Dict[str, Any]:
       
        pkt = self._make_packet(
            block_id=model,
            session_id=session_id or str(uuid.uuid4()),
            seq_no=seq_no if seq_no is not None else self._now_ms(),
            data=prompt,
            selection_query=selection_query,
            output_ptr=output_ptr if output_ptr is not None else (graph if graph is not None else None),
            frame_ptr=frame_ptr,
            files=None,
        )
        return self._call(pkt, metadata=metadata)

  
    def _resolve_rpc(self, stub) -> Any:
        for name in self._LIKELY_RPC_NAMES:
            fn = getattr(stub, name, None)
            if callable(fn):
                return fn
        # Fallback: try to deduce by listing attributes
        raise GRPCBlockInferenceError(
            f"Could not find an RPC on BlockInferenceServiceStub named any of: {', '.join(self._LIKELY_RPC_NAMES)}"
        )

    def _call(self, packet: service_pb2.BlockInferencePacket, *, metadata: Optional[List[Tuple[str, str]]] = None) -> Dict[str, Any]:
        call_md = list(self.call_metadata)
        if metadata:
            call_md.extend(metadata)
        try:
            # No timeout
            resp: service_pb2.AIOSPacket = self._rpc(packet, metadata=call_md)
        except grpc.RpcError as e:
            code = e.code().value[0] if hasattr(e.code(), "value") else None
            raise GRPCBlockInferenceError(
                f"gRPC call failed: {e.code().name if hasattr(e, 'code') else 'UNKNOWN'}",
                status_code=code,
                details=e.details() if hasattr(e, "details") else None,
            ) from e
        return self._parse_aios_packet(resp)

    def _make_packet(
        self,
        *,
        block_id: str,
        session_id: Union[str, bytes],
        seq_no: Union[int, str],
        data: Any,
        selection_query: Optional[Dict[str, Any]],
        output_ptr: Optional[Union[str, Dict[str, Any]]],
        frame_ptr: Optional[Union[str, bytes]],
        files: Optional[Iterable[Union[str, bytes, Dict[str, Any]]]],
    ) -> service_pb2.BlockInferencePacket:
        # data, query_parameters, output_ptr are strings in your server impl
        data_str = data if isinstance(data, str) else json.dumps(data)
        query_str = "" if selection_query is None else (selection_query if isinstance(selection_query, str) else json.dumps(selection_query))
        out_ptr_str = "" if output_ptr is None else (output_ptr if isinstance(output_ptr, str) else json.dumps(output_ptr))

        # frame_ptr is bytes on the wire (AIOSPacket branch encodes if str)
        frame_bytes: Optional[bytes]
        if frame_ptr is None:
            frame_bytes = None
        elif isinstance(frame_ptr, bytes):
            frame_bytes = frame_ptr
        else:
            frame_bytes = frame_ptr.encode("utf-8")

        file_infos: List[service_pb2.FileInfo] = []
        for f in (files or []):
            file_infos.append(self._normalize_fileinfo(f))

        return service_pb2.BlockInferencePacket(
            block_id=block_id or "",
            session_id=str(session_id),
            seq_no=int(seq_no),
            ts=time.time(),
            data=data_str,
            output_ptr=out_ptr_str,
            query_parameters=query_str,
            frame_ptr=frame_bytes,
            files=file_infos,
        )

    def _normalize_fileinfo(self, item: Union[str, bytes, Dict[str, Any]]) -> service_pb2.FileInfo:
      
        if isinstance(item, dict):
            raw = item.get("file_data", None)
            if raw is None:
                raise GRPCBlockInferenceError("File dict missing 'file_data'.")
            b = self._ensure_bytes(raw)
            meta = item.get("metadata", {})
            meta_str = meta if isinstance(meta, str) else json.dumps(meta or {})
            return service_pb2.FileInfo(file_data=b, metadata=meta_str)

        # path or bytes
        b = self._ensure_bytes(item)
        return service_pb2.FileInfo(file_data=b, metadata="{}")

    @staticmethod
    def _ensure_bytes(x: Union[str, bytes]) -> bytes:
        if isinstance(x, bytes):
            return x
        with open(x, "rb") as fh:
            return fh.read()

    @staticmethod
    def _parse_aios_packet(pkt: service_pb2.AIOSPacket) -> Dict[str, Any]:
       
        # data may be JSON or plain text
        raw_data = pkt.data
        if isinstance(raw_data, (bytes, bytearray)):
            try:
                raw_data = raw_data.decode("utf-8")
            except Exception:
                pass

        parsed_data: Union[Dict[str, Any], str]
        if isinstance(raw_data, str):
            try:
                parsed_data = json.loads(raw_data)
            except Exception:
                parsed_data = raw_data
        else:
            parsed_data = raw_data 

        files_out = [f.file_data for f in pkt.files]

        return {
            "session_id": pkt.session_id,
            "seq_no": pkt.seq_no,
            "ts": pkt.ts,
            "data": parsed_data,
            "files": files_out,
        }

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
