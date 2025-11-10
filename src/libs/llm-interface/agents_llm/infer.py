from typing import Any, Dict, Optional, List, Union


from .block_infer import BlockInferenceSystem
from .vdag_infer import vDAGInferenceSystem
from .custom import AbstractBlockInferenceSystem
from .selection import SelectionEngine

class AIGridClient:
    def __init__(self) -> None:
        self._systems: Dict[str, Any] = {}

    def add_block(
        self,
        *,
        network_host: str,
        inference_server_id: str,
        model: str,
        mode: str = "auto",
        block_data: Optional[Dict[str, Any]] = None,
        default_headers: Optional[Dict[str, str]] = None,
        name: Optional[str] = None,
        urls={}
    ) -> None:
        key = name or "default"
        system = BlockInferenceSystem(
            network_host=network_host,
            inference_server_id=inference_server_id,
            model=model,
            block_data=block_data,
            mode=mode,
            default_headers=default_headers,
            urls=urls,
        )
        self._systems[key] = system
    

    def add_custom_block(self, name: Optional[str], system: AbstractBlockInferenceSystem) -> None:
        key = name or "default"
        self._systems[key] = system

    def add_vdag(
        self,
        *,
        registry_base_url: str,
        vdag_uri: str,
        mode: str = "auto",
        block_data: Optional[Dict[str, Any]] = None,
        default_headers: Optional[Dict[str, str]] = None,
        name: Optional[str] = None,
    ) -> None:
        key = name or "default"
        system = vDAGInferenceSystem(
            registry_base_url=registry_base_url,
            vdag_uri=vdag_uri,
            mode=mode,
            block_data=block_data,
            default_headers=default_headers,
        )
        self._systems[key] = system

    def remove(self, name: str) -> None:
        if name not in self._systems:
            raise KeyError(f"No system registered with name '{name}'")
        del self._systems[name]

    def list(self) -> List[str]:
        return list(self._systems.keys())

    def get(self, name: Optional[str] = None) -> Any:
        key = name or "default"
        if key not in self._systems:
            raise KeyError(f"No system registered with name '{key}'")
        return self._systems[key]

    # ---------------------------------------
    # Internal: full-parameter passthroughs
    # ---------------------------------------
    def internal_infer(self, *, name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        return self.get(name).infer(**kwargs)

    def internal_chat_completions(self, *, name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        return self.get(name).chat_completions(**kwargs)

    def internal_completions(self, *, name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        return self.get(name).completions(**kwargs)

    def internal_infer_multipart(self, *, name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        return self.get(name).infer_multipart(**kwargs)

    def internal_async_infer(self, *, name: Optional[str] = None, **kwargs):
        return self.get(name).async_infer(**kwargs)

    def internal_async_chat_completions(self, *, name: Optional[str] = None, **kwargs):
        return self.get(name).async_chat_completions(**kwargs)

    def internal_async_completions(self, *, name: Optional[str] = None, **kwargs):
        return self.get(name).async_completions(**kwargs)

    def internal_async_infer_multipart(self, *, name: Optional[str] = None, **kwargs):
        return self.get(name).async_infer_multipart(**kwargs)

    
    def create_selector(self, name: str, base_query):
        return SelectionEngine(client=self, name=name, base_query=base_query)

   
    def infer(self, *, session_id: str, data: Dict[str, Any], name: Optional[str] = None) -> Dict[str, Any]:
        return self.get(name).infer(
            session_id=session_id,
            seq_no=0,
            data=data,
            files=None,
            selection_query=None,
            graph=None,
            frame_ptr=None,
            output_ptr=None,
        )

    def chat_completions(self, *, session_id: str, messages: list, data: Dict[str, Any], name: Optional[str] = None) -> Dict[str, Any]:
        return self.get(name).chat_completions(
            messages=messages,
            session_id=session_id,
            seq_no=0,
            selection_query=None,
            graph=None,
            frame_ptr=None,
            output_ptr=None,
            data=data
        )

    def completions(self, *, session_id: str, prompts: list, name: Optional[str] = None, data=None) -> Dict[str, Any]:
        return self.get(name).completions(
            prompt=prompts,
            session_id=session_id,
            seq_no=0,
            selection_query=None,
            graph=None,
            frame_ptr=None,
            output_ptr=None,
            data=data
        )

    def infer_multipart(self, *, session_id: str, data: Dict[str, Any], name: Optional[str] = None) -> Dict[str, Any]:
        return self.get(name).infer_multipart(
            session_id=session_id,
            seq_no=0,
            data=data,
            ts=None,
            frame_ptr=None,
            files=None,
        )

    # ---------- Async simplified ----------
    def async_infer(self, *, session_id: str, data: Dict[str, Any], name: Optional[str] = None):
        return self.get(name).async_infer(
            session_id=session_id,
            seq_no=0,
            data=data,
            files=None,
            selection_query=None,
            graph=None,
            frame_ptr=None,
            output_ptr=None,
        )

    def async_chat_completions(self, *, session_id: str, messages, data: dict, name: Optional[str] = None):
        return self.get(name).async_chat_completions(
            messages=messages,
            session_id=session_id,
            seq_no=0,
            selection_query=None,
            graph=None,
            frame_ptr=None,
            output_ptr=None,
            data=data
        )

    def async_completions(self, *, session_id: str, prompts: list, name: Optional[str] = None, data=None):
        return self.get(name).async_completions(
            prompt=prompts,
            session_id=session_id,
            seq_no=0,
            selection_query=None,
            graph=None,
            frame_ptr=None,
            output_ptr=None,
            data=data
        )

    def async_infer_multipart(self, *, session_id: str, data: Dict[str, Any], name: Optional[str] = None):
        return self.get(name).async_infer_multipart(
            session_id=session_id,
            seq_no=0,
            data=data,
            ts=None,
            frame_ptr=None,
            files=None,
        )

    

    
