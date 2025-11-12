# sample_agent.py
import logging
from typing import List, Optional
import uuid
import os

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
            out = text.upper() + "-HELLO "

            if os.getenv("SUBJECT_ID") == "meeting-2":

                op2 = self.context.delegator.submit_and_wait(
                    subject_id="meeting-3", session_id=str(uuid.uuid4()), task_id=task.task_id, task_data={"text": out}
                )

                self.context.direct.submit(to="subject-11", task=task, job_data={
                    "text": "hello"
                })

                return AgentResult(
                    skip=True
                )

            return AgentResult(
                task_id=task.task_id,
                job_output={"output": out},
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
