import logging
from flask import Flask, jsonify, request
from kubernetes.client import ApiException

from .k8s_infra import AgentsExecutorManager
from .k8s_agent_infra import AgentsInstanceDeployer
from .db.agents_db import SubjectDBClient
from .k8s_workflow import WorkflowExecutorManager

# Initialize Flask app
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("executor-api")

manager = AgentsExecutorManager(logger=logger)
deployer = AgentsInstanceDeployer(logger=logger)

def get_agent_image(subject_id: str):
    db_client = SubjectDBClient()
    subject = db_client.get_subject(subject_id)
    if not subject:
        raise Exception("subject with given ID not found")
    
    info = subject.info
    return info.container_image_name

@app.route("/executors/<string:subject_id>", methods=["POST"])
def create_executor(subject_id):

    try:

        allocation_info = request.get_json()

        logger.info(f"[Allocation Info] {allocation_info}")

        meshes = allocation_info.get('meshes', [])
        dep_name = manager.create_executor(subject_id, meshes=meshes)
        image_name = get_agent_image(subject_id)
        delegate_url = allocation_info.get('delegate_api_url')

        # deploy agent instances:
        deployer.deploy_instances(allocation_info["instances"], image_name, meshes=meshes, delegate=delegate_url)
        

        return jsonify({
            "success": True,
            "deployment": dep_name,
            "message": f"Executor created for subject_id '{subject_id}'."
        }), 200
    except ApiException as e:
        return jsonify({
            "success": False,
            "error": f"Kubernetes API error: {e}"
        }), e.status or 500
    except Exception as e:
        logger.exception("Error creating executor")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/executors/<string:subject_id>", methods=["DELETE"])
def remove_executor(subject_id):

    try:
        ok = manager.remove_executor(subject_id)
        if ok:
            deleted_resources = manager.delete_resources_by_subject_label(subject_id=subject_id)
            return jsonify({
                "success": True,
                "message": f"Executor removed for subject_id '{subject_id}'.",
                "deleted_resources": deleted_resources
            })
        else:
            return jsonify({
                "success": False,
                "error": f"Failed to remove executor for subject_id '{subject_id}'.",
            }), 500
    except ApiException as e:
        return jsonify({
            "success": False,
            "error": f"Kubernetes API error: {e}"
        }), e.status or 500
    except Exception as e:
        logger.exception("Error removing executor")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/workflows/<string:workflow_id>", methods=["POST"])
def create_workflow_executor(workflow_id: str):
    try:
        payload: dict = request.get_json() or {}

        logger.info(f"[Workflow Allocation Info] {payload}")

        delegate_api_url: str = payload.get("delegate_api_url")
        policy_db_url: str = payload.get("policy_db_url")
        deployment_name: str = payload.get("deployment_name")
        instances: int = payload.get("instances", 1)

        if not delegate_api_url or not policy_db_url:
            return jsonify({
                "success": False,
                "error": "delegate_api_url and policy_db_url are required."
            }), 400

        if not deployment_name:
            return jsonify({
                "success": False,
                "error": "deployment_name is required."
            }), 400

        manager = WorkflowExecutorManager(
            delegate_api_url=delegate_api_url,
            policy_db_url=policy_db_url,
        )

        deployment_info = manager.create_executor(
            workflow_id=workflow_id,
            deployment_name=deployment_name,
        )

        return jsonify({
            "success": True,
            "deployment": deployment_info,
            "service_name": f"{deployment_name}-svc",
            "message": f"Workflow executor created for workflow_id '{workflow_id}'."
        }), 200

    except ApiException as e:
        return jsonify({
            "success": False,
            "error": f"Kubernetes API error: {e}"
        }), e.status or 500

    except Exception as e:
        logger.exception("Error creating workflow executor")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/workflows/<string:workflow_id>", methods=["DELETE"])
def remove_workflow_executor(workflow_id: str):
    try:
        payload: dict = request.get_json() or {}
        deployment_name: str = payload.get("deployment_name")

        if not deployment_name:
            return jsonify({
                "success": False,
                "error": "deployment_name is required."
            }), 400

        # URLs not needed for delete, pass dummy valid values if constructor enforces
        manager = WorkflowExecutorManager(
            delegate_api_url="unused",
            policy_db_url="unused",
        )

        ok: bool = manager.remove_executor(
            deployment_name=deployment_name,
        )

        if ok:
            return jsonify({
                "success": True,
                "message": f"Workflow executor '{deployment_name}' removed successfully."
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": f"Failed to remove workflow executor '{deployment_name}'."
            }), 500

    except ApiException as e:
        return jsonify({
            "success": False,
            "error": f"Kubernetes API error: {e}"
        }), e.status or 500

    except Exception as e:
        logger.exception("Error removing workflow executor")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

def run_server():
    app.run(host="0.0.0.0", port=9000)
