import json
from .tracer import WorkflowTracer
from .cache import PlanCache
from .registry import ModuleRegistry

class LLMPlanner:

    def __init__(
        self,
        llm_client,
        registry: ModuleRegistry,
        enable_validation: bool = False,
        plan_cache: PlanCache = None,
        tracer: WorkflowTracer = None,
        llm_output_parser = None
    ):
        self.llm = llm_client
        self.registry = registry
        self.enable_validation = enable_validation
        self.cache = plan_cache
        self.tracer = tracer
        self.llm_output_parser = llm_output_parser

    def create_plan(self, goal: str, context: dict):

        if self.cache:
            cached = self.cache.get(goal, context)
            if cached:
                if self.tracer:
                    self.tracer.log("plan_cache_hit", {"goal": goal})
                return cached
            else:
                if self.tracer:
                    self.tracer.log("plan_cache_miss", {"goal": goal})

        raw = self._call_llm(goal, context, replanning=False)
        plan = self._parse_plan(raw)
        self._validate_plan(plan)

        if self.enable_validation:
            self._validate_with_llm(plan, goal, context)

        if self.cache:
            self.cache.set(goal, context, plan)

        return plan

    def replan(self, goal: str, state):

        context = {
            "completed_nodes": state.get_completed_nodes(),
            "failed_nodes": state.get_failed_nodes(),
            "global_context": state.get_all_global()
        }

        return self.create_plan(goal, context)

    # =====================================================
    # INTERNAL
    # =====================================================

    def _call_llm(self, goal, context, replanning=False):

        modules_metadata = self.registry.get_planner_metadata()

        system_prompt = """
You are a workflow planning agent.

Return STRICT JSON only.
No markdown.
No explanation.

Format:
{
  "nodes": [
    {
      "id": "string",
      "module_name": "registered_module_name",
      "input": {}
    }
  ],
  "edges": [
    {
      "from": "node_id",
      "to": "node_id",
      "converter_code": "optional python code"
    }
  ]
}

Rules:
- Only use provided module names.
- If parent output does not match child input, generate converter_code.
- converter_code must define:

    def convert(parent_output):
        ...
        return dict

- No imports allowed.
"""

        user_payload = {
            "goal": goal,
            "context": context,
            "available_modules": modules_metadata,
            "replanning": replanning
        }

        waiter = self.llm.async_chat_completions(
            session_id="planner-session",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload)}
            ],
            data={"mode": "chat"}
        )

        return waiter.wait()

    def _parse_plan(self, raw_response: str):

        try:
            if self.llm_output_parser:
                raw_response = self.llm_output_parser(raw_response)
            plan = json.loads(raw_response)
        except Exception:
            raise RuntimeError(
                f"Planner did not return valid JSON:\n{raw_response}"
            )

        return plan

    def _validate_plan(self, plan):

        if "nodes" not in plan or "edges" not in plan:
            raise RuntimeError("Plan must contain 'nodes' and 'edges'")

        node_ids = set()

        for node in plan["nodes"]:

            if "id" not in node or "module_name" not in node:
                raise RuntimeError(
                    "Each node must have 'id' and 'module_name'"
                )

            if node["module_name"] not in self.registry.list_modules():
                raise RuntimeError(
                    f"Unknown module: {node['module_name']}"
                )

            node_ids.add(node["id"])

        for edge in plan["edges"]:

            if edge["from"] not in node_ids:
                raise RuntimeError(f"Invalid edge from: {edge['from']}")

            if edge["to"] not in node_ids:
                raise RuntimeError(f"Invalid edge to: {edge['to']}")

            if "converter_code" in edge:
                if "def convert" not in edge["converter_code"]:
                    raise RuntimeError(
                        "converter_code must define convert()"
                    )

    def _validate_with_llm(self, plan, goal, context):

        modules_metadata = self.registry.get_planner_metadata()

        prompt = f"""
    You are validating a workflow DAG plan.

    IMPORTANT:
    - You are NOT evaluating runtime data.
    - You are ONLY validating structural compatibility.
    - Assume modules return valid outputs matching their output_schema.
    - Do NOT speculate about empty data.

    Goal:
    {goal}

    Available Modules:
    {json.dumps(modules_metadata)}

    Plan:
    {json.dumps(plan)}

    Validate:
    1. All module names exist.
    2. Edges form a valid DAG.
    3. For every edge:
    - Either output_schema matches input_schema
    - Or converter_code exists.
    4. converter_code defines:
    def convert(parent_output): return dict

    Return STRICT JSON:
    {{ "valid": true }} 
    OR
    {{ "valid": false, "reason": "..." }}
    """

        waiter = self.llm.async_chat_completions(
            session_id="plan-validator",
            messages=[{"role": "user", "content": prompt}],
            data={"mode": "chat"}
        )

        response = waiter.wait()

        if self.llm_output_parser:
            response = self.llm_output_parser(response)

        result = json.loads(response)

        if not result.get("valid"):
            raise RuntimeError(
                f"Plan rejected: {result.get('reason')}"
            )