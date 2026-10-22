import os
import logging
from typing import Any, Dict

from .redis_listener import RedisOutputListener
from .task_init import push_task_to_agent

from flask import Flask, request, jsonify
import requests

REDIS_PUBLIC_HOST = os.getenv("REDIS_PUBLIC_HOST", "localhost")
REDIS_PUBLIC_PORT = int(os.getenv("REDIS_PUBLIC_PORT", "6379"))

RUNTIME_SUBJECTS_API_URL = os.getenv("RUNTIME_SUBJECTS_API_URL") 

REDIS_URL = os.getenv("REDIS_URL", f"redis://{REDIS_PUBLIC_HOST}:{REDIS_PUBLIC_PORT}/0")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
log = logging.getLogger("submit_and_wait_api")

app = Flask(__name__)


@app.route("/api/submit-and-wait", methods=["POST"])
def submit_and_wait():
   
    if not RUNTIME_SUBJECTS_API_URL:
        return jsonify({"success": False, "message": "RUNTIME_SUBJECTS_API_URL is not set"}), 500

    data: Dict[str, Any] = request.get_json(silent=True) or {}
    subject_id = data.get("subject_id")
    session_id = data.get("session_id")
    task_id = data.get("task_id")
    task_data = data.get("task_data")
    headers = data.get("headers") or {}

    missing = [k for k in ("subject_id", "session_id", "task_id", "task_data") if not data.get(k)]
    if missing:
        return jsonify({"success": False, "message": f"Missing fields: {', '.join(missing)}"}), 400

    redis_url = data.get("redis_url") or REDIS_URL

    try:
        with requests.Session() as sess:
            ack = push_task_to_agent(
                runtime_db_base_url=RUNTIME_SUBJECTS_API_URL,
                runtime_subject_id=subject_id,   # map subject_id -> runtime_subject_id
                session_id=session_id,
                task_id=task_id,
                task_data=task_data,
                headers=headers,
                session=sess,
            )

            ack_raw = getattr(ack, "raw", {}) if ack else {}

    except NameError as e:
        log.exception("Server misconfiguration/missing import: %s", e)
        return jsonify({"success": False, "message": "Server not fully configured (missing imports)."}), 500
    except Exception as e:
       
        log.exception("Failed to submit task: %s", e)
        return jsonify({"success": False, "message": f"Submit failed: {e}"}), 502

    try:
        with RedisOutputListener(redis_url=redis_url) as listener:
            output = listener.get_output(session_id)
    except Exception as e:
        log.exception("Failed while waiting for output: %s", e)
        return jsonify({"success": False, "message": f"Wait failed: {e}"}), 502

    return jsonify({
        "success": True,
        "ack": ack_raw,
        "output": output,
    }), 200


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"ok": True, "redis": bool(REDIS_URL), "runtime_api": bool(RUNTIME_SUBJECTS_API_URL)}), 200


def run_app():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
