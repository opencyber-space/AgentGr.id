import logging
import os
import uuid
import requests
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Deque

from .api import (
    LocalType1Evaluator,
    CentralType2Executor,
    FunctionType3Executor,
    JobType4Executor,
)

logger = logging.getLogger(__name__)


class WorkflowSpecError(ValueError):
    pass


class WorkflowCycleError(ValueError):
    pass


class WorkflowNodeError(RuntimeError):
    def __init__(
        self,
        node_id: str,
        reason: str,
        cause: Optional[Exception] = None,
    ) -> None:
        self.node_id = node_id
        self.cause = cause
        super().__init__("Node '{}' failed: {}".format(node_id, reason))


class WorkflowExecutionError(RuntimeError):
    pass


class UnknownNodeTypeError(WorkflowSpecError):
    pass


class UnknownPolicyTypeError(WorkflowSpecError):
    pass


class AgentDSLWorkflowExecutor:

    DELEGATE_API_URL = os.environ.get(
        "DELGATE_API_URL",
        "http://35.223.239.192:30725",
    ).rstrip("/")

    VALID_NODE_TYPES = {"policy", "agent"}
    VALID_POLICY_TYPES = {"local", "central", "function", "job"}

    REQUIRED_SETTINGS: Dict[str, List[str]] = {
        "central": ["executor_id", "endpoint"],
        "function": ["endpoint"],
        "job": ["executor_id", "endpoint"],
        "local": [],
    }

    def __init__(self, spec: Dict[str, Any]) -> None:
        if not isinstance(spec, dict):
            raise WorkflowSpecError(
                "Spec must be a dict, got {}".format(type(spec).__name__)
            )

        self._validate_spec_structure(spec)

        self.spec: Dict[str, Any] = spec
        self.header: Dict[str, Any] = spec["header"]
        self.body: Dict[str, Any] = spec["body"]

        self.nodes: Dict[str, Dict[str, Any]] = {}
        self._load_and_validate_nodes(self.body["nodes"])

        self.graph: Dict[str, List[str]] = self.body.get("graph", {})
        self._validate_graph(self.graph)

    def execute(self, initial_input: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(initial_input, dict):
            raise WorkflowSpecError(
                "initial_input must be a dict, got {}".format(
                    type(initial_input).__name__
                )
            )

        if not self.nodes:
            raise WorkflowSpecError("Workflow has no nodes to execute.")

        try:
            execution_order = self._topological_sort()
        except (WorkflowCycleError, WorkflowSpecError):
            raise
        except Exception as e:
            raise WorkflowExecutionError(
                "Failed to compute execution order: {}".format(e)
            )

        parent_map = self._build_parent_map()
        outputs: Dict[str, Any] = {}

        for node_id in execution_order:
            node = self.nodes[node_id]
            parents = parent_map.get(node_id, [])
            node_input = self._resolve_input(
                node_id, parents, outputs, initial_input
            )

            try:
                result = self._execute_node(node, node_input)
            except (WorkflowNodeError, WorkflowSpecError):
                raise
            except Exception as e:
                raise WorkflowNodeError(node_id, str(e), cause=e)

            if result is None:
                result = {}

            outputs[node_id] = result

        return outputs

    def _resolve_input(
        self,
        node_id: str,
        parents: List[str],
        outputs: Dict[str, Any],
        initial_input: Dict[str, Any],
    ) -> Any:
        if not parents:
            return initial_input

        missing = [p for p in parents if p not in outputs]
        if missing:
            raise WorkflowExecutionError(
                "Node '{}' depends on {} whose outputs are not yet available.".format(
                    node_id, missing
                )
            )

        if len(parents) == 1:
            return outputs[parents[0]]

        return [outputs[p] for p in parents]

    def _execute_node(
        self,
        node: Dict[str, Any],
        input_data: Any,
    ) -> Any:
        node_type = node["type"]

        if node_type == "policy":
            return self._execute_policy_node(node, input_data)

        if node_type == "agent":
            return self._execute_agent_node(node, input_data)

        raise UnknownNodeTypeError(
            "Unknown node type '{}' for nodeID='{}'".format(
                node_type, node["nodeID"]
            )
        )

    def _execute_policy_node(
        self,
        node: Dict[str, Any],
        input_data: Any,
    ) -> Any:
        policy_type = node.get("policyType")
        settings = node.get("settings") or {}
        parameters = node.get("parameters") or {}
        policy_id = node["id"]
        node_id = node["nodeID"]

        if policy_type == "local":
            executor = LocalType1Evaluator(
                policy_rule_uri=policy_id,
                parameters=parameters,
            )
            return executor.execute(input_data)

        if policy_type == "central":
            executor = CentralType2Executor(
                executor_id=settings["executor_id"],
                endpoint=settings["endpoint"],
                policy_rule_uri=policy_id,
                parameters=parameters,
            )
            return executor.execute(input_data)

        if policy_type == "function":
            executor = FunctionType3Executor(
                function_id=policy_id,
                endpoint=settings["endpoint"],
            )
            return executor.execute(input_data)

        if policy_type == "job":
            executor = JobType4Executor(
                executor_id=settings["executor_id"],
                endpoint=settings["endpoint"],
                policy_rule_uri=policy_id,
                parameters=parameters,
                node_selector=settings.get("node_selector", {}),
                poll_interval=settings.get("poll_interval", 2),
                max_retries=settings.get("max_retries", 30),
            )
            job_name = settings.get(
                "job_name",
                "job-{}-{}".format(node_id, uuid.uuid4().hex[:8]),
            )
            return executor.execute(job_name, input_data)

        raise UnknownPolicyTypeError(
            "Unknown policyType '{}' for nodeID='{}'".format(
                policy_type, node_id
            )
        )

    def _execute_agent_node(
        self,
        node: Dict[str, Any],
        input_data: Any,
    ) -> Any:
        node_id = node["nodeID"]
        subject_id = node["id"]
        settings = node.get("settings") or {}
        model_name = settings.get("model_name", "")

        if not isinstance(input_data, dict):
            input_data = {"data": input_data}

        session_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())

        payload = {
            "subject_id": subject_id,
            "session_id": session_id,
            "task_id": task_id,
            "task_data": {
                **input_data,
                "model_name": model_name,
            },
        }

        url = "{}/api/submit-and-wait".format(self.DELEGATE_API_URL)

        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise WorkflowNodeError(node_id, str(e), cause=e)

        try:
            return response.json()
        except ValueError as e:
            raise WorkflowNodeError(
                node_id,
                "Delegate API returned non-JSON response: {}".format(
                    response.text[:200]
                ),
                cause=e,
            )

    def _topological_sort(self) -> List[str]:
        in_degree: Dict[str, int] = {node_id: 0 for node_id in self.nodes}

        for parent, children in self.graph.items():
            for child in children:
                if child not in in_degree:
                    raise WorkflowSpecError(
                        "Graph references nodeID '{}' which is not defined.".format(
                            child
                        )
                    )
                in_degree[child] += 1

        queue: Deque[str] = deque(
            node_id for node_id, degree in in_degree.items() if degree == 0
        )

        order: List[str] = []

        while queue:
            node_id = queue.popleft()
            order.append(node_id)

            for child in self.graph.get(node_id, []):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(order) != len(self.nodes):
            cycle_nodes = [
                n for n in self.nodes if in_degree[n] > 0
            ]
            raise WorkflowCycleError(
                "Cycle detected involving nodes: {}".format(cycle_nodes)
            )

        return order

    def _build_parent_map(self) -> Dict[str, List[str]]:
        parent_map: Dict[str, List[str]] = defaultdict(list)

        for parent, children in self.graph.items():
            for child in children:
                parent_map[child].append(parent)

        return parent_map

    def _validate_spec_structure(
        self,
        spec: Dict[str, Any],
    ) -> None:
        for key in ("header", "body"):
            if key not in spec:
                raise WorkflowSpecError(
                    "Spec missing required top-level key: '{}'".format(key)
                )

    def _load_and_validate_nodes(
        self,
        nodes: List[Dict[str, Any]],
    ) -> None:
        for node in nodes:
            node_id = node["nodeID"]

            if node_id in self.nodes:
                raise WorkflowSpecError(
                    "Duplicate nodeID '{}'".format(node_id)
                )

            node_type = node["type"]

            if node_type not in self.VALID_NODE_TYPES:
                raise UnknownNodeTypeError(
                    "Unknown node type '{}'".format(node_type)
                )

            self.nodes[node_id] = node

    def _validate_graph(
        self,
        graph: Dict[str, List[str]],
    ) -> None:
        for parent, children in graph.items():
            if parent not in self.nodes:
                raise WorkflowSpecError(
                    "Graph references undefined parent '{}'".format(parent)
                )

            for child in children:
                if child not in self.nodes:
                    raise WorkflowSpecError(
                        "Graph references undefined child '{}'".format(child)
                    )
                if child == parent:
                    raise WorkflowCycleError(
                        "Self-loop detected on node '{}'".format(parent)
                    )