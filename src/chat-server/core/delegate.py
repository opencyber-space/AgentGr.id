import logging
from typing import Any, Dict, Tuple

import httpx

from .config import DELEGATE_SERVER_URL

logger = logging.getLogger("chat.delegate")

SUBMIT_ENDPOINT = "/api/submit-and-wait"


async def submit_and_wait(
    subject_id: str,
    session_id: str,
    task_id: str,
    task_data: Dict[str, Any],
) -> Tuple[Dict, Dict]:
    """POST to the delegate server and return (request_payload, response_body)."""
    payload = {
        "subject_id": subject_id,
        "session_id": session_id,
        "task_id": task_id,
        "task_data": task_data,
    }
    url = f"{DELEGATE_SERVER_URL}{SUBMIT_ENDPOINT}"
    logger.debug("Delegating task_id=%s to %s", task_id, url)

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return payload, resp.json()
