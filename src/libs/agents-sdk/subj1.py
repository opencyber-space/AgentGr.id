# sample_agent.py
import logging
from typing import List, Optional
import uuid
import os

from core.agent_executor import AgentTask, AgentResult
from core.main import main
from core.agent_executor import Context

log = logging.getLogger(__name__)

class Muxer:

    def __init__(self, N) -> None:
        self.packets = {}
    
    def add(self, key, task: AgentTask):
        self.packets[key] = self.packets.get(key, [])
        self.packets[key].append(task)

        if len(self.packets[key]) == 2:

            # combine logic here
            return self.packets[key]
        
        return None


class SampleAgent:

    def __init__(self, subject, context: Context) -> None:
        self.subject = subject
        self.context = context
        self.muxer = Muxer(N=2)


    def get_muxer(self):
        return self.muxer


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


            '''result = self.context.p2p_manager.send_and_wait_sync(
                task_id=str(uuid.uuid4()),
                subject_id="p2p-test-002",
                task_data={"text": out},
                timeout=None
            )'''

            '''self.context.direct.submit(
                to="p2p-test-002", session_id=str(uuid.uuid4()),
                task=task, job_data={"text": out}
            )'''

            self.context.p2p_manager.send_sync(
                task=task, subject_id="p2p-test-002",
                job_data={"text": out}, 
                session_id=str(uuid.uuid4())
            )


            return AgentResult(
                task_id=task.task_id,
                job_output={"output": ""},
                job_output_metadata={"length": len(out)},
                is_error=False,
                skip=True
            )

        except Exception as e:
            log.exception("Error processing task %s: %s", task.task_id, e)
            return AgentResult(
                task_id=task.task_id,
                is_error=True,
                error_data={"stage": "on_data", "message": str(e)},
            )


main(SampleAgent)
