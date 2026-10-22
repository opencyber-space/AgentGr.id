import logging
import os


from typing import Any, Dict, List, Optional
from .types import AgentTask, AgentResult
from .delegate import AgentDelegator
from .direct import AgentDirect

from .p2p import PeersManager


log = logging.getLogger(__name__)


class AgentExecutorError(Exception):
    pass


class BadTaskError(AgentExecutorError):
    pass


def task_from_dict(d: Dict[str, Any]) -> AgentTask:
    if not isinstance(d, dict):
        raise BadTaskError("Task payload must be a dict")
    task_id = str(d.get("task_id") or d.get("id") or "").strip()
    if not task_id:
        raise BadTaskError("task_id is required")
    return AgentTask(
        task_id=task_id,
        job_data=d.get("job_data") or {},
        output_ptr=d.get("output_ptr") or {},
        task_metadata=d.get("task_metadata") or {},
    )


def result_to_dict(r: AgentResult) -> Dict[str, Any]:
    return {
        "task_id": r.task_id,
        "job_output": r.job_output,
        "job_output_metadata": r.job_output_metadata,
        "job_output_trace_data": r.job_output_trace_data,
        "is_error": r.is_error,
        "error_data": r.error_data,
    }


class Context:
    def __init__(self, p2p_manager: PeersManager) -> None:
        self.p2p_manager: PeersManager = p2p_manager
        self.subject_id: str = os.getenv("SUBJECT_ID")

        delegation_url = os.getenv("AGENT_DELEGATE_URL")
        logging.info(f"[Delegator] Using delegation system {delegation_url}")
        self.delegator: AgentDelegator = AgentDelegator(base_url=delegation_url)
        agent_runtime_db_url = os.getenv("SUBJECT_DB_URL")
        logging.info(f"[AgentDirect] Using delegation system {delegation_url}")
        self.direct: AgentDirect = AgentDirect(runtime_db_url=agent_runtime_db_url)


class AgentExecutor:
    def __init__(
        self,
        *,
        agent_class,
        message_transformer=None,
        pre_processor=None,
        post_processor=None,
        subject=None,
        meshes: Optional[List[Dict[str, str]]] = None, 
        use_env_mesh_list: bool = True,                  
    ):
        self.message_transformer = message_transformer
        self.pre_processor = pre_processor
        self.post_processor = post_processor
        self.subject = subject

        # P2P + agent wiring
        self.p2p_manager = PeersManager(agent_data=self.subject)
        self.context = Context(p2p_manager=self.p2p_manager)
        self.agent = agent_class(subject, self.context)

        # Initialize P2P manager (starts NATS listeners in a thread)
        self._init_p2p(meshes=meshes, use_env_mesh_list=use_env_mesh_list)

    def _init_p2p(
        self,
        *,
        meshes: Optional[List[Dict[str, str]]] = None,
        use_env_mesh_list: bool = True,
    ) -> None:
       
        self.p2p_manager.register_event_handler(self.on_p2p_event)

        self.p2p_manager.start_background_loop()

        if meshes is not None:
            self.p2p_manager.initialize_meshes_sync(meshes)
        elif use_env_mesh_list:
            self.p2p_manager.initialize_meshes_sync()

        log.info("[AgentExecutor] P2P initialized; NATS listeners active.")

    def shutdown(self) -> None:
        try:
            self.p2p_manager.close_sync()
        finally:
            self.p2p_manager.stop_background_loop()
        log.info("[AgentExecutor] P2P shut down cleanly.")

    def on_p2p_event(self, mesh_id: str, event_name: str, event_data: Dict[str, Any]) -> None:
      
        try:
            if hasattr(self.agent, "on_event") and callable(getattr(self.agent, "on_event")):
                self.agent.on_event(event_name, event_data)
            else:
                log.info("[AgentExecutor] Event from %s: %s -> %s", mesh_id, event_name, event_data)
        except Exception as e:
            log.exception("[AgentExecutor] on_p2p_event failed (%s): %s", event_name, e)

    def broadcast_event(self, event_name: str, event_data: Dict[str, Any], mesh_ids: Optional[List[str]] = None) -> None:
        self.p2p_manager.broadcast_event_sync(event_name, event_data, mesh_ids=mesh_ids)

    def send_event(self, event_name: str, event_data: Dict[str, Any], subject_id: str, mesh_ids: Optional[List[str]] = None) -> None:
        self.p2p_manager.send_event_sync(event_name, event_data, subject_id=subject_id, mesh_ids=mesh_ids)



    def _safe_msg_transform(self, task: AgentTask) -> AgentTask:
        if not self.message_transformer or not getattr(self.message_transformer, "policy", None):
            return task
        try:
            transformed = self.message_transformer.execute({
                "task_id": task.task_id,
                "job_data": task.job_data,
                "task_metadata": task.task_metadata,
                "output_ptr": task.output_ptr,
            })
            return AgentTask(
                task_id=str(transformed.get("task_id", task.task_id)),
                job_data=transformed.get("job_data", task.job_data) or {},
                task_metadata=transformed.get("task_metadata", task.task_metadata) or {},
                output_ptr=transformed.get("output_ptr", task.output_ptr) or {},
            )
        except Exception as e:
            log.exception("Message transformer failed, passing through (task_id=%s): %s", task.task_id, e)
            return task

    def _safe_preprocess_policy(self, data: dict) -> dict:
        if not self.pre_processor or not getattr(self.pre_processor, "policy", None):
            return data
        try:
            return self.pre_processor.execute(data)
        except Exception as e:
            log.exception("Pre-processing policy failed, passing through: %s", e)
            return data

    def _safe_postprocess_policy(self, out: dict) -> dict:
        if not self.post_processor or not getattr(self.post_processor, "policy", None):
            return out
        try:
            return self.post_processor.execute(out)
        except Exception as e:
            log.exception("Post-processing policy failed, passing through: %s", e)
            return out

    def process_task(self, task: AgentTask) -> List[AgentResult]:
        task = self._safe_msg_transform(task)

        pre_policy_input = {
            "task_id": task.task_id,
            "job_data": task.job_data,
            "task_metadata": task.task_metadata,
            "output_ptr": task.output_ptr,
        }
        pre_policy_output = self._safe_preprocess_policy(pre_policy_input)
        task.job_data = pre_policy_output.get("job_data", task.job_data) or task.job_data
        task.task_metadata = pre_policy_output.get("task_metadata", task.task_metadata) or task.task_metadata
        task.output_ptr = pre_policy_output.get("output_ptr", task.output_ptr) or task.output_ptr

        try:
            pre = self.agent.on_preprocess(task)
        except Exception as e:
            log.exception("on_preprocess failed (task_id=%s): %s", task.task_id, e)
            return [AgentResult(
                task_id=task.task_id,
                is_error=True,
                error_data={"stage": "preprocess", "message": str(e)}
            )]

        if pre is None:
            log.info("on_preprocess returned None (task_id=%s); no downstream on_data calls.", task.task_id)
            return []

        results: List[AgentResult] = []
        for entry in pre:
            try:
                res = self.agent.on_data(entry)
            except Exception as e:
                log.exception("on_data failed (subtask_id=%s): %s", entry.task_id, e)
                res = AgentResult(
                    task_id=entry.task_id,
                    is_error=True,
                    error_data={"stage": "data", "message": str(e)}
                )

            post_payload = {
                "task_id": res.task_id,
                "job_output": res.job_output,
                "job_output_metadata": res.job_output_metadata,
                "job_output_trace_data": res.job_output_trace_data,
                "is_error": res.is_error,
                "error_data": res.error_data,
            }
            post_out = self._safe_postprocess_policy(post_payload)

            res.task_id = str(post_out.get("task_id", res.task_id))
            res.job_output = post_out.get("job_output", res.job_output) or res.job_output
            res.job_output_metadata = post_out.get("job_output_metadata", res.job_output_metadata) or res.job_output_metadata
            res.job_output_trace_data = post_out.get("job_output_trace_data", res.job_output_trace_data) or res.job_output_trace_data
            res.is_error = bool(post_out.get("is_error", res.is_error))
            res.error_data = post_out.get("error_data", res.error_data) or res.error_data

            results.append(res)

        return results
