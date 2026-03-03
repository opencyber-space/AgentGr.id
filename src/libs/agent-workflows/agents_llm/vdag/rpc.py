import json
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import grpc

from . import vdag_service_pb2
from . import vdag_service_pb2_grpc


class vDAGInferenceGRPCError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class vDAGInferenceClient:
   

    _LIKELY_RPC_NAMES = ("Infer", "infer", "Run", "Execute", "Process", "ProcessRequest")

    def __init__(
        self,
        address: str = "127.0.0.1:50052",
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

        self.stub = vdag_service_pb2_grpc.vDAGInferenceServiceStub(self.channel)
        self._rpc = self._resolve_rpc(self.stub)

  

    def infer(
        self,
        *,
        session_id: str,
        seq_no: Union[int, str],
        data: Any,
        files: Optional[Iterable[Union[str, bytes, Dict[str, Any]]]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        ts: Optional[float] = None,
        metadata: Optional[List[Tuple[str, str]]] = None,
    ) -> Dict[str, Any]:
        pkt = self._make_packet(
            session_id=session_id,
            seq_no=seq_no,
            data=data,
            frame_ptr=frame_ptr,
            files=files,
            ts=ts if ts is not None else time.time(),
        )
        return self._call(pkt, metadata=metadata)

    def chat_completions(
        self,
        *,
        messages: List[Dict[str, Any]],
        session_id: Optional[str] = None,
        seq_no: Optional[int] = None,
        files: Optional[Iterable[Union[str, bytes, Dict[str, Any]]]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        metadata: Optional[List[Tuple[str, str]]] = None,
    ) -> Dict[str, Any]:
        pkt = self._make_packet(
            session_id=session_id or str(uuid.uuid4()),
            seq_no=seq_no if seq_no is not None else self._now_ms(),
            data=messages,
            frame_ptr=frame_ptr,
            files=files,
            ts=time.time(),
        )
        return self._call(pkt, metadata=metadata)

    def completions(
        self,
        *,
        prompt: Union[str, List[str]],
        session_id: Optional[str] = None,
        seq_no: Optional[int] = None,
        files: Optional[Iterable[Union[str, bytes, Dict[str, Any]]]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        metadata: Optional[List[Tuple[str, str]]] = None,
    ) -> Dict[str, Any]:
        pkt = self._make_packet(
            session_id=session_id or str(uuid.uuid4()),
            seq_no=seq_no if seq_no is not None else self._now_ms(),
            data=prompt,
            frame_ptr=frame_ptr,
            files=files,
            ts=time.time(),
        )
        return self._call(pkt, metadata=metadata)

 
    def _resolve_rpc(self, stub) -> Any:
        for name in self._LIKELY_RPC_NAMES:
            fn = getattr(stub, name, None)
            if callable(fn):
                return fn
        raise vDAGInferenceGRPCError(
            f"Could not find an RPC on vDAGInferenceServiceStub named any of: {', '.join(self._LIKELY_RPC_NAMES)}"
        )

    def _call(self, packet: vdag_service_pb2.vDAGInferencePacket, *, metadata: Optional[List[Tuple[str, str]]] = None) -> Dict[str, Any]:
        call_md = list(self.call_metadata)
        if metadata:
            call_md.extend(metadata)
        try:
            resp: vdag_service_pb2.vDAGInferencePacket = self._rpc(packet, metadata=call_md)  # no timeout
        except grpc.RpcError as e:
            code = e.code()
            raise vDAGInferenceGRPCError(
                f"gRPC call failed: {getattr(code, 'name', 'UNKNOWN')}",
                status_code=getattr(code, "value", None)[0] if hasattr(code, "value") else None,
                details=e.details() if hasattr(e, "details") else None,
            ) from e
        return self._parse_vdag_packet(resp)

    def _make_packet(
        self,
        *,
        session_id: str,
        seq_no: Union[int, str],
        data: Any,
        frame_ptr: Optional[Union[str, bytes]],
        files: Optional[Iterable[Union[str, bytes, Dict[str, Any]]]],
        ts: float,
    ) -> vdag_service_pb2.vDAGInferencePacket:
        data_str = data if isinstance(data, str) else json.dumps(data)

        if frame_ptr is None:
            frame_bytes = None
        elif isinstance(frame_ptr, bytes):
            frame_bytes = frame_ptr
        else:
            frame_bytes = frame_ptr.encode("utf-8")

        file_infos: List[vdag_service_pb2.vDAGFileInfo] = []
        for f in (files or []):
            file_infos.append(self._normalize_fileinfo(f))

        return vdag_service_pb2.vDAGInferencePacket(
            session_id=str(session_id),
            seq_no=int(seq_no),
            ts=float(ts),
            data=data_str,
            frame_ptr=frame_bytes,
            files=file_infos,
        )

    def _normalize_fileinfo(self, item: Union[str, bytes, Dict[str, Any]]) -> vdag_service_pb2.vDAGFileInfo:
        
        if isinstance(item, dict):
            raw = item.get("file_data", None)
            if raw is None:
                raise vDAGInferenceGRPCError("File dict missing 'file_data'.")
            b = self._ensure_bytes(raw)
            meta = item.get("metadata", {})
            meta_str = meta if isinstance(meta, str) else json.dumps(meta or {})
            return vdag_service_pb2.vDAGFileInfo(file_data=b, metadata=meta_str)

        b = self._ensure_bytes(item)  # path or bytes
        return vdag_service_pb2.vDAGFileInfo(file_data=b, metadata="{}")

    @staticmethod
    def _ensure_bytes(x: Union[str, bytes]) -> bytes:
        if isinstance(x, bytes):
            return x
        with open(x, "rb") as fh:
            return fh.read()

    @staticmethod
    def _parse_vdag_packet(pkt: vdag_service_pb2.vDAGInferencePacket) -> Dict[str, Any]:
      
        raw = pkt.data
        if isinstance(raw, (bytes, bytearray)):
            try:
                raw = raw.decode("utf-8")
            except Exception:
                pass

        if isinstance(raw, str):
            try:
                parsed_data: Union[Dict[str, Any], str, bytes] = json.loads(raw)
            except Exception:
                parsed_data = raw
        else:
            parsed_data = raw  # bytes

        out_files: List[Dict[str, Any]] = []
        for f in pkt.files:
            meta = f.metadata
            try:
                meta_parsed = json.loads(meta) if meta else {}
            except Exception:
                meta_parsed = meta  # keep raw string if not JSON
            out_files.append({"file_data": f.file_data, "metadata": meta_parsed})

        return {
            "session_id": pkt.session_id,
            "seq_no": pkt.seq_no,
            "ts": pkt.ts,
            "data": parsed_data,
            "files": out_files,
        }

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
