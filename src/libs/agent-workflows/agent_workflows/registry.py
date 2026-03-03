import threading
from typing import Dict, List


class ModuleRegistry:
    """
    Stores pre-instantiated workflow modules.
    """

    def __init__(self):
        self._modules: Dict[str, object] = {}
        self._lock = threading.RLock()

    def register(self, name: str, module):
        with self._lock:
            if name in self._modules:
                raise ValueError(f"Module '{name}' already registered")
            self._modules[name] = module

    def get(self, name: str):
        if name not in self._modules:
            raise ValueError(f"Module '{name}' not found in registry")
        return self._modules[name]

    def list_modules(self) -> List[str]:
        return list(self._modules.keys())

    def get_planner_metadata(self):
        metadata = []
        for name, module in self._modules.items():
            metadata.append({
                "name": name,
                "description": module.get_description(),
                "input_schema": module.get_input_structure(),
                "output_schema": module.get_output_structure(),
            })
        return metadata