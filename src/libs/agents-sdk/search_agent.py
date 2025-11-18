# sample_agent.py
import logging
from typing import List, Optional


from core.agent_executor import AgentTask, AgentResult
from core.main import main
from core.agent_executor import Context
from core.known_agents import KnownAgents

log = logging.getLogger(__name__)


class SampleAgent:

    def __init__(self, subject, context: Context) -> None:
        self.subject = subject
        self.context = context
        self.known_agents = KnownAgents(default_compact=True, default_custom_repr_fn=None)

        # add agents (example)
        self.known_agents.add_by_id(subject_id="consensus-synthesizer")
        self.known_agents.add_by_id(subject_id="con-argument-generator")

    def get_muxer(self):
        return None

    def on_preprocess(self, task: AgentTask) -> Optional[List[AgentTask]]:

        text = task.job_data.get("text")
        if not text:
            log.warning(
                "Task %s has no 'text' in job_data, skipping.", task.task_id)
            return None

        return [task]

    def on_data(self, task: AgentTask) -> AgentResult:

        try:
            agents = self.known_agents.list_all()

            output = [ agent.get_searchable_representation() for agent in agents ]

            return AgentResult(
                task_id=task.task_id,
                job_output={"output": output},
                job_output_metadata={"length": len(output)},
                is_error=False,
            )

        except Exception as e:
            log.exception("Error processing task %s: %s", task.task_id, e)
            return AgentResult(
                task_id=task.task_id,
                is_error=True,
                error_data={"stage": "on_data", "message": str(e)},
            )


main(SampleAgent)
