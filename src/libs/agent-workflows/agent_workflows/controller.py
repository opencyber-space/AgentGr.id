from typing import Dict, Tuple, Callable
from .planner import LLMPlanner
from .tracer import WorkflowTracer
from .state import WorkflowState
from .dag import WorkflowGraph

class WorkflowController:

    def __init__(
        self,
        planner: LLMPlanner,
        executor,
        tracer: WorkflowTracer = None
    ):
        self.planner = planner
        self.executor = executor
        self.tracer = tracer

        self.converters: Dict[Tuple[str, str], Callable] = {}

    def run(self, goal: str):

        state = WorkflowState()
        state.set_global("goal", goal)

        if self.tracer:
            self.tracer.log("workflow_start", {"goal": goal})

        while True:

            graph, initial_inputs = self._build_graph_from_plan(
                goal,
                state
            )

            self.executor.graph = graph
            self.executor.tracer = self.tracer

            for node_id, input_data in initial_inputs.items():
                if node_id not in state.nodes:
                    state.initialize_node(node_id, input_data)

            try:
                self._execute_with_converters(state)

                if state.get_status() == "completed":
                    if self.tracer:
                        self.tracer.log("workflow_completed", {})
                    return state

            except Exception as e:
                if self.tracer:
                    self.tracer.log(
                        "workflow_failed",
                        {"error": str(e)}
                    )

            if self.tracer:
                self.tracer.log("replan_triggered", {})

            goal = self.planner.replan(goal, state)

    def _build_graph_from_plan(self, goal, state):

        plan = self.planner.create_plan(
            goal,
            state.get_all_global()
        )

        graph = WorkflowGraph()
        self.converters.clear()

        initial_inputs = {}

        for node_def in plan["nodes"]:

            node_id = node_def["id"]
            module_name = node_def["module_name"]
            input_data = node_def.get("input", {})

            module_instance = self.planner.registry.get(
                module_name
            )

            graph.add_node(node_id, module_instance)
            initial_inputs[node_id] = input_data

        for edge_def in plan["edges"]:

            parent = edge_def["from"]
            child = edge_def["to"]

            graph.add_edge(parent, child)

            converter_code = edge_def.get("converter_code")

            if converter_code:
                fn = self._compile_converter(converter_code)
                self.converters[(parent, child)] = fn

        return graph, initial_inputs

    # =====================================================
    # EXECUTION
    # =====================================================

    def _execute_with_converters(self, state):

        if state.get_status() == "initialized":
            state.set_status("running")

        while True:

            if self.executor.graph.is_complete(state):
                state.set_status("completed")
                return

            ready_nodes = self.executor.graph.get_ready_nodes(state)

            if not ready_nodes:
                state.set_status("failed")
                raise RuntimeError("Workflow stuck")

            next_node = self.executor._select_next_node(
                ready_nodes
            )

            prepared_input = self._prepare_node_input(
                next_node,
                state
            )

            state.nodes[next_node]["input"] = prepared_input

            self.executor._execute_node(next_node, state)

    # =====================================================
    # INPUT PREPARATION
    # =====================================================

    def _prepare_node_input(self, node_id, state):

        parents = self.executor.graph.get_parents(node_id)

        if not parents:
            return state.get_node_input(node_id)

        aggregated_input = {}

        for parent in parents:

            parent_output = state.get_node_output(parent)
            if parent_output is None:
                continue

            converter = self.converters.get((parent, node_id))

            if converter:
                if self.tracer:
                    self.tracer.log(
                        "converter_executed",
                        {"from": parent, "to": node_id}
                    )

                transformed = converter(parent_output)
            else:
                transformed = parent_output

            if not isinstance(transformed, dict):
                raise RuntimeError(
                    f"Converter must return dict for {parent}->{node_id}"
                )

            aggregated_input.update(transformed)

        return aggregated_input

   

    def _compile_converter(self, code_str: str):

        restricted_globals = {"__builtins__": {}}
        local_env = {}

        exec(code_str, restricted_globals, local_env)

        if "convert" not in local_env:
            raise RuntimeError(
                "Converter must define function 'convert'"
            )

        fn = local_env["convert"]

        if not callable(fn):
            raise RuntimeError("convert must be callable")

        return fn