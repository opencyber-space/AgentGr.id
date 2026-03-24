import os
import logging
from typing import Any, Dict

from flask import Flask, request, jsonify

from .executor import (
    AgentDSLWorkflowExecutor,
    WorkflowExecutionError,
    WorkflowNodeError,
    WorkflowRouterError,
    WorkflowSpecError,
    WorkflowDBError,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

executor: AgentDSLWorkflowExecutor = None


def load_workflow() -> AgentDSLWorkflowExecutor:
    workflow_id = os.getenv("WORKFLOW_ID", "")

    if not workflow_id:
        raise RuntimeError("Environment variable WORKFLOW_ID is not set")

    logger.info(f"Loading workflow '{workflow_id}'")

    executor = AgentDSLWorkflowExecutor.from_workflow_id(workflow_id)

    logger.info("Workflow loaded successfully")

    return executor


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/execute", methods=["POST"])
def execute_workflow():
    global executor


    if executor is None:
        return jsonify({
            "success": False,
            "error": "Workflow executor not initialised"
        }), 500

    try:
        payload: Dict[str, Any] = request.get_json(force=True)

        logger.info("Received workflow execution request")

        result = executor.execute(payload)

        return jsonify({
            "success": True,
            "data": result
        })

    except WorkflowSpecError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    except WorkflowNodeError as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "node_id": e.node_id
        }), 500

    except WorkflowRouterError as e:
        return jsonify({"success": False, "error": str(e)}), 500

    except WorkflowExecutionError as e:
        return jsonify({"success": False, "error": str(e)}), 500

    except WorkflowDBError as e:
        return jsonify({"success": False, "error": str(e)}), 500

    except Exception as e:
        logger.exception("Unexpected execution error")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


def run_server():

    try:
        global executor
        executor = load_workflow()
    except Exception as e:
        logger.error(f"Failed to load workflow: {e}")
        raise

    port = int(os.getenv("PORT", 9100))

    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True
    )