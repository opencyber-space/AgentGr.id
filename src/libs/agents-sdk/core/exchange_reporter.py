import logging
import threading
import os
import time
from dataclasses import dataclass
from queue import Queue, Full, Empty
from typing import Any, Dict, Optional

from .exchange_client import ExchangeClient

@dataclass(frozen=True)
class _ReportItem:
    exchange_id: str
    result_body: Dict[str, Any]
    headers: Optional[Dict[str, str]] = None


class OutputReporter:
   

    def __init__(
        self,
        *,
        max_queue_size: int = 10000,
        retry_attempts: int = 3,
        retry_backoff_secs: float = 2.0,
        logger: Optional[logging.Logger] = None,
        worker_name: str = "OutputReporterWorker",
        daemon: bool = True,
    ) -> None:
        self.client = ExchangeClient(base_url=os.getenv(""))
        self.q: "Queue[_ReportItem]" = Queue(maxsize=max_queue_size)
        self.retry_attempts = max(1, retry_attempts)
        self.retry_backoff_secs = max(0.0, retry_backoff_secs)

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._worker_loop, name=worker_name, daemon=daemon)

        self.log = logger or logging.getLogger(self.__class__.__name__)
        if not self.log.handlers:
            logging.basicConfig(level=logging.INFO)

        self._sentinel = object()


    def start(self) -> None:
        if self._thread.is_alive():
            self.log.debug("OutputReporter already running.")
            return
        self.log.info("Starting OutputReporter worker thread.")
        self._stop_event.clear()
        self._thread.start()

    def submit_output(
        self,
        exchange_id: str,
        result_body: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        *,
        block: bool = True,
        timeout: Optional[float] = None,
    ) -> None:
        
        if self._stop_event.is_set():
            self.log.warning("submit_output called after stop was requested; dropping entry.")
            return

        item = _ReportItem(exchange_id=exchange_id, result_body=result_body, headers=headers)
        try:
            self.q.put(item, block=block, timeout=timeout)
            self.log.debug("Queued output for exchange_id=%s (qsize=%d)", exchange_id, self.q.qsize())
        except Full:
            self.log.error(
                "Queue is full (size=%d). Failed to enqueue output for exchange_id=%s.",
                self.q.maxsize,
                exchange_id,
            )
            raise

    def flush(self, timeout: Optional[float] = None) -> bool:
     
        deadline = None if timeout is None else time.time() + timeout
        while not self.q.empty():
            if timeout is not None and time.time() >= deadline:
                return False
            time.sleep(0.05)
        return True

    def stop(self, *, drain: bool = True, join_timeout: Optional[float] = None) -> None:
        
        self.log.info("Stopping OutputReporter (drain=%s)...", drain)
        self._stop_event.set()

        if drain:
            self.q.put(self._sentinel)  
        else:
            try:
                while True:
                    self.q.get_nowait()
                    self.q.task_done()
            except Empty:
                pass
            self.q.put(self._sentinel)  
        self._thread.join(timeout=join_timeout)
        if self._thread.is_alive():
            self.log.warning("OutputReporter worker did not stop within the timeout.")

    # ---------- Internal ----------

    def _worker_loop(self) -> None:
        self.log.info("OutputReporter worker started.")
        while True:
            try:
                item = self.q.get() 
                if item is self._sentinel: 
                    self.q.task_done()
                    self.log.info("OutputReporter received sentinel; exiting worker loop.")
                    break

                self._process_item(item)
            except Exception as e:
                # Never let the worker die
                self.log.exception("Unexpected error in worker loop: %s", e)
            finally:
               
                pass

        self.log.info("OutputReporter worker stopped.")

    def _process_item(self, item: _ReportItem) -> None:
       
        try:
            for attempt in range(1, self.retry_attempts + 1):
                try:
                    self.log.debug(
                        "Sending result to exchange_id=%s (attempt %d/%d).",
                        item.exchange_id,
                        attempt,
                        self.retry_attempts,
                    )
                    resp = self.client.set_job_result(
                        exchange_id=item.exchange_id,
                        result_body=item.result_body,
                        headers=item.headers,
                    )

                    # Expecting {"success": True/False, ...}
                    if isinstance(resp, dict) and resp.get("success", False):
                        self.log.info(
                            "Successfully reported output to exchange_id=%s.",
                            item.exchange_id,
                        )
                        break
                    else:
                        self.log.warning(
                            "Exchange responded with failure for exchange_id=%s: %s",
                            item.exchange_id,
                            resp,
                        )
                        # Decide whether to retry based on attempt count
                        if attempt < self.retry_attempts:
                            time.sleep(self.retry_backoff_secs * attempt)
                            continue
                        else:
                            self.log.error(
                                "Exhausted retries for exchange_id=%s. Dropping item.",
                                item.exchange_id,
                            )
                    break  # exit attempts loop after handling response

                except Exception as send_err:
                    self.log.warning(
                        "Error reporting output to exchange_id=%s on attempt %d/%d: %s",
                        item.exchange_id,
                        attempt,
                        self.retry_attempts,
                        send_err,
                    )
                    if attempt < self.retry_attempts:
                        time.sleep(self.retry_backoff_secs * attempt)
                    else:
                        self.log.error(
                            "Exhausted retries for exchange_id=%s due to exceptions. Dropping item.",
                            item.exchange_id,
                        )
                        break
        finally:
            self.q.task_done()


