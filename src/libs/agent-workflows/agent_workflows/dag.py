import threading
from typing import Dict, Set, List
from collections import defaultdict, deque

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .abstract import AgentWorkflowModule
    from .state import WorkflowState


class WorkflowGraph:
   

    def __init__(self):
        self.nodes: Dict[str, "AgentWorkflowModule"] = {}
        self.adjacency: Dict[str, Set[str]] = defaultdict(set)
        self.reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)

        self._lock = threading.RLock()


    def add_node(self, node_id: str, module: "AgentWorkflowModule"):
        with self._lock:
            if node_id in self.nodes:
                raise ValueError(f"Node {node_id} already exists")

            self.nodes[node_id] = module
            self.adjacency[node_id] = set()
            self.reverse_adjacency[node_id] = set()

    def remove_node(self, node_id: str):
        with self._lock:
            self._ensure_node_exists(node_id)

            # Remove edges
            for parent in self.reverse_adjacency[node_id]:
                self.adjacency[parent].remove(node_id)

            for child in self.adjacency[node_id]:
                self.reverse_adjacency[child].remove(node_id)

            del self.nodes[node_id]
            del self.adjacency[node_id]
            del self.reverse_adjacency[node_id]

    def add_edge(self, from_node: str, to_node: str):
        with self._lock:
            self._ensure_node_exists(from_node)
            self._ensure_node_exists(to_node)

            self.adjacency[from_node].add(to_node)
            self.reverse_adjacency[to_node].add(from_node)

            if self._has_cycle():
                # rollback
                self.adjacency[from_node].remove(to_node)
                self.reverse_adjacency[to_node].remove(from_node)
                raise ValueError("Adding this edge introduces a cycle")

    def remove_edge(self, from_node: str, to_node: str):
        with self._lock:
            self.adjacency[from_node].discard(to_node)
            self.reverse_adjacency[to_node].discard(from_node)

  

    def get_children(self, node_id: str) -> Set[str]:
        self._ensure_node_exists(node_id)
        return set(self.adjacency[node_id])

    def get_parents(self, node_id: str) -> Set[str]:
        self._ensure_node_exists(node_id)
        return set(self.reverse_adjacency[node_id])

    def get_root_nodes(self) -> List[str]:
        """
        Nodes with no parents.
        """
        return [
            node_id
            for node_id in self.nodes
            if len(self.reverse_adjacency[node_id]) == 0
        ]

    def get_leaf_nodes(self) -> List[str]:
     
        return [
            node_id
            for node_id in self.nodes
            if len(self.adjacency[node_id]) == 0
        ]

    def get_topological_order(self) -> List[str]:
      
        in_degree = {
            node_id: len(self.reverse_adjacency[node_id])
            for node_id in self.nodes
        }

        queue = deque(
            [node for node, deg in in_degree.items() if deg == 0]
        )

        order = []

        while queue:
            node = queue.popleft()
            order.append(node)

            for child in self.adjacency[node]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(order) != len(self.nodes):
            raise RuntimeError("Graph contains a cycle")

        return order

    def get_ready_nodes(self, state: "WorkflowState") -> List[str]:
      
        ready = []

        for node_id in self.nodes:
            if state.get_node_status(node_id) != "pending":
                continue

            parents = self.get_parents(node_id)

            if all(
                state.get_node_status(parent) == "completed"
                for parent in parents
            ):
                ready.append(node_id)

        return ready

    def is_complete(self, state: "WorkflowState") -> bool:
        return all(
            state.get_node_status(node_id) == "completed"
            for node_id in self.nodes
        )

  

    def _has_cycle(self) -> bool:
       
        try:
            self.get_topological_order()
            return False
        except RuntimeError:
            return True

    def _ensure_node_exists(self, node_id: str):
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} does not exist")