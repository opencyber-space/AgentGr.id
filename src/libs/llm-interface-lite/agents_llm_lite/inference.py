from __future__ import annotations

import logging
from typing import Dict, Optional, Any, List, Iterable, Sequence, Callable
import re
import sys
import subprocess

from .aios import AIOSInferenceAPI    
from .custom import BaseInference    


class AgentInferenceManager:
    

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self._registry: Dict[str, BaseInference] = {}

    # ---------- Registration ----------

    def register_new_inference(
        self,
        *,
        name: str,
        model: str,
        inference_server_id: str,
        aios_url_map: Dict[str, str],
        system_message: str = "",
        session_id: Optional[str] = None,
        overwrite: bool = False,
        logger: Optional[logging.Logger] = None,
    ) -> BaseInference:
        if not overwrite and name in self._registry:
            raise ValueError(f"Inference provider '{name}' already exists")

        provider = AIOSInferenceAPI(
            model=model,
            inference_server_id=inference_server_id,
            aios_url_map=aios_url_map,
            system_message=system_message,
            session_id=session_id,
            logger=logger or self._logger.getChild(f"inf:{name}"),
        )
        self._registry[name] = provider
        self._logger.debug("Registered AIOSInferenceAPI as '%s'", name)
        return provider

    def register_custom_inference(
        self,
        *,
        name: str,
        provider: BaseInference,
        overwrite: bool = False,
    ) -> None:
        if not isinstance(provider, BaseInference):
            raise TypeError("provider must be an instance of BaseInference")
        if not overwrite and name in self._registry:
            raise ValueError(f"Inference provider '{name}' already exists")

        self._registry[name] = provider
        self._logger.debug(
            "Registered custom inference as '%s' (%s)", name, provider.__class__.__name__
        )

    # ---------- Accessors ----------

    def get_inference(self, name: str) -> BaseInference:
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(f"Inference provider '{name}' not found")

    def has_inference(self, name: str) -> bool:
        return name in self._registry

    def list_inferences(self) -> List[str]:
        return list(self._registry.keys())

    # ---------- Removal ----------

    def unregister_inference(self, name: str) -> None:
        try:
            del self._registry[name]
            self._logger.debug("Unregistered inference '%s'", name)
        except KeyError:
            raise KeyError(f"Inference provider '{name}' not found")

    def clear_inferences(self) -> None:
        self._registry.clear()
        self._logger.debug("Cleared all registered inferences")

    # ---------- Inference ----------

    def infer(
        self,
        *,
        name: str,
        prompt: str,
        callback: Callable[[Any], str],
        temperature: float = 0.1,
        top_p: float = 0.95,
        max_tokens: int = 4096,
        system_message: Optional[str] = None,
        **provider_kwargs: Any,
    ) -> str:
        provider = self.get_inference(name)
        self._logger.debug(
            "Running inference using '%s' with prompt length=%d", name, len(prompt)
        )
        return provider.infer(
            prompt=prompt,
            callback=callback,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            system_message=system_message,
            **provider_kwargs,
        )

    def infer_and_execute(
        self,
        *,
        name: str,
        prompt: str,
        callback: Callable[[Any], str],
        # callable resolution prefs
        function_name: str = "main",
        class_name: Optional[str] = None,
        method_name: Optional[str] = None,
        # model params
        temperature: float = 0.1,
        top_p: float = 0.95,
        max_tokens: int = 4096,
        system_message: Optional[str] = None,
        # execution params
        scope_objects: Optional[Dict[str, Any]] = None,
        args: Optional[Sequence[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        install_deps: bool = True,
        # passthrough to provider (e.g., seq_no, extra_headers):
        **provider_kwargs: Any,
    ) -> Any:
        code = self.infer(
            name=name,
            prompt=prompt,
            callback=callback,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            system_message=system_message,
            **provider_kwargs,
        )
        py_code = self._strip_md_fences(code)

        # Optional: infer and install deps
        deps = self._extract_dependencies(py_code)
        if install_deps and deps:
            self._logger.debug("Installing dependencies: %s", deps)
            self._pip_install(deps)

        # Compile
        compiled = compile(py_code, "<generated>", "exec")

        # Exec in a real module registered in sys.modules
        import types
        import uuid as _uuid
        module_name = f"__generated_{_uuid.uuid4().hex}__"
        module = types.ModuleType(module_name)
        module.__package__ = None
        module.__file__ = "<generated>"

        # Inject caller-provided globals
        if scope_objects:
            for k, v in scope_objects.items():
                if k not in ("__name__", "__file__", "__package__"):
                    setattr(module, k, v)

        sys.modules[module_name] = module
        exec(compiled, module.__dict__)

        # Resolve a callable and invoke
        ns = module.__dict__
        target = self._resolve_callable(
            ns=ns,
            function_name=function_name,
            class_name=class_name,
            method_name=method_name,
        )
        return target(*(args or ()), **(kwargs or {}))

    # ----------------------
    # Internal helpers
    # ----------------------

    @staticmethod
    def _strip_md_fences(text: str) -> str:
        if not isinstance(text, str):
            return ""
        s = text.strip()
        if not s.startswith("```"):
            return text
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)
