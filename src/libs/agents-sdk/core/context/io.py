import time
import uuid
from typing import Any, Optional


class IOChannel:

    def __init__(self, store, name: str):
        self.base = store.get_namespace("io_channels").get_namespace(name)

    def _req_store(self, request_id: str):
        return self.base.get_namespace(request_id)

    def submit(self, input_data: Any) -> str:
        req_id = str(uuid.uuid4())
        s = self._req_store(req_id)
        s.set("input", input_data)
        s.set("status", "pending")
        s.set("created_at", time.time())
        return req_id

    def fetch_input(self) -> Optional[tuple]:
        for rid in self.base.keys():
            s = self._req_store(rid)
            if s.get("status") == "pending":
                s.set("status", "processing")
                return rid, s.get("input")
        return None

    def set_output(self, request_id: str, output: Any):
        s = self._req_store(request_id)
        s.set("output", output)
        s.set("status", "complete")
        s.set("completed_at", time.time())

    def wait_for_output(
        self,
        request_id: str,
        timeout: int = 60,
        poll_interval: float = 0.1,
    ) -> Optional[Any]:

        s = self._req_store(request_id)
        start = time.time()

        while True:
            if s.get("status") == "complete":
                return s.get("output")

            if timeout and time.time() - start > timeout:
                return None

            time.sleep(poll_interval)

    def get_status(self, request_id: str):
        return self._req_store(request_id).get("status")

    def cleanup(self, request_id: str):
        self._req_store(request_id).clear()