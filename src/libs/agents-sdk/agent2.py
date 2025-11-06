# sample_agent.py
import logging
from typing import List, Optional

from core.agent_executor import AgentTask, AgentResult
from core.main import main
from core.agent_executor import Context

log = logging.getLogger(__name__)


class SampleAgent:

    def __init__(self, subject, context: Context) -> None:
        self.subject = subject
        self.context = context

    def on_preprocess(self, task: AgentTask) -> Optional[List[AgentTask]]:

        text = task.job_data.get("text")
        if not text:
            log.warning(
                "Task %s has no 'text' in job_data, skipping.", task.task_id)
            return None

        return [task]

    def on_data(self, task: AgentTask) -> AgentResult:

        try:
            text = task.job_data["text"]
            out = text.upper()

            if self.context.subject_id == "uppercase-002":

                op_x = self.context.delegator.submit_and_wait(
                    subject_id="subject-2", session_id="session-123",
                    task_id=task.task_id, task_data={
                        "text": "What's up?"
                    }
                )

                return AgentResult(
                    task_id=task.task_id,
                    job_output=op_x,
                    job_output_metadata={"length": len(out)},
                    is_error=False,
                )

            else:

                return AgentResult(
                    task_id=task.task_id,
                    job_output={"text": out},
                    job_output_metadata={"length": len(out)},
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
