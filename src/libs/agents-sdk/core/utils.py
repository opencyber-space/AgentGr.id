import json
import logging
import os
from typing import Any, Dict, List, Optional

import redis
from websockets.sync.server import serve 

from .agent_executor import AgentExecutor, task_from_dict, result_to_dict
from .input_streams.redis_listener import RedisBRPOPWorker
from .input_streams.websocket_listener import WebSocketJSONSyncServer
from .types import AgentTask

log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


import json
import os
from typing import Any, Dict, List, Optional, Union

import redis
from .exchange_reporter import OutputReporter
from .p2p import PeersManager



def start_redis_listener(
    *,
    executor: "AgentExecutor",
    stream: str,
    redis_url: Optional[str] = None,
    results_stream: Optional[str] = None,
    block_ms: int = 10_000,
    p2p_mesh: PeersManager = None
) -> "RedisBRPOPWorker":

    reporter = OutputReporter()
    reporter.start()
  
    redis_url = redis_url or os.getenv("REDIS_URL") or "redis://localhost:6379/0"
    r = redis.from_url(redis_url, decode_responses=True)

    queue_key = stream  # same param name reused as list key
    block_seconds = max(1, int(block_ms / 1000))

    def _select_results_stream(task_dict: Dict[str, Any]) -> str:
        task_output_ptr = task_dict.get("output_ptr") or {}
        task_stream = task_output_ptr.get("stream") if isinstance(task_output_ptr, dict) else None
        return results_stream or task_stream or f"{stream}:results"

    def _publish_results(task: AgentTask, results: List[Dict[str, Any]]) -> None:
        logging.info(f"[task_data] {task}")
        for result in results:
            logging.info(f"[task_data] {result}")

            # obtain task output:
            output_ptr = task.output_ptr
            exchange_id = output_ptr.get('exchange_id')

            if exchange_id:

                job_output_data = result.get('job_output_metadata', {})
                job_tracing_data = result.get('job_output_trace_data', {})
                is_error = result.get('is_error', False)
                error_data = result.get('error_data', {})
                job_output_metadata = result.get('job_output_metadata', {})

                if task.output_ptr.get("type") == "exchange":
                    reporter.submit_output(
                        exchange_id=exchange_id,
                        result_body={
                            "task_id": task.task_id,
                            "job_output": job_output_data,
                            "job_output_metadata": job_output_metadata,
                            "job_output_trace_data": job_tracing_data,
                            "is_error": is_error,
                            "error_data": error_data
                        }
                    )

                elif task.output_ptr.get("type") == "mesh":
                    p2p_mesh.reply_sync(task_id=output_ptr.get('internal_task_id'), to_subject_id=task.output_ptr.get('sender_subject_id'), result_data={
                            "task_id": task.task_id,
                            "job_output": job_output_data,
                            "job_output_metadata": job_output_metadata,
                            "job_output_trace_data": job_tracing_data,
                            "is_error": is_error,
                            "error_data": error_data
                    })
    
            else:
                log.info(f"[OutputReporter] task_id={task.task_id} has no exchange_id specified")


    def _ensure_dict(msg: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        if isinstance(msg, dict):
            return msg
        try:
            obj = json.loads(msg)
            if isinstance(obj, dict):
                return obj
            return {"value": obj}
        except Exception:
            return {"value": msg}

    def _handler(message: Union[str, Dict[str, Any]]) -> None:
        data = _ensure_dict(message)

        task = task_from_dict(data)
        res_list = executor.process_task(task)  # -> List[AgentResult]

        out: List[Dict[str, Any]] = []
        for res in res_list:
            d = result_to_dict(res)
            d.setdefault("origin_task_id", task.task_id)
            out.append(d)

        _publish_results(task, out)

    worker = RedisBRPOPWorker(
        redis_url=redis_url,
        queue_key=queue_key,
        block_seconds=block_seconds,
    )

    def _run():
        worker.run_forever(_handler)

    worker.run = _run            
    worker.handler = _handler

    return worker



def start_websocket_listener(
    *,
    executor: AgentExecutor,
    host: str = "127.0.0.1",
    port: int = 8765,
    auth_token: Optional[str] = None,
    max_size: int = 2 * 1024 * 1024,
) -> None:
   
    def _ws_callback(msg: Dict[str, Any]) -> Dict[str, Any]:
        # batch
        if "tasks" in msg:
            if not isinstance(msg["tasks"], list):
                raise ValueError("'tasks' must be a list of objects")
            all_results: List[Dict[str, Any]] = []
            for t in msg["tasks"]:
                task = task_from_dict(t)
                res_list = executor.process_task(task)
                for r in res_list:
                    d = result_to_dict(r)
                    d.setdefault("origin_task_id", task.task_id)
                    all_results.append(d)
            return {"results": all_results}

        task_payload = msg.get("task", msg)
        task = task_from_dict(task_payload)
        res_list = executor.process_task(task)
        out = []
        for r in res_list:
            d = result_to_dict(r)
            d.setdefault("origin_task_id", task.task_id)
            out.append(d)
        return {"results": out}

    server = WebSocketJSONSyncServer(
        host=host,
        port=port,
        auth_token=auth_token,
        max_size=max_size,
    )

    server.run_forever(_ws_callback)
