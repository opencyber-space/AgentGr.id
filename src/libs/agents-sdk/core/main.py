# main.py
import logging
import os
import signal
import threading
import time

from .utils import start_websocket_listener, start_redis_listener
from .db.agents_db import SubjectDBClient

from .agent_executor import AgentExecutor 

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("launcher")


def run_websocket(executor: AgentExecutor) -> None:
  
    start_websocket_listener(
        executor=executor,
        host=os.getenv("WS_HOST", "0.0.0.0"),
        port=int(os.getenv("WS_PORT", "8765")),
        auth_token=os.getenv("WS_BEARER_TOKEN"),  # or None
        max_size=2 * 1024 * 1024,
    )


def init_agent_class(agent_class):
    agent_id = os.getenv("SUBJECT_ID")
    if not agent_id:
        raise Exception("subject not specified")
    
    subject_db_client = SubjectDBClient(os.getenv("SUBJECT_DB_URL"))
    subject = subject_db_client.get_subject(agent_id)
    
    return subject, agent_class


def main(agent_class):

    subject, agent_class = init_agent_class(agent_class)
    executor = AgentExecutor(agent_class=agent_class, subject=subject)

    ws_thread = threading.Thread(target=run_websocket, args=(executor,), daemon=True)
    ws_thread.start()
    log.info("WebSocket listener started on background thread (daemon=%s)", ws_thread.daemon)

    worker = start_redis_listener(
        executor=executor,
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        stream=os.getenv("REDIS_STREAM", "jobs:inbox"),
        results_stream=os.getenv("RESULTS_STREAM", "jobs:results"),
        block_ms=int(os.getenv("BLOCK_MS", "100000")),
        p2p_mesh=executor.p2p_manager
    )

    stopping = {"value": False}

    def _stop(signum, frame):
        if stopping["value"]:
            return
        stopping["value"] = True
        log.info("Signal %s received; stopping Redis worker...", signum)
        try:
            worker.stop()  
        except Exception:
            pass

    try:
        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)
    except Exception:
        pass

    try:
        if hasattr(worker, "run"):
            worker.run() 
        else:
            raise RuntimeError("worker.run() not found; ensure you're using the provided start_redis_listener")
    finally:
        time.sleep(0.25)
        log.info("Shutdown complete.")

