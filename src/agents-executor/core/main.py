from flask import Flask, request, jsonify
import os
from uuid import uuid4
import json
import logging

from typing import Any, Dict, Union, List

from .db.agents_db import Subject, SubjectDBClient
from .rate_limiter import RateLimiterPolicy
from .message_pre_check import MessagePreChecker
from .backlog import MessageBacklogHandler
from .policy_base import PoliciesManager
from .lb import LoadBalancer
from .p2p import PeersManager
from .k8s import AgentsUpdateNotifier


Message = Dict[str, Any]
BatchOrSingle = Union[Message, List[Message]]


def pre_process(message):

    if message['event_type'] != "task":
        raise Exception("only event of 'event_type=task' is supported")

    return {
        "session_id": str(uuid4()),
        "message_data": {
            "task_id": message['task_id'],
            "job_data": message['task'],
            "output_ptr": message['origin']
        }
    }

def init_subject() -> Subject:
    subject_id = os.getenv("SUBJECT_ID")
    if not subject_id:
        raise Exception("SUBJECT_ID not specified")

    base_url = os.getenv("SUBJECT_DB_URL")
    if not base_url:
        raise Exception("SUBJECT_DB_URL not specified")

    subject_db = SubjectDBClient(base_url)
    return subject_db.get_subject(subject_id)


def init_policy_manager(subject: Subject):
    policies = PoliciesManager(subject)
    rate_limiter = RateLimiterPolicy(policies)
    backlog_handler = MessageBacklogHandler(policies)
    pre_checker = MessagePreChecker(policies)
    return policies, rate_limiter, backlog_handler, pre_checker


def _extract_subject_id(subject: Subject) -> str:
    sid = getattr(subject.identity, "subject_id", None) or getattr(subject.identity, "id", None)
    if not sid:
        raise Exception("Subject has no subject_id/id field")
    return sid


def pre_process_message(
    *,
    session_id: str,
    message_data: Message,
    pre_checker: "MessagePreChecker",
    rate_limiter: "RateLimiterPolicy",
    backlog_handler: "MessageBacklogHandler",
) -> Dict[str, Any]:

    try:
        allowed, reason = pre_checker.check(session_id, message_data)
    except Exception:
        allowed, reason = True, None

    if not allowed:
        return {
            "status": "blocked",
            "stage": "pre_check",
            "reason": reason or {},
        }

    try:
        rl_ok = rate_limiter.is_allowed(session_id, message_data)
    except Exception:
        rl_ok = True

    if not rl_ok:
        return {
            "status": "blocked",
            "stage": "rate_limit",
        }

    try:
        backlogged, data_or_reason = backlog_handler.decide(
            session_id, message_data)
    except Exception:
        backlogged, data_or_reason = False, message_data

    if backlogged:

        return {
            "status": "backlogged",
            "stage": "backlog",
            "reason": data_or_reason if isinstance(data_or_reason, dict) else {},
        }

    if isinstance(data_or_reason, list):
        messages: List[Message] = [
            m for m in data_or_reason if isinstance(m, dict)]
    elif isinstance(data_or_reason, dict):
        messages = [data_or_reason]
    else:
        messages = [message_data]

    return {
        "status": "ready",
        "messages": messages,
    }


def create_app() -> Flask:
    app = Flask(__name__)

    subject = init_subject()
    policies, rate_limiter, backlog_handler, pre_checker = init_policy_manager(subject)

    lb = LoadBalancer(policies)
    lb.set_subject_id(_extract_subject_id(subject))
    lb.start()

    subject_id = os.getenv("SUBJECT_ID")
    if not subject_id:
        raise Exception("SUBJECT_ID not specified")
    notifier = AgentsUpdateNotifier(on_instances_update=lb.update_current_instances, namespace="agents")
    notifier.start(block_id=subject_id)

    async def on_p2p_message(mesh_id, msg):
        try:
            raw = msg.data.decode("utf-8")
        except Exception:
            raw = repr(msg.data)

        logging.info("[p2p <- %s] subject=%s raw=%s", mesh_id, getattr(msg, "subject", "?"), raw)

        try:
            payload = json.loads(raw)
        except Exception as e:
            logging.warning("[p2p %s] bad JSON: %s", mesh_id, e)
            return

        # --- unwrap control plane / custom_event like we discussed ---
        if isinstance(payload, dict) and "event" in payload:
            evt = payload.get("event")

            if evt in ("join", "remove", "task_result"):
                logging.debug("[p2p %s] ignoring control event %s", mesh_id, evt)
                return

            if evt == "custom_event":
                payload = payload.get("event_data") or {}
            else:
                logging.debug("[p2p %s] unknown event %s", mesh_id, evt)
                return

        try:
            payload = pre_process(payload)
        except Exception as e:
            logging.exception("[p2p %s] pre_process failed: %s", mesh_id, e)
            return

        session_id = payload.get("session_id")
        message_data = payload.get("message_data")

        if not session_id or not isinstance(message_data, dict):
            logging.warning("[p2p %s] dropped (no session/message_data): %s", mesh_id, payload)
            return

        logging.info("[p2p %s] ACCEPT session_id=%s message_data_keys=%s",
                    mesh_id, session_id, list(message_data.keys()))

        try:
            result = pre_process_message(
                session_id=session_id,
                message_data=message_data,
                pre_checker=pre_checker,
                rate_limiter=rate_limiter,
                backlog_handler=backlog_handler,
            )

            status = result.get("status")

            if status == "blocked":
                logging.info("[p2p %s] BLOCKED session_id=%s", mesh_id, session_id)
                return

            if status == "ready":
                logging.info("[p2p %s] SUBMIT session_id=%s", mesh_id, session_id)
                lb.submit(result)

            # if backlogged, backlog_handler already took it
            logging.info("[p2p %s] OK status=%s session_id=%s", mesh_id, status, session_id)

        except Exception as e:
            logging.exception("[p2p %s] handler crashed: %s", mesh_id, e)
            return

    # Create P2P manager bound to this subject and start listeners in a thread
    p2p = PeersManager(agent_data=subject)
    p2p.set_message_handler(on_p2p_message)
    p2p.start_background_loop()
   
    # {"meshes":[{"mesh_id":"xxx","url":"nats://host1:4222"},{"mesh_id":"yyy","url":"nats://host2:4222"}]}
    p2p.initialize_meshes_sync()


    @app.route("/dryRun", methods=["POST"])
    def dry_run():
        try:
            payload = request.get_json(force=True) or {}
            # payload = pre_process(payload)

            session_id = payload.get("session_id")
            message_data: Dict[str, Any] = payload.get("message_data")
            message_data["is_dry_run"] = True

            if not session_id or not isinstance(message_data, dict):
                return jsonify({"success": False, "error": "Missing or invalid 'session_id' or 'message_data'"}), 400

            result = pre_process_message(
                session_id=session_id,
                message_data=message_data,
                pre_checker=pre_checker,
                rate_limiter=rate_limiter,
                backlog_handler=backlog_handler,
            )

            status = result.get("status")

            if status == "blocked":
                return jsonify({
                    "success": False,
                    "error": "blocked",
                    "stage": result.get("stage"),
                    "reason": result.get("reason") or {}
                }), 429

            if status == "ready":
                return jsonify({"success": True, "message": "ok"})

        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/submitTask", methods=["POST"])
    def submit_task():
        try:
            payload = request.get_json(force=True) or {}

            payload = pre_process(payload)

            session_id = payload.get("session_id")
            message_data: Dict[str, Any] = payload.get("message_data")

            if not session_id or not isinstance(message_data, dict):
                return jsonify({"success": False, "error": "Missing or invalid 'session_id' or 'message_data'"}), 400

            result = pre_process_message(
                session_id=session_id,
                message_data=message_data,
                pre_checker=pre_checker,
                rate_limiter=rate_limiter,
                backlog_handler=backlog_handler,
            )

            status = result.get("status")

            if status == "blocked":
                return jsonify({
                    "success": False,
                    "error": "blocked",
                    "stage": result.get("stage"),
                    "reason": result.get("reason") or {}
                }), 429

            if status == "ready":
                lb.submit(result)

            # Acknowledge for both ready/backlogged
            return jsonify({
                "success": True,
                "message": "task received for processing",
                "result": result
            }), 202

        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/healthz", methods=["GET"])
    def healthz():
        return jsonify({"ok": True}), 200

    # keep references for later teardown or inspection
    app._subject = subject
    app._policies = policies
    app._rate_limiter = rate_limiter
    app._backlog_handler = backlog_handler
    app._pre_checker = pre_checker
    app._lb = lb
    app._notifier = notifier
    app._p2p = p2p

    return app