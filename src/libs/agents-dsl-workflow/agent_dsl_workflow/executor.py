import logging
import os
import uuid
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

import requests

from .api import (
    CentralType2Executor,
    FunctionType3Executor,
    JobType4Executor,
    LocalType1Evaluator,
)

logger = logging.getLogger(__name__)


class WorkflowSpecError(ValueError):
    """Raised when the workflow spec is malformed or missing required fields."""
    pass


class WorkflowCycleError(ValueError):
    """Raised when a cycle is detected in the workflow graph."""
    pass


class WorkflowNodeError(RuntimeError):
    """Raised when a node fails during execution."""

    def __init__(self, node_id: str, reason: str, cause: Exception = None):
        self.node_id = node_id
        self.cause = cause
        super().__init__(f"Node '{node_id}' failed: {reason}")


class WorkflowRouterError(RuntimeError):
    """Raised when the router returns an invalid or unexpected response."""
    pass


class WorkflowExecutionError(RuntimeError):
    """Raised when the overall workflow execution fails."""
    pass


class UnknownNodeTypeError(WorkflowSpecError):
    """Raised when a node has an unrecognised type."""
    pass


class UnknownPolicyTypeError(WorkflowSpecError):
    """Raised when a policy node has an unrecognised policyType."""
    pass


class WorkflowDBError(Exception):
    """Raised when WorkflowDB encounters an API or response error."""
    pass


class WorkflowDB:

    def __init__(self, timeout: int = 10) -> None:
        base_url = os.getenv("SUBJECT_DB_URL")
        if not base_url:
            raise WorkflowDBError(
                "Environment variable 'SUBJECT_DB_URL' is not set or empty."
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _handle_response(self, resp: requests.Response) -> Any:
        try:
            data = resp.json()
        except Exception:
            raise WorkflowDBError(
                f"Invalid JSON response (status={resp.status_code}): {resp.text[:200]}"
            )
        if not resp.ok or not data.get("success", False):
            raise WorkflowDBError(
                data.get("message") or data.get("error") or resp.text
            )
        return data.get("data")

    # -----------------------------------------------------------------------
    # CRUD
    # -----------------------------------------------------------------------

    def get_workflow(self, workflow_uri: str) -> Dict[str, Any]:
        if not workflow_uri:
            raise WorkflowDBError("workflow_uri must be a non-empty string.")
        url = f"{self.base_url}/api/workflows/{workflow_uri}"
        try:
            resp = requests.get(url, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise WorkflowDBError(f"GET {url} failed: {e}") from e
        return self._handle_response(resp)

    def replace_workflow(
        self, workflow_uri: str, workflow_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not workflow_uri:
            raise WorkflowDBError("workflow_uri must be a non-empty string.")
        if not isinstance(workflow_data, dict):
            raise WorkflowDBError("workflow_data must be a dict.")
        url = f"{self.base_url}/api/workflows/{workflow_uri}"
        try:
            resp = requests.put(url, json=workflow_data, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise WorkflowDBError(f"PUT {url} failed: {e}") from e
        return self._handle_response(resp)

    def update_workflow(
        self, workflow_uri: str, update_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not workflow_uri:
            raise WorkflowDBError("workflow_uri must be a non-empty string.")
        if not isinstance(update_fields, dict):
            raise WorkflowDBError("update_fields must be a dict.")
        url = f"{self.base_url}/api/workflows/{workflow_uri}"
        try:
            resp = requests.patch(
                url, json={"update": update_fields}, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise WorkflowDBError(f"PATCH {url} failed: {e}") from e
        return self._handle_response(resp)

    def delete_workflow(self, workflow_uri: str) -> bool:
        if not workflow_uri:
            raise WorkflowDBError("workflow_uri must be a non-empty string.")
        url = f"{self.base_url}/api/workflows/{workflow_uri}"
        try:
            resp = requests.delete(url, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise WorkflowDBError(f"DELETE {url} failed: {e}") from e
        self._handle_response(resp)
        return True

    def list_workflows(
        self,
        *,
        limit: int = 50,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/workflows"
        try:
            resp = requests.get(
                url, params={"limit": limit, "skip": skip}, timeout=self.timeout
            )
        except requests.exceptions.RequestException as e:
            raise WorkflowDBError(f"GET {url} failed: {e}") from e
        return self._handle_response(resp)

    def query_workflows(
        self,
        query: Dict[str, Any],
        *,
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[List] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/workflows/query"
        payload = {
            "query": query,
            "projection": projection,
            "sort": sort,
            "limit": limit,
            "skip": skip,
        }
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise WorkflowDBError(f"POST {url} failed: {e}") from e
        return self._handle_response(resp)


# ---------------------------------------------------------------------------
# AgentDSLWorkflowExecutor
# ---------------------------------------------------------------------------

class AgentDSLWorkflowExecutor:

    DELEGATE_API_URL = os.environ.get(
        "DELGATE_API_URL", "http://35.223.239.192:30725"
    ).rstrip("/")

    VALID_NODE_TYPES = {"policy", "agent", "workflow"}
    VALID_POLICY_TYPES = {"local", "central", "function", "job"}
    VALID_GRAPH_TYPES = {"static", "dynamic"}

    REQUIRED_SETTINGS: Dict[str, List[str]] = {
        "central":  ["executor_id", "endpoint"],
        "function": ["endpoint"],
        "job":      ["executor_id", "endpoint"],
        "local":    [],
    }

    def __init__(self, spec: dict, db: Optional[WorkflowDB] = None) -> None:

        if not isinstance(spec, dict):
            raise WorkflowSpecError(
                f"Spec must be a dict, got {type(spec).__name__}")

        self._validate_spec_structure(spec)

        self.spec = spec
        self.header = spec["header"]
        self.body = spec["body"]
        self._db = db  # lazily initialised if None and a workflow node is hit

        self.nodes: Dict[str, dict] = {}
        self._load_and_validate_nodes(self.body["nodes"])
        self._parse_graph(self.body.get("graph", {}))

        workflow_id = self.header.get("workflow_id", {})
        logger.info(
            f"AgentDSLWorkflowExecutor initialized | "
            f"workflow={workflow_id.get('name')} "
            f"version={workflow_id.get('version')} "
            f"release={workflow_id.get('release')} | "
            f"nodes={len(self.nodes)} | "
            f"mode={'dynamic' if self.is_dynamic else 'static'}"
            + (f" | router={self.router_node_id}" if self.is_dynamic else "")
        )

    @classmethod
    def from_workflow_id(cls, workflow_id: str) -> "AgentDSLWorkflowExecutor":

        if not workflow_id or not isinstance(workflow_id, str):
            raise WorkflowSpecError(
                f"workflow_id must be a non-empty string, got: {workflow_id!r}"
            )

        db = WorkflowDB()

        logger.info(f"Fetching workflow spec for workflow_id='{workflow_id}'")

        try:
            spec = db.get_workflow(workflow_id)
        except WorkflowDBError as e:
            raise WorkflowDBError(
                f"Failed to fetch workflow '{workflow_id}' from DB: {e}"
            ) from e

        if not spec:
            raise WorkflowDBError(
                f"WorkflowDB returned empty spec for workflow_id='{workflow_id}'"
            )

        if not isinstance(spec, dict):
            raise WorkflowDBError(
                f"WorkflowDB returned non-dict spec for workflow_id='{workflow_id}': "
                f"{type(spec).__name__}"
            )

        logger.info(
            f"Successfully fetched spec for workflow_id='{workflow_id}', initialising executor")
        return cls(spec=spec, db=db)

    @property
    def db(self) -> WorkflowDB:
        """Lazily initialise WorkflowDB on first access."""
        if self._db is None:
            logger.debug(
                "Lazily initialising WorkflowDB from SUBJECT_DB_URL env var")
            self._db = WorkflowDB()
        return self._db

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def execute(self, initial_input: dict) -> Dict[str, Any]:

        if not isinstance(initial_input, dict):
            raise WorkflowSpecError(
                f"initial_input must be a dict, got {type(initial_input).__name__}"
            )
        if not self.nodes:
            raise WorkflowSpecError("Workflow has no nodes to execute.")

        if self.is_dynamic:
            return self._execute_dynamic(initial_input)
        return self._execute_static(initial_input)

    def _execute_static(self, initial_input: dict) -> Dict[str, Any]:
        logger.info("Starting static workflow execution")

        try:
            execution_order = self._topological_sort()
        except (WorkflowCycleError, WorkflowSpecError):
            raise
        except Exception as e:
            raise WorkflowExecutionError(
                f"Failed to compute execution order: {e}") from e

        parent_map = self._build_parent_map()
        outputs: Dict[str, Any] = {}

        for node_id in execution_order:
            node = self.nodes[node_id]
            parents = parent_map.get(node_id, [])
            node_input = self._resolve_static_input(
                node_id, parents, outputs, initial_input)
            outputs[node_id] = self._run_node(node, node_input)

        logger.info(
            f"Static workflow execution completed | nodes_executed={len(outputs)}")
        return outputs

    def _resolve_static_input(
        self,
        node_id: str,
        parents: List[str],
        outputs: Dict[str, Any],
        initial_input: dict,
    ) -> Any:
        if not parents:
            return initial_input

        missing = [p for p in parents if p not in outputs]
        if missing:
            raise WorkflowExecutionError(
                f"Node '{node_id}' depends on {missing} whose outputs are not yet available. "
                "This indicates a bug in topological ordering."
            )

        if len(parents) == 1:
            return outputs[parents[0]]

        return [outputs[p] for p in parents]

    def _execute_dynamic(self, initial_input: dict) -> Dict[str, Any]:
        logger.info(
            f"Starting dynamic workflow execution | router='{self.router_node_id}'"
        )

        history: List[str] = []
        outputs: Dict[str, Any] = {}
        last_executed_batch: List[dict] = []

        next_steps = self._call_router(
            self._build_router_payload(history, outputs, last_executed_batch, initial_input)
        )

        if not next_steps:
            logger.warning(
                "Router returned empty on first call — workflow completed immediately"
            )
            return outputs

        while next_steps:
            self._validate_router_response(next_steps)
            last_executed_batch = []

            for step in next_steps:
                node_id = step["nodeID"]
                node_input = step.get("input", {})

                if not isinstance(node_input, dict):
                    logger.warning(
                        f"Router provided non-dict input for node '{node_id}' "
                        f"({type(node_input).__name__}). Wrapping in {{\"data\": ...}}."
                    )
                    node_input = {"data": node_input}

                result = self._run_node(self.nodes[node_id], node_input)

                outputs[node_id] = result
                history.append(node_id)
                last_executed_batch.append({"nodeID": node_id, "output": result})

            logger.info(
                f"Dynamic: batch of {len(last_executed_batch)} node(s) completed, querying router"
            )

            next_steps = self._call_router(
                self._build_router_payload(history, outputs, last_executed_batch, initial_input)
            )

        logger.info(
            f"Dynamic workflow execution completed | nodes_executed={len(outputs)}"
        )
        return outputs

    def _build_router_payload(self, history, outputs, last_executed_batch, initial_input):
        return {
            "initial_input":        initial_input,
            "history":              history,
            "outputs":              outputs,
            "last_executed":        last_executed_batch[-1] if last_executed_batch else None,
            "last_executed_batch":  last_executed_batch,
        }

    def _call_router(self, payload: dict) -> List[dict]:
        router_node = self.nodes[self.router_node_id]
        logger.debug(f"Calling router '{self.router_node_id}'")

        try:
            raw_response = self._execute_node(router_node, payload)
        except (WorkflowNodeError, WorkflowSpecError):
            raise
        except Exception as e:
            raise WorkflowRouterError(
                f"Router node '{self.router_node_id}' raised an unexpected error: {e}"
            ) from e

        if raw_response is None:
            logger.info("Router returned None — treating as workflow complete")
            return []

        if isinstance(raw_response, dict):
            for key in ("next_steps", "steps", "nodes", "data", "result"):
                if key in raw_response and isinstance(raw_response[key], list):
                    logger.debug(f"Router response unwrapped from key '{key}'")
                    raw_response = raw_response[key]
                    break
            else:
                if not raw_response:
                    return []
                raise WorkflowRouterError(
                    f"Router node '{self.router_node_id}' returned a dict with no recognised "
                    f"list key. Got keys: {list(raw_response.keys())}"
                )

        if not isinstance(raw_response, list):
            raise WorkflowRouterError(
                f"Router node '{self.router_node_id}' must return a list or dict, "
                f"got {type(raw_response).__name__}: {str(raw_response)[:200]}"
            )

        return raw_response

    def _validate_router_response(self, steps: list) -> None:
        if not isinstance(steps, list):
            raise WorkflowRouterError(
                f"Router response must be a list, got {type(steps).__name__}"
            )
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                raise WorkflowRouterError(
                    f"Router response step[{i}] must be a dict, got {type(step).__name__}"
                )
            if "nodeID" not in step:
                raise WorkflowRouterError(
                    f"Router response step[{i}] missing required key 'nodeID'. Got: {step}"
                )
            node_id = step["nodeID"]
            if not isinstance(node_id, str) or not node_id:
                raise WorkflowRouterError(
                    f"Router response step[{i}].nodeID must be a non-empty string, "
                    f"got: {node_id!r}"
                )
            if node_id not in self.nodes:
                raise WorkflowRouterError(
                    f"Router response step[{i}] references unknown nodeID '{node_id}'. "
                    f"Available nodes: {list(self.nodes.keys())}"
                )
            if node_id == self.router_node_id:
                raise WorkflowRouterError(
                    f"Router response step[{i}] references the router itself ('{node_id}'). "
                    "The router cannot route to itself."
                )

    # -----------------------------------------------------------------------
    # Node runner (shared by both modes)
    # -----------------------------------------------------------------------

    def _run_node(self, node: dict, node_input: Any) -> Any:
        node_id = node["nodeID"]
        logger.info(f"Executing node '{node_id}' | type={node['type']}")

        try:
            result = self._execute_node(node, node_input)
        except (WorkflowNodeError, WorkflowSpecError, WorkflowDBError):
            raise
        except Exception as e:
            raise WorkflowNodeError(node_id, str(e), cause=e) from e

        if result is None:
            logger.warning(
                f"Node '{node_id}' returned None — passing empty dict downstream")
            result = {}

        logger.info(f"Node '{node_id}' completed successfully")
        return result

    # -----------------------------------------------------------------------
    # Node dispatch
    # -----------------------------------------------------------------------

    def _execute_node(self, node: dict, input_data: Any) -> Any:
        node_type = node["type"]

        if node_type == "policy":
            return self._execute_policy_node(node, input_data)
        elif node_type == "agent":
            return self._execute_agent_node(node, input_data)
        elif node_type == "workflow":
            return self._execute_workflow_node(node, input_data)
        else:
            raise UnknownNodeTypeError(
                f"Unknown node type '{node_type}' for nodeID='{node['nodeID']}'"
            )

    # -----------------------------------------------------------------------
    # Policy executor
    # -----------------------------------------------------------------------

    def _execute_policy_node(self, node: dict, input_data: Any) -> Any:
        policy_type = node.get("policyType")
        settings = node.get("settings") or {}
        parameters = node.get("parameters") or {}
        policy_id = node["id"]
        node_id = node["nodeID"]

        logger.debug(f"Policy node '{node_id}' | policyType={policy_type}")

        if policy_type == "local":
            return LocalType1Evaluator(
                policy_rule_uri=policy_id,
                parameters=parameters,
            ).execute(input_data)

        elif policy_type == "central":
            return CentralType2Executor(
                executor_id=settings["executor_id"],
                endpoint=settings["endpoint"],
                policy_rule_uri=policy_id,
                parameters=parameters,
            ).execute(input_data)

        elif policy_type == "function":
            return FunctionType3Executor(
                function_id=policy_id,
                endpoint=settings["endpoint"],
            ).execute(input_data)

        elif policy_type == "job":
            job_name = settings.get(
                "job_name", f"job-{node_id}-{uuid.uuid4().hex[:8]}")
            return JobType4Executor(
                executor_id=settings["executor_id"],
                endpoint=settings["endpoint"],
                policy_rule_uri=policy_id,
                parameters=parameters,
                node_selector=settings.get("node_selector", {}),
                poll_interval=settings.get("poll_interval", 2),
                max_retries=settings.get("max_retries", 30),
            ).execute(job_name, input_data)

        else:
            raise UnknownPolicyTypeError(
                f"Unknown policyType '{policy_type}' for nodeID='{node_id}'"
            )

    # -----------------------------------------------------------------------
    # Agent executor
    # -----------------------------------------------------------------------

    def _execute_agent_node(self, node: dict, input_data: Any) -> Any:
        node_id = node["nodeID"]
        subject_id = node["id"]
        settings = node.get("settings") or {}
        model_name = settings.get("model_name", "")

        if not model_name:
            logger.warning(f"Agent node '{node_id}' has no model_name in settings")

        if not isinstance(input_data, dict):
            logger.warning(
                f"Agent node '{node_id}' received non-dict input "
                f"({type(input_data).__name__}). Wrapping in {{\"data\": ...}}."
            )
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

        url = f"{self.DELEGATE_API_URL}/api/submit-and-wait"
        logger.info(
            f"Agent node '{node_id}' | POST {url} | "
            f"session_id={session_id} task_id={task_id}"
        )
        logger.debug(f"Agent payload: {payload}")

        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise WorkflowNodeError(
                node_id, f"Could not connect to delegate API at {url}: {e}", cause=e
            ) from e
        except requests.exceptions.Timeout:
            raise WorkflowNodeError(
                node_id, f"Delegate API timed out after 60s (url={url})"
            )
        except requests.exceptions.HTTPError as e:
            raise WorkflowNodeError(
                node_id,
                f"Delegate API returned HTTP {response.status_code}: {e}",
                cause=e,
            ) from e
        except requests.exceptions.RequestException as e:
            raise WorkflowNodeError(
                node_id, f"Unexpected request error calling delegate API: {e}", cause=e
            ) from e

        try:
            response_json = response.json()
        except ValueError as e:
            raise WorkflowNodeError(
                node_id,
                f"Delegate API returned non-JSON response: {response.text[:200]}",
                cause=e,
            ) from e

        logger.debug(f"Agent node '{node_id}' response: {response_json}")

        try:
            return response_json["output"]["job_output"]
        except KeyError as e:
            raise WorkflowNodeError(
                node_id,
                f"Missing 'output.job_output' in delegate response: {response_json}",
                cause=e,
            ) from e

    # -----------------------------------------------------------------------
    # Workflow (sub-workflow) executor
    # -----------------------------------------------------------------------

    def _execute_workflow_node(self, node: dict, input_data: Any) -> Any:

        node_id = node["nodeID"]
        workflow_id = node["id"]

        logger.info(
            f"Workflow node '{node_id}' | fetching sub-workflow '{workflow_id}' from DB"
        )

        if not isinstance(input_data, dict):
            logger.warning(
                f"Workflow node '{node_id}' received non-dict input "
                f"({type(input_data).__name__}). Wrapping in {{\"data\": ...}}."
            )
            input_data = {"data": input_data}

        # Fetch spec from DB
        try:
            sub_spec = self.db.get_workflow(workflow_id)
        except WorkflowDBError as e:
            raise WorkflowNodeError(
                node_id,
                f"Failed to fetch sub-workflow '{workflow_id}' from DB: {e}",
                cause=e,
            ) from e

        if not sub_spec:
            raise WorkflowNodeError(
                node_id,
                f"WorkflowDB returned empty spec for workflow_id='{workflow_id}'",
            )

        if not isinstance(sub_spec, dict):
            raise WorkflowNodeError(
                node_id,
                f"WorkflowDB returned non-dict spec for workflow_id='{workflow_id}': "
                f"{type(sub_spec).__name__}",
            )

        logger.info(
            f"Workflow node '{node_id}' | initialising sub-executor for '{workflow_id}'"
        )

        # Initialise a fresh executor for the sub-workflow, passing down the same DB instance
        try:
            sub_executor = AgentDSLWorkflowExecutor(spec=sub_spec, db=self._db)
        except WorkflowSpecError as e:
            raise WorkflowNodeError(
                node_id,
                f"Sub-workflow '{workflow_id}' has an invalid spec: {e}",
                cause=e,
            ) from e

        # Execute the sub-workflow
        try:
            sub_outputs = sub_executor.execute(input_data)
        except (WorkflowNodeError, WorkflowExecutionError, WorkflowRouterError) as e:
            raise WorkflowNodeError(
                node_id,
                f"Sub-workflow '{workflow_id}' failed during execution: {e}",
                cause=e,
            ) from e

        logger.info(
            f"Workflow node '{node_id}' | sub-workflow '{workflow_id}' completed | "
            f"sub_nodes_executed={len(sub_outputs)}"
        )

        return sub_outputs

    def _parse_graph(self, graph: Any) -> None:
        if not graph:
            self.is_dynamic = False
            self.router_node_id = None
            self.graph = {}
            logger.warning(
                "No graph defined — nodes will execute without edges")
            return

        if not isinstance(graph, dict):
            raise WorkflowSpecError(
                f"'body.graph' must be a dict, got {type(graph).__name__}"
            )

        graph_type = graph.get("type", "static")

        if graph_type not in self.VALID_GRAPH_TYPES:
            raise WorkflowSpecError(
                f"'body.graph.type' must be one of {self.VALID_GRAPH_TYPES}, "
                f"got '{graph_type}'"
            )

        if graph_type == "dynamic":
            self._parse_dynamic_graph(graph)
        else:
            self._parse_static_graph(graph)

    def _parse_dynamic_graph(self, graph: dict) -> None:
        router_node_id = graph.get("nodeID")

        if not router_node_id:
            raise WorkflowSpecError(
                "'body.graph' with type='dynamic' must include 'nodeID' "
                "pointing to the router node."
            )
        if not isinstance(router_node_id, str):
            raise WorkflowSpecError(
                f"'body.graph.nodeID' must be a string, got {type(router_node_id).__name__}"
            )
        if router_node_id not in self.nodes:
            raise WorkflowSpecError(
                f"Router nodeID '{router_node_id}' referenced in graph is not defined in nodes."
            )

        extra_keys = set(graph.keys()) - {"type", "nodeID"}
        if extra_keys:
            logger.warning(
                f"Dynamic graph has unrecognised keys (ignored): {extra_keys}")

        self.is_dynamic = True
        self.router_node_id = router_node_id
        self.graph = {}
        logger.info(
            f"Dynamic graph mode enabled | router_node='{router_node_id}'")

    def _parse_static_graph(self, graph: dict) -> None:
        adjacency = {k: v for k, v in graph.items() if k != "type"}
        self._validate_static_graph(adjacency)
        self.is_dynamic = False
        self.router_node_id = None
        self.graph = adjacency

    def _validate_static_graph(self, graph: dict) -> None:
        for parent, children in graph.items():
            if parent not in self.nodes:
                raise WorkflowSpecError(
                    f"Graph references parent nodeID '{parent}' not defined in nodes."
                )
            if not isinstance(children, list):
                raise WorkflowSpecError(
                    f"Graph entry for '{parent}' must be a list of child nodeIDs, "
                    f"got {type(children).__name__}"
                )
            for child in children:
                if not isinstance(child, str):
                    raise WorkflowSpecError(
                        f"Graph child entries for '{parent}' must be strings, "
                        f"got {type(child).__name__}"
                    )
                if child not in self.nodes:
                    raise WorkflowSpecError(
                        f"Graph references child nodeID '{child}' not defined in nodes."
                    )
                if child == parent:
                    raise WorkflowCycleError(
                        f"Self-loop detected on node '{parent}'")

    # -----------------------------------------------------------------------
    # Static graph utilities
    # -----------------------------------------------------------------------

    def _topological_sort(self) -> List[str]:
        in_degree: Dict[str, int] = {node_id: 0 for node_id in self.nodes}

        for parent, children in self.graph.items():
            for child in children:
                if child not in in_degree:
                    raise WorkflowSpecError(
                        f"Graph references nodeID '{child}' not defined in nodes."
                    )
                in_degree[child] += 1

        queue = deque(n for n, d in in_degree.items() if d == 0)
        order: List[str] = []

        while queue:
            node_id = queue.popleft()
            order.append(node_id)
            for child in self.graph.get(node_id, []):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(order) != len(self.nodes):
            cycle_nodes = [n for n in self.nodes if in_degree[n] > 0]
            raise WorkflowCycleError(
                f"Cycle detected in workflow graph involving nodes: {cycle_nodes}"
            )

        return order

    def _build_parent_map(self) -> Dict[str, List[str]]:
        parent_map: Dict[str, List[str]] = defaultdict(list)
        for parent, children in self.graph.items():
            for child in children:
                parent_map[child].append(parent)
        return parent_map

    # -----------------------------------------------------------------------
    # Spec & node validation
    # -----------------------------------------------------------------------

    def _validate_spec_structure(self, spec: dict) -> None:
        for top_key in ("header", "body"):
            if top_key not in spec:
                raise WorkflowSpecError(
                    f"Spec missing required top-level key: '{top_key}'"
                )

        header = spec["header"]
        if not isinstance(header, dict):
            raise WorkflowSpecError("'header' must be a dict")
        if "workflow_id" not in header:
            raise WorkflowSpecError(
                "'header' missing required key: 'workflow_id'")

        workflow_id = header["workflow_id"]
        if not isinstance(workflow_id, dict):
            raise WorkflowSpecError("'header.workflow_id' must be a dict")
        for wf_key in ("name", "version", "release"):
            if wf_key not in workflow_id:
                raise WorkflowSpecError(
                    f"'header.workflow_id' missing required key: '{wf_key}'"
                )

        body = spec["body"]
        if not isinstance(body, dict):
            raise WorkflowSpecError("'body' must be a dict")
        if "nodes" not in body:
            raise WorkflowSpecError("'body' missing required key: 'nodes'")
        if not isinstance(body["nodes"], list):
            raise WorkflowSpecError("'body.nodes' must be a list")

    def _load_and_validate_nodes(self, nodes: list) -> None:
        if not nodes:
            logger.warning("Workflow spec contains zero nodes")

        for i, node in enumerate(nodes):
            if not isinstance(node, dict):
                raise WorkflowSpecError(
                    f"Node at index {i} must be a dict, got {type(node).__name__}"
                )
            for required in ("nodeID", "type", "id"):
                if not node.get(required):
                    raise WorkflowSpecError(
                        f"Node at index {i} missing required field: '{required}'"
                    )

            node_id = node["nodeID"]
            node_type = node["type"]

            if node_id in self.nodes:
                raise WorkflowSpecError(
                    f"Duplicate nodeID detected: '{node_id}'")

            if node_type not in self.VALID_NODE_TYPES:
                raise UnknownNodeTypeError(
                    f"Node '{node_id}' has unknown type '{node_type}'. "
                    f"Valid types: {self.VALID_NODE_TYPES}"
                )

            if node_type == "policy":
                self._validate_policy_node(node)
            elif node_type == "agent":
                self._validate_agent_node(node)
            elif node_type == "workflow":
                self._validate_workflow_node(node)

            self.nodes[node_id] = node

    def _validate_policy_node(self, node: dict) -> None:
        node_id = node["nodeID"]
        policy_type = node.get("policyType")

        if not policy_type:
            raise WorkflowSpecError(
                f"Policy node '{node_id}' missing required field: 'policyType'"
            )
        if policy_type not in self.VALID_POLICY_TYPES:
            raise UnknownPolicyTypeError(
                f"Policy node '{node_id}' has unknown policyType '{policy_type}'. "
                f"Valid types: {self.VALID_POLICY_TYPES}"
            )

        settings = node.get("settings") or {}
        missing_keys = [k for k in self.REQUIRED_SETTINGS.get(
            policy_type, []) if not settings.get(k)]
        if missing_keys:
            raise WorkflowSpecError(
                f"Policy node '{node_id}' (policyType='{policy_type}') "
                f"missing required settings keys: {missing_keys}"
            )

        if "endpoint" in settings:
            endpoint = settings["endpoint"]
            if not isinstance(endpoint, str) or not endpoint.startswith("http"):
                raise WorkflowSpecError(
                    f"Policy node '{node_id}' settings.endpoint must be a valid HTTP URL, "
                    f"got: '{endpoint}'"
                )

        for num_field in ("poll_interval", "max_retries"):
            if num_field in settings:
                val = settings[num_field]
                if not isinstance(val, int) or val <= 0:
                    raise WorkflowSpecError(
                        f"Policy node '{node_id}' settings.{num_field} must be a positive int, "
                        f"got: {val!r}"
                    )

    def _validate_agent_node(self, node: dict) -> None:
        node_id = node["nodeID"]
        settings = node.get("settings") or {}
        if not settings.get("model_name"):
            logger.warning(
                f"Agent node '{node_id}' has no 'model_name' in settings. "
                "This may cause issues at runtime."
            )

    def _validate_workflow_node(self, node: dict) -> None:
        """Validates workflow node — id (workflow_id) must be a non-empty string."""
        node_id = node["nodeID"]
        workflow_id = node.get("id")

        if not workflow_id or not isinstance(workflow_id, str):
            raise WorkflowSpecError(
                f"Workflow node '{node_id}' must have a non-empty string 'id' "
                "representing the sub-workflow's workflow_id."
            )
