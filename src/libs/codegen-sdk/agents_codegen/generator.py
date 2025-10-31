from __future__ import annotations

import logging
from typing import Dict, Optional, Any, List, Iterable, Sequence
import re
import sys
import subprocess

from .aios import AIOSCodeGeneratorAPI
from .custom import BaseCodeGenerator


class AgentCodeGenerator:

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self._registry: Dict[str, BaseCodeGenerator] = {}

    def register_new_code_generator(
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
    ) -> BaseCodeGenerator:
        if not overwrite and name in self._registry:
            raise ValueError(f"Generator '{name}' already exists")

        gen = AIOSCodeGeneratorAPI(
            model=model,
            inference_server_id=inference_server_id,
            aios_url_map=aios_url_map,
            system_message=system_message,
            session_id=session_id,
            logger=logger or self._logger.getChild(f"gen:{name}"),
        )
        self._registry[name] = gen
        self._logger.debug("Registered AIOSCodeGeneratorAPI as '%s'", name)
        return gen

    def register_custom_generator(
        self,
        *,
        name: str,
        generator: BaseCodeGenerator,
        overwrite: bool = False,
    ) -> None:
        if not isinstance(generator, BaseCodeGenerator):
            raise TypeError(
                "generator must be an instance of BaseCodeGenerator")

        if not overwrite and name in self._registry:
            raise ValueError(f"Generator '{name}' already exists")

        self._registry[name] = generator
        self._logger.debug(
            "Registered custom generator as '%s' (%s)", name, generator.__class__.__name__
        )

    # ---------- Accessors ----------

    def get_generator(self, name: str) -> BaseCodeGenerator:
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(f"Generator '{name}' not found")

    def has_generator(self, name: str) -> bool:
        return name in self._registry

    def list_generators(self) -> List[str]:
        return list(self._registry.keys())

    # ---------- Removal ----------

    def unregister_generator(self, name: str) -> None:
        try:
            del self._registry[name]
            self._logger.debug("Unregistered generator '%s'", name)
        except KeyError:
            raise KeyError(f"Generator '{name}' not found")

    def clear_generators(self) -> None:
        self._registry.clear()
        self._logger.debug("Cleared all registered generators")

    def generate_code(
        self,
        *,
        name: str,
        prompt: str,
        temperature: float = 0.1,
        top_p: float = 0.95,
        max_tokens: int = 4096,
        system_message: Optional[str] = None,
        **provider_kwargs: Any,
    ) -> str:
        gen = self.get_generator(name)
        self._logger.debug(
            "Generating code using '%s' with prompt length=%d", name, len(
                prompt)
        )
        return gen.generate_code(
            prompt=prompt,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            system_message=system_message,
            **provider_kwargs,
        )

    def generate_and_execute(
        self,
        *,
        name: str,
        prompt: str,
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
        code = self.generate_code(
            name=name,
            prompt=prompt,
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

        # --- NEW: exec in a real module registered in sys.modules ---
        import types
        import uuid
        import sys
        module_name = f"__generated_{uuid.uuid4().hex}__"
        module = types.ModuleType(module_name)
        module.__package__ = None
        module.__file__ = "<generated>"

        # Inject caller-provided globals
        if scope_objects:
            for k, v in scope_objects.items():
                if k not in ("__name__", "__file__", "__package__"):
                    setattr(module, k, v)

        sys.modules[module_name] = module  # register first
        exec(compiled, module.__dict__)    # then exec in that module

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

    @staticmethod
    def _extract_dependencies(code: str) -> List[str]:
        deps: List[str] = []

        # REQUIREMENTS = ["pkg", "pkg==1.2"]
        m = re.search(
            r"^\s*REQUIREMENTS\s*=\s*\[(.*?)\]\s*$", code, re.MULTILINE | re.DOTALL)
        if m:
            inner = m.group(1)
            deps.extend(re.findall(r"""['"]([^'"]+)['"]""", inner))

        # "# requirements: a, b==1.2" and "# deps: a b==1.2"
        for rx in (r"^\s*#\s*requirements\s*:\s*(.+)$", r"^\s*#\s*deps\s*:\s*(.+)$"):
            for m in re.finditer(rx, code, re.IGNORECASE | re.MULTILINE):
                deps.extend([t for t in re.split(
                    r"[,\s]+", m.group(1).strip()) if t])

        # ```requirements.txt ... ```
        fenced = re.search(r"```requirements\.txt\s+(.+?)```",
                           code, re.IGNORECASE | re.DOTALL)
        if fenced:
            for line in fenced.group(1).splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    deps.append(line)

        # de-dupe
        seen, deduped = set(), []
        for d in (d.strip() for d in deps if d.strip()):
            if d not in seen:
                seen.add(d)
                deduped.append(d)
        return deduped

    @staticmethod
    def _pip_install(packages: Iterable[str]) -> None:
        pkgs = list(packages)
        if not pkgs:
            return

        logging.info(f"[Dependency] installing dependency: {packages}")
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade"] + pkgs
        proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"pip install failed:\n{proc.stdout}")

    @staticmethod
    def _resolve_callable(
        *,
        ns: Dict[str, Any],
        function_name: str,
        class_name: Optional[str],
        method_name: Optional[str],
    ):

        # 1) direct function
        fn = ns.get(function_name)
        if callable(fn):
            return fn

        # 2) class + method
        if class_name and method_name:
            cls = ns.get(class_name)
            if isinstance(cls, type):
                inst = cls()
                meth = getattr(inst, method_name, None)
                if callable(meth):
                    return meth
                raise RuntimeError(
                    f"Method '{method_name}' not found/callable on class '{class_name}'")
            raise RuntimeError(f"Class '{class_name}' not found")

        callables = []
        for name, obj in ns.items():
            if isinstance(obj, type) and hasattr(obj, "__call__") and obj.__call__ is not object.__call__:
                callables.append(obj)
        if len(callables) == 1:
            return callables[0]()

        raise RuntimeError(
            "No callable found. Provide a top-level function 'main', "
            "or (class_name, method_name), or a single class with __call__."
        )
