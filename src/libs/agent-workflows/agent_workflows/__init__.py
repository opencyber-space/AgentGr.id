from .registry import ModuleRegistry
from .tracer import WorkflowTracer
from .cache import PlanCache
from .planner import LLMPlanner
from .executor import WorkflowExecutor
from .controller import WorkflowController

class AgentWorkflowEngine:
    

    def __init__(
        self,
        llm_client,
        modules: dict,
        enable_validation: bool = False,
        enable_tracing: bool = False,
        cache_ttl: int = None,
        llm_output_parser = None
    ):
        
        self.registry = ModuleRegistry()

        for name, module in modules.items():
            self.registry.register(name, module)

     
        self.tracer = WorkflowTracer() if enable_tracing else None

        self.plan_cache = PlanCache(ttl_seconds=cache_ttl) if cache_ttl else None

       
        self.planner = LLMPlanner(
            llm_client=llm_client,
            registry=self.registry,
            enable_validation=enable_validation,
            plan_cache=self.plan_cache,
            tracer=self.tracer,
            llm_output_parser=llm_output_parser
        )

      
        self.executor = WorkflowExecutor(graph=None)
        self.executor.tracer = self.tracer

       
        self.controller = WorkflowController(
            planner=self.planner,
            executor=self.executor,
            tracer=self.tracer
        )


    def run(self, goal: str):
       
        return self.controller.run(goal)

    def get_registry(self):
        return self.registry

    def get_planner(self):
        return self.planner

    def get_controller(self):
        return self.controller