import traceback
from typing import Optional


class WorkflowExecutor:
   
    def __init__(self, graph):
        self.graph = graph

  

    def execute(self, state):
      

        if state.get_status() == "initialized":
            self._initialize_state(state)

        state.set_status("running")

        while True:
            if self.graph.is_complete(state):
                state.set_status("completed")
                return state

            ready_nodes = self.graph.get_ready_nodes(state)

            if not ready_nodes:
                state.set_status("failed")
                raise RuntimeError(
                    "No executable nodes remaining. "
                    "Workflow is stuck or failed."
                )

            next_node = self._select_next_node(ready_nodes)

            self._execute_node(next_node, state)


    def _execute_node(self, node_id: str, state):
        module = self.graph.nodes[node_id]

        input_data = state.get_node_input(node_id)

        state.mark_node_running(node_id)

        try:
            result = module.execute(state, input_data)

            if result["status"] == "success":
                state.mark_node_completed(node_id, result["output"])
            else:
                state.mark_node_failed(node_id, result["error"])

                if not module.allow_failure:
                    state.set_status("failed")
                    raise RuntimeError(
                        f"Node {node_id} failed and failure not allowed."
                    )

        except Exception as e:
            state.mark_node_failed(
                node_id,
                {
                    "message": str(e),
                    "trace": traceback.format_exc(),
                },
            )
            state.set_status("failed")
            raise

   
    def _initialize_state(self, state):
       
        for node_id in self.graph.nodes:
            if node_id not in state.nodes:
                state.initialize_node(node_id, input_data={})

    def _select_next_node(self, ready_nodes):
       
        topo = self.graph.get_topological_order()

        for node_id in topo:
            if node_id in ready_nodes:
                return node_id

        return ready_nodes[0]