import threading
import time
import uuid
from typing import Dict, Any, Optional


class WorkflowState:
  

    def __init__(self, workflow_id: Optional[str] = None):
        self.workflow_id = workflow_id or str(uuid.uuid4())
        self.status = "initialized"

        self.global_context: Dict[str, Any] = {}
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.execution_order = []

        self.metadata: Dict[str, Any] = {}

        self._lock = threading.RLock()


    def set_status(self, status: str):
        with self._lock:
            self.status = status

    def get_status(self) -> str:
        return self.status

   
    def set_global(self, key: str, value: Any):
        with self._lock:
            self.global_context[key] = value

    def get_global(self, key: str, default=None):
        return self.global_context.get(key, default)

    def get_all_global(self):
        return dict(self.global_context)

   

    def initialize_node(self, node_id: str, input_data: Dict[str, Any]):
        with self._lock:
            if node_id in self.nodes:
                raise ValueError(f"Node {node_id} already initialized")

            self.nodes[node_id] = {
                "status": "pending",
                "input": input_data,
                "output": None,
                "error": None,
                "attempts": 0,
                "started_at": None,
                "completed_at": None,
            }

    def mark_node_running(self, node_id: str):
        with self._lock:
            self._ensure_node_exists(node_id)

            self.nodes[node_id]["status"] = "running"
            self.nodes[node_id]["started_at"] = time.time()
            self.nodes[node_id]["attempts"] += 1
            self.execution_order.append(node_id)

    def mark_node_completed(self, node_id: str, output_data: Dict[str, Any]):
        with self._lock:
            self._ensure_node_exists(node_id)

            self.nodes[node_id]["status"] = "completed"
            self.nodes[node_id]["output"] = output_data
            self.nodes[node_id]["completed_at"] = time.time()

    def mark_node_failed(self, node_id: str, error: Dict[str, Any]):
        with self._lock:
            self._ensure_node_exists(node_id)

            self.nodes[node_id]["status"] = "failed"
            self.nodes[node_id]["error"] = error
            self.nodes[node_id]["completed_at"] = time.time()

    def get_node_input(self, node_id: str) -> Dict[str, Any]:
        self._ensure_node_exists(node_id)
        return self.nodes[node_id]["input"]

    def get_node_output(self, node_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_node_exists(node_id)
        return self.nodes[node_id]["output"]

    def get_node_status(self, node_id: str) -> str:
        self._ensure_node_exists(node_id)
        return self.nodes[node_id]["status"]

    def get_node_error(self, node_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_node_exists(node_id)
        return self.nodes[node_id]["error"]

  
    def get_completed_nodes(self):
        return [
            node_id
            for node_id, data in self.nodes.items()
            if data["status"] == "completed"
        ]

    def get_failed_nodes(self):
        return [
            node_id
            for node_id, data in self.nodes.items()
            if data["status"] == "failed"
        ]

    def get_pending_nodes(self):
        return [
            node_id
            for node_id, data in self.nodes.items()
            if data["status"] == "pending"
        ]


    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "workflow_id": self.workflow_id,
                "status": self.status,
                "global_context": self.global_context,
                "nodes": self.nodes,
                "execution_order": self.execution_order,
                "metadata": self.metadata,
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        obj = cls(workflow_id=data["workflow_id"])
        obj.status = data["status"]
        obj.global_context = data["global_context"]
        obj.nodes = data["nodes"]
        obj.execution_order = data["execution_order"]
        obj.metadata = data["metadata"]
        return obj

   
    def _ensure_node_exists(self, node_id: str):
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} does not exist")