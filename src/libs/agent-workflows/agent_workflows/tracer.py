

class WorkflowTracer:

    def log(self, event_type: str, payload: dict):
        print(f"[TRACE] {event_type} | {payload}")