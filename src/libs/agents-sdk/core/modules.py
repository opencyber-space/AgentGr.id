from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Iterable
from .db.schema import Subject

import logging
from threading import RLock


class AgentModule(ABC):
  

    def __init__(
        self,
        name: str,
        settings: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.settings = settings or {}
        self.parameters = parameters or {}

    @abstractmethod
    def execute_management_command(
        self,
        command_name: str,
        command_data: Dict[str, Any],
    ) -> Any:
     
        pass

    @abstractmethod
    def execute(self, data: Dict[str, Any]) -> Any:
        
        pass

    @abstractmethod
    def get_searchable_representation(self) -> Dict[str, Any]:
       
        pass

    @abstractmethod
    def set_parameters(self, parameters: Dict[str, Any]) -> None:
        
        pass



class ModuleAlreadyRegistered(Exception):
    """Raised when attempting to register a module with a name that already exists."""


class ModuleNotFound(Exception):
    """Raised when the requested module name does not exist."""


class ModulesManager:
   
    def __init__(self, *, subject: Subject, logger: Optional[logging.Logger] = None) -> None:
        self._modules: Dict[str, AgentModule] = {}
        self.subject = subject
        self._lock = RLock()
        self._log = logger or logging.getLogger(self.__class__.__name__)
        if not self._log.handlers:
            logging.basicConfig(level=logging.INFO)

    def register(self, name, module_class) -> None:

        if name in self._modules:
            raise Exception("module already registered")

        subject_modules = self.subject.integrations.builtin_modules
        for module in subject_modules:
            if module.module_id == name:
                self._modules[name] = module_class(name, module.module_settings, module.module_parameters)
        else:
            logging.info(f"module [{name}] not found, initializing defaults")
            self._modules[name] = module_class(name, {}, {})

    def unregister(self, name: str) -> bool:
       
        with self._lock:
            removed = self._modules.pop(name, None) is not None
            if removed:
                self._log.info("Unregistered module: %s", name)
            else:
                self._log.debug("Unregister requested for non-existent module: %s", name)
            return removed

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._modules

    def list_names(self) -> List[str]:
        with self._lock:
            return list(self._modules.keys())

    def get(self, name: str) -> AgentModule:
        with self._lock:
            mod = self._modules.get(name)
            if not mod:
                raise ModuleNotFound(f"Module '{name}' not found.")
            return mod

    def get_many(self, names: Optional[Iterable[str]] = None) -> List[AgentModule]:
       
        with self._lock:
            if names is None:
                return list(self._modules.values())
            mods: List[AgentModule] = []
            for n in names:
                mod = self._modules.get(n)
                if not mod:
                    raise ModuleNotFound(f"Module '{n}' not found.")
                mods.append(mod)
            return mods

    def execute(self, name: str, data: Dict[str, Any]) -> Any:
        mod = self.get(name)
        self._log.debug("Executing module '%s' with data keys=%s", name, list((data or {}).keys()))
        return mod.execute(data)

    def execute_management_command(
        self, name: str, command_name: str, command_data: Dict[str, Any]
    ) -> Any:
        mod = self.get(name)
        self._log.debug(
            "Executing management command '%s' on module '%s' with data keys=%s",
            command_name,
            name,
            list((command_data or {}).keys()),
        )
        return mod.execute_management_command(command_name, command_data)

    def set_parameters(self, name: str, parameters: Dict[str, Any]) -> None:
        mod = self.get(name)
        self._log.debug("Setting parameters on module '%s' with keys=%s", name, list(parameters.keys()))
        mod.set_parameters(parameters)

    def get_searchable_representation(self, name: str) -> Dict[str, Any]:
        mod = self.get(name)
        rep = mod.get_searchable_representation()
        self._log.debug("Searchable representation for '%s' -> keys=%s", name, list((rep or {}).keys()))
        return rep

    def get_all_modules(self):
        mods = [m for _, m in self._modules.items()]
        return mods

    # ---------- Broadcast helpers (optional but handy) ----------
    def execute_all(self, data: Dict[str, Any]) -> Dict[str, Any]:
        
        results: Dict[str, Any] = {}
        for mod in self.get_many():
            try:
                self._log.debug("execute_all -> %s", mod.name)
                results[mod.name] = mod.execute(data)
            except Exception as e:
                self._log.exception("execute_all error on '%s': %s", mod.name, e)
                results[mod.name] = {"error": str(e)}
        return results

    def set_parameters_all(self, parameters: Dict[str, Any]) -> None:
        
        for mod in self.get_many():
            try:
                self._log.debug("set_parameters_all -> %s", mod.name)
                mod.set_parameters(parameters)
            except Exception as e:
                self._log.exception("set_parameters_all error on '%s': %s", mod.name, e)

    def get_all_searchable_representations(self) -> Dict[str, Dict[str, Any]]:
       
        out: Dict[str, Dict[str, Any]] = {}
        for mod in self.get_many():
            try:
                rep = mod.get_searchable_representation()
                out[mod.name] = rep
            except Exception as e:
                self._log.exception("get_all_searchable_representations error on '%s': %s", mod.name, e)
                out[mod.name] = {"error": str(e)}
        return out
