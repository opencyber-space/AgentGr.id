import os
import time
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from .metadata import subject_to_exchange_subject

import requests

logger = logging.getLogger("exchange_registration")
if not logger.handlers:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())


class ExchangeRegistrationError(Exception):
    pass


def _require_env(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise ExchangeRegistrationError(f"Missing required environment variable: {name}")
    return v


def _unique_exchanges(subject) -> List[str]:
    seen, out = set(), []
    for eid in (getattr(subject.runtime, "exchanges", None) or []):
        eid = (eid or "").strip()
        if eid and eid not in seen:
            seen.add(eid)
            out.append(eid)
    return out


def _endpoint(base_url: str, exchange_id: str) -> str:
    return f"{base_url.rstrip('/')}/exchange/{exchange_id}/exchange_subjects/add"


def _post_json(
    url: str, payload: Dict[str, Any], *, timeout: float = 15.0, max_retries: int = 3, backoff_sec: float = 0.75
) -> Tuple[int, Dict[str, Any]]:
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            ct = (resp.headers.get("content-type") or "").lower()
            data: Dict[str, Any]
            if "application/json" in ct:
                data = resp.json()
            else:
                # Try best-effort parse; else wrap as text
                try:
                    data = json.loads(resp.text or "{}")
                except Exception:
                    data = {"raw": (resp.text or "").strip()}
            return resp.status_code, data
        except Exception as e:
            last_err = e
            logger.warning(f"[exchange.register] POST failed (attempt {attempt}/{max_retries}) {url}: {e}")
            if attempt < max_retries:
                time.sleep(backoff_sec * attempt)
    # If we’re here, exhausted retries
    raise ExchangeRegistrationError(f"POST {url} failed after {max_retries} attempts: {last_err}")


def register_subject_on_exchanges(
    subject,
    *,
    subject_page_base: Optional[str] = None,
    api_base: Optional[str] = None,
    docs_base: Optional[str] = None,
    timeout: float = 15.0,
    max_retries: int = 3,
    verbose: bool = True,
) -> Dict[str, Any]:
    
    base_url = api_base or _require_env("JOB_EXCHANGE_API_URL")

    # 2) Collect exchange IDs
    exchange_ids = _unique_exchanges(subject)

    if not exchange_ids:
        return

   
    ex_record = subject_to_exchange_subject(
        subject,
        subject_page_base=subject_page_base,
        api_base=base_url,     
        docs_base=docs_base,
    )
    payload = ex_record.to_dict()

    results: Dict[str, Any] = {}
    overall_ok = True

    for eid in exchange_ids:
        url = _endpoint(base_url, eid)
        try:
            status, resp_json = _post_json(url, payload, timeout=timeout, max_retries=max_retries)
            ok = (200 <= status < 300) and bool(resp_json.get("success", True))
            results[eid] = {"ok": ok, "status": status, "response": resp_json}
            if verbose:
                logger.info(f"[exchange.register] {eid} -> {status} ok={ok}")
            overall_ok = overall_ok and ok
        except Exception as e:
            overall_ok = False
            results[eid] = {"ok": False, "status": 0, "response": {"error": str(e)}}
            logger.error(f"[exchange.register] {eid} -> ERROR: {e}")

    return {"success": overall_ok, "results": results}



def register_subject_on_exchange(
    subject,
    exchange_id: str,
    *,
    subject_page_base: Optional[str] = None,
    api_base: Optional[str] = None,
    docs_base: Optional[str] = None,
    timeout: float = 15.0,
    max_retries: int = 3,
) -> Dict[str, Any]:
   
    base_url = api_base or _require_env("JOB_EXCHANGE_API_URL")

    ex_record = subject_to_exchange_subject(
        subject,
        subject_page_base=subject_page_base,
        api_base=base_url,
        docs_base=docs_base,
    )
    payload = ex_record.to_dict()

    url = _endpoint(base_url, exchange_id)

    try:
        status, resp_json = _post_json(
            url, payload, timeout=timeout, max_retries=max_retries
        )
        ok = (200 <= status < 300) and bool(resp_json.get("success", True))
        return {"ok": ok, "status": status, "response": resp_json}
    except Exception as e:
        return {"ok": False, "status": 0, "response": {"error": str(e)}}
