import base64
import json
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import requests
from requests import Response
from email import policy
from email.parser import BytesParser


class RESTBlockInferenceError(RuntimeError):
    """Raised when the server responds with a non-2xx status or malformed body."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class RESTBlockInference:
    

    def __init__(self, base_url: str, default_headers: Optional[Dict[str, str]] = None, session: Optional[requests.Session] = None):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.default_headers = default_headers or {"Content-Type": "application/json"}

   
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
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        
        payload_files = []
        for item in files or []:
            file_b64, meta_json = self._normalize_file_item(item)
            payload_files.append({"file_data": file_b64, "metadata": json.loads(meta_json)})

        body = {
            "model": model or "",
            "session_id": session_id,
            "seq_no": seq_no,
            "graph": graph if graph is not None else None,
            "selection_query": selection_query if selection_query is not None else None,
            "data": data,
            "files": payload_files,
        }

        return self._post_json("/v1/infer", body, extra_headers=extra_headers)

    def chat_completions(
        self,
        *,
        messages: List[Dict[str, Any]],
        model: str,
        session_id: Optional[str] = None,
        seq_no: Optional[int] = None,
        selection_query: Optional[Dict[str, Any]] = None,
        graph: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
     
        body = {
            "messages": messages,
            "model": model,
            "session_id": session_id or str(uuid.uuid4()),
            "seq_no": seq_no if seq_no is not None else self._now_ms(),
            "selection_query": selection_query if selection_query is not None else None,
            "graph": graph if graph is not None else None,
        }
        return self._post_json("/v1/chat/completions", body, extra_headers=extra_headers)

    def completions(
        self,
        *,
        prompt: Union[str, List[str]],
        model: str,
        session_id: Optional[str] = None,
        seq_no: Optional[int] = None,
        selection_query: Optional[Dict[str, Any]] = None,
        graph: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        
        body = {
            "prompt": prompt,
            "model": model,
            "session_id": session_id or str(uuid.uuid4()),
            "seq_no": seq_no if seq_no is not None else self._now_ms(),
            "selection_query": selection_query if selection_query is not None else None,
            "graph": graph if graph is not None else None,
        }
        return self._post_json("/v1/completions", body, extra_headers=extra_headers)

    def infer_multipart(
        self,
        *,
        model: str,
        session_id: str,
        seq_no: int,
        data: Union[str, Dict[str, Any]],
        ts: Optional[float] = None,
        output_ptr: Optional[Union[str, Dict[str, Any]]] = None,
        query_parameters: Optional[Union[str, Dict[str, Any]]] = None,
        frame_ptr: Optional[Union[str, bytes]] = None,
        files: Optional[List[Tuple[str, Union[str, bytes], Optional[Dict[str, Any]]]]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        
        url = self.base_url + "/v1/infer-multipart"

        # Prepare form fields
        form: Dict[str, Any] = {
            "model": model,
            "session_id": session_id,
            "seq_no": str(seq_no),
            "ts": str(ts if ts is not None else 0),
            "data": data if isinstance(data, str) else json.dumps(data),
            "output_ptr": output_ptr if isinstance(output_ptr, str) or output_ptr is None else json.dumps(output_ptr),
            "query_parameters": query_parameters if isinstance(query_parameters, str) or query_parameters is None else json.dumps(query_parameters),
            "frame_ptr": frame_ptr if isinstance(frame_ptr, (bytes, str)) else "",
        }

        # Files payload
        req_files = []
        for idx, (field_name, file_data, metadata) in enumerate(files or []):
            bin_data = self._ensure_bytes(file_data)
            req_files.append((field_name, (f"{field_name}.bin", bin_data, "application/octet-stream")))
            if metadata is not None:
                form[f"{field_name}_metadata"] = json.dumps(metadata)

        headers = dict(self.default_headers)
        # requests will set proper multipart boundary when files=form-data, so remove JSON content-type:
        headers.pop("Content-Type", None)
        if extra_headers:
            headers.update(extra_headers)

        try:
            resp = self.session.post(url, data=form, files=req_files, headers=headers)
        except Exception as e:
            raise RESTBlockInferenceError(f"Request failed: {e}") from e

        if not (200 <= resp.status_code < 300):
            raise RESTBlockInferenceError(
                f"Server returned HTTP {resp.status_code} for {url}",
                status_code=resp.status_code,
                response_text=_safe_text(resp),
            )

        ctype = resp.headers.get("Content-Type", "")
        if "multipart/" not in ctype:
            # Server said success but not multipart; try JSON first
            try:
                return resp.json()
            except Exception:
                raise RESTBlockInferenceError(
                    "Expected multipart response but got non-multipart and non-JSON.",
                    status_code=resp.status_code,
                    response_text=_safe_text(resp),
                )

        return self._parse_multipart_mixed(resp)

    def _post_json(self, path: str, body: Dict[str, Any], extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        url = self.base_url + path
        headers = dict(self.default_headers)
        if extra_headers:
            headers.update(extra_headers)

        try:
            resp: Response = self.session.post(url, data=json.dumps(body), headers=headers)
        except Exception as e:
            raise RESTBlockInferenceError(f"Request failed: {e}") from e

        if not (200 <= resp.status_code < 300):
            # Attempt to surface structured error details if present
            err_text = _safe_text(resp)
            try:
                err_json = resp.json()
                msg = err_json.get("error", {}).get("message") or err_json.get("message") or err_text
            except Exception:
                msg = err_text
            raise RESTBlockInferenceError(
                f"Server returned HTTP {resp.status_code} for {url}: {msg}",
                status_code=resp.status_code,
                response_text=err_text,
            )

        try:
            return resp.json()
        except Exception as e:
            raise RESTBlockInferenceError("Response was not valid JSON.", status_code=resp.status_code, response_text=_safe_text(resp)) from e

    def _normalize_file_item(self, item: Union[str, bytes, Dict[str, Any]]) -> Tuple[str, str]:
        
        metadata = {}
        if isinstance(item, dict):
            meta = item.get("metadata", {})
            if isinstance(meta, str):
                try:
                    metadata = json.loads(meta)
                except Exception:
                    metadata = {"raw": meta}
            else:
                metadata = meta or {}

            raw = item.get("file_data")
            if raw is None:
                raise RESTBlockInferenceError("File dict missing 'file_data' key.")
            b = self._ensure_bytes(raw)
            return base64.b64encode(b).decode("ascii"), json.dumps(metadata)
        else:
            # item is path or bytes; empty metadata
            b = self._ensure_bytes(item)
            return base64.b64encode(b).decode("ascii"), json.dumps(metadata)

    @staticmethod
    def _ensure_bytes(data: Union[str, bytes]) -> bytes:
        if isinstance(data, bytes):
            return data
        with open(data, "rb") as f:
            return f.read()

    @staticmethod
    def _now_ms() -> int:
        import time
        return int(time.time() * 1000)

    @staticmethod
    def _parse_multipart_mixed(resp: Response) -> Dict[str, Any]:
       
        raw = resp.content
        content_type = resp.headers.get("Content-Type", "multipart/mixed")
        # Build a complete message for the parser
        header_block = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        msg = BytesParser(policy=policy.default).parsebytes(header_block + raw)

        if not msg.is_multipart():
            raise RESTBlockInferenceError("Expected multipart/mixed response but message is not multipart.")

        parsed_meta = {}
        parsed_data: Union[Dict[str, Any], str] = {}
        files_out: List[bytes] = []

        for part in msg.iter_parts():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()

            payload = part.get_payload(decode=True)  # bytes
            if ctype == "application/json":
                filename = part.get_param("filename", header="content-disposition") or ""
                try:
                    as_json = json.loads(payload.decode("utf-8"))
                except Exception:
                    as_json = {"raw": payload.decode("utf-8", errors="replace")}

                if "metadata" in disp or filename == "metadata.json":
                    parsed_meta = as_json
                else:
                    parsed_data = as_json
            else:
                files_out.append(payload if isinstance(payload, (bytes, bytearray)) else bytes(payload))

        return {"metadata": parsed_meta, "data": parsed_data, "files": files_out}


def _safe_text(resp: Response) -> str:
    try:
        return resp.text
    except Exception:
        try:
            return resp.content.decode("utf-8", errors="replace")
        except Exception:
            return "<unavailable>"
