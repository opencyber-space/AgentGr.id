# sample_agent.py
import logging
import uuid
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

                # agent P2P
                op_x = {}

                op_x = self.context.p2p_manager.send_and_wait_sync(
                    task.task_id, subject_id="uppercase-003",
                    task_data={"text": out + "World!"}
                )

                # agent direct (doesn't return the result to the caller)
                self.context.direct.submit(to="uppercase-003", session_id=str(uuid.uuid4()), task=task, job_data={
                    "text": "out " + "World!"
                })


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
