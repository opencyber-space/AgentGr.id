import os
import json
import logging
from typing import Any, Dict, Optional
import time
from flask import Flask, request, jsonify

from .exchange_register import register_subject_on_exchange, register_subject_on_exchanges
from .db.schema import Subject
from .db.agents_db import SubjectDBClient

app = Flask(__name__)
logger = logging.getLogger("exchange_api")
if not logger.handlers:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())


def _as_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "y", "on")


def init():
    try:

        subject_id = os.getenv("SUBJECT_ID")
        subject = SubjectDBClient(base_url=os.getenv("SUBJECT_DB_URL"), timeout=100).get_subject(subject_id)

        if not subject:
            raise Exception("subject not found")
        
        result = register_subject_on_exchanges(
            subject,
            subject_page_base="",
            docs_base="",
            api_base="",         
            timeout=100,
            max_retries=5,
            verbose=True,
        )

        logger.info(f"[Subject Registration]: {result}")
        
    except Exception as e:
        raise e

@app.post("/subject/register-exchanges")
def register_subject_all():
    
    try:
        body: Dict[str, Any] = request.get_json(silent=True) or {}
        subject_dict = body.get("subject", body)
        if not isinstance(subject_dict, dict):
            return jsonify({"success": False, "error": "Invalid subject payload"}), 400

        # Build Subject
        subject = Subject.from_dict(subject_dict)

        subject_page_base: Optional[str] = body.get("subject_page_base")
        docs_base: Optional[str] = body.get("docs_base")
        api_base: Optional[str] = body.get("api_base") 

        timeout = float(body.get("timeout", 15.0))
        max_retries = int(body.get("max_retries", 3))
        verbose = _as_bool(body.get("verbose"), True)

        result = register_subject_on_exchanges(
            subject,
            subject_page_base=subject_page_base,
            docs_base=docs_base,
            api_base=api_base,         
            timeout=timeout,
            max_retries=max_retries,
            verbose=verbose,
        )
        status = 200 if result.get("success") else 207  
        return jsonify(result), status

    except Exception as e:
        logger.exception("[/subjects/register] error")
        return jsonify({"success": False, "error": str(e)}), 500


@app.post("/subjects/register/<string:exchange_id>")
def register_subject_single(exchange_id: str):
   
    try:
        body: Dict[str, Any] = request.get_json(silent=True) or {}
        subject_dict = body.get("subject", body)
        if not isinstance(subject_dict, dict):
            return jsonify({"ok": False, "error": "Invalid subject payload"}), 400

        subject = Subject.from_dict(subject_dict)

        subject_page_base: Optional[str] = body.get("subject_page_base")
        docs_base: Optional[str] = body.get("docs_base")
        api_base: Optional[str] = body.get("api_base")  

        timeout = float(body.get("timeout", 15.0))
        max_retries = int(body.get("max_retries", 3))

        result = register_subject_on_exchange(
            subject,
            exchange_id,
            subject_page_base=subject_page_base,
            docs_base=docs_base,
            api_base=api_base,
            timeout=timeout,
            max_retries=max_retries,
        )
        status = 200 if result.get("ok") else 502
        return jsonify(result), status

    except Exception as e:
        logger.exception(f"[/subjects/register/{exchange_id}] error")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True})


def run_server():

    logger.info("Agent scouter initializing")
    time.sleep(10)
    init()
    app.run(host='0.0.0.0', port=10000)