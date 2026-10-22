# app.py
from __future__ import annotations

import logging
import requests
import os
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException, BadRequest


from .crud import SubjectsDB, SubjectsDBError, AgentDeployersDB, AgentDeployersDBError
from .crud import RuntimeSubjectsDB, RuntimeSubjectsDBError

from .schema import AgentDeployer
from .deployer import create_agent_deployer, remove_agent_deployer
from .workflow_crud import WorkflowsDB, RuntimeWorkflowsDB, WorkflowsDBError, RuntimeWorkflowsDBError
from .workflow_schema import Workflow, RuntimeWorkflow

from dataclasses import asdict

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("subjects.api")

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ---- Env & DBs ----
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
SUBJECTS_DB_NAME = os.getenv("SUBJECTS_DB_NAME", "aios")
RUNTIME_DB_NAME = os.getenv("RUNTIME_DB_NAME", SUBJECTS_DB_NAME)
AGENTS_DB_NAME = os.getenv("AGENTS_DB_NAME", "aios")
AGENTS_COLL_NAME = os.getenv("AGENT_DEPLOYERS_COLLECTION", "agent_deployers")

subjects_db = SubjectsDB(mongo_uri=MONGODB_URI, db_name=SUBJECTS_DB_NAME, collection_name="subjects")
runtime_db = RuntimeSubjectsDB(mongo_uri=MONGODB_URI, db_name=RUNTIME_DB_NAME, collection_name="runtime_subjects")
deployers_db = AgentDeployersDB(mongo_uri=MONGODB_URI, db_name=AGENTS_DB_NAME, collection_name=AGENTS_COLL_NAME)
workflows_db = WorkflowsDB(mongo_uri=MONGODB_URI)
runtime_workflows_db = RuntimeWorkflowsDB(mongo_uri=MONGODB_URI)


# ---------------------------
# Helpers
# ---------------------------
def response(ok: bool, data: Any = None, message: Optional[str] = None, status: int = 200):
    payload: Dict[str, Any] = {"success": ok}
    if message is not None:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


@app.errorhandler(Exception)
def handle_exception(e: Exception):
    if isinstance(e, HTTPException):
        return response(False, message=e.description, status=e.code)
    logger.exception("Unhandled exception")
    return response(False, message=str(e), status=500)


# ---------------------------
# Subjects CRUD
# ---------------------------
@app.route("/api/subjects/health", methods=["GET"])
def health_subjects():
    return response(True, {"service": "subjects", "status": "ok"})

@app.route("/api/subjects", methods=["POST"])
def create_subject():
    try:
        data = request.get_json(force=True)
        # Expect full Subject dict payload
        subj = subjects_db._doc_to_subject({"_id": "dummy", **data})  # quick re-use: -> Subject
        created = subjects_db.create_subject(subj)
        return response(True, created.to_dict(), status=201)
    except SubjectsDBError as e:
        return response(False, message=str(e), status=400)

@app.route("/api/subjects/<string:subject_id>", methods=["GET"])
def get_subject(subject_id: str):
    try:
        subj = subjects_db.get_subject(subject_id)
        if not subj:
            return response(False, message="Subject not found", status=404)
        return response(True, subj.to_dict())
    except SubjectsDBError as e:
        return response(False, message=str(e), status=400)

@app.route("/api/subjects/<string:subject_id>", methods=["PUT"])
def replace_subject(subject_id: str):
    try:
        data = request.get_json(force=True)
        subj = subjects_db._doc_to_subject({"_id": "dummy", **data})
        replaced = subjects_db.replace_subject(subject_id, subj)
        if not replaced:
            return response(False, message="Subject not found", status=404)
        return response(True, replaced.to_dict())
    except SubjectsDBError as e:
        return response(False, message=str(e), status=400)

@app.route("/api/subjects/<string:subject_id>", methods=["PATCH"])
def update_subject(subject_id: str):
    """
    Body: { "update": { "identity.subject_name": "New Name", ... } }
    """
    try:
        data = request.get_json(force=True)
        update_fields: Dict[str, Any] = (data or {}).get("update") or {}
        if not isinstance(update_fields, dict):
            raise BadRequest("Body must contain 'update' dict.")
        updated = subjects_db.update_subject_fields(subject_id, update_fields)
        if not updated:
            return response(False, message="Subject not found", status=404)
        return response(True, updated.to_dict())
    except SubjectsDBError as e:
        return response(False, message=str(e), status=400)

@app.route("/api/subjects/<string:subject_id>", methods=["DELETE"])
def delete_subject(subject_id: str):
    try:
        ok = subjects_db.delete_subject(subject_id)
        if not ok:
            return response(False, message="Subject not found", status=404)
        return response(True, {"deleted": True})
    except SubjectsDBError as e:
        return response(False, message=str(e), status=400)

@app.route("/api/subjects", methods=["GET"])
def list_subjects():
   
    try:
        subject_type = request.args.get("subject_type")
        tags = request.args.get("tags")
        tags_list: Optional[List[str]] = [t.strip() for t in tags.split(",")] if tags else None
        limit = int(request.args.get("limit", 50))
        skip = int(request.args.get("skip", 0))
        items = subjects_db.list_subjects(
            subject_type=subject_type, search_tags_any=tags_list, limit=limit, skip=skip
        )
        return response(True, [i.to_dict() for i in items])
    except SubjectsDBError as e:
        return response(False, message=str(e), status=400)

@app.route("/api/subjects/query", methods=["POST"])
def query_subjects():
    
    try:
        body = request.get_json(force=True) or {}
        query = body.get("query") or {}
        projection = body.get("projection")
        sort = body.get("sort")
        limit = int(body.get("limit", 50))
        skip = int(body.get("skip", 0))
        items = subjects_db.query_subjects(query, projection=projection, sort=sort, limit=limit, skip=skip)
        return response(True, [i.to_dict() for i in items])
    except SubjectsDBError as e:
        return response(False, message=str(e), status=400)


# ---------------------------
# RuntimeSubjects CRUD
# ---------------------------
@app.route("/api/runtime-subjects/health", methods=["GET"])
def health_runtime():
    return response(True, {"service": "runtime-subjects", "status": "ok"})

@app.route("/api/runtime-subjects", methods=["POST"])
def create_runtime_subject():
    try:
        data = request.get_json(force=True)
        # Expect: runtime_subject_id, subject_id, runtime_info, runtime_status
        from .crud import RuntimeSubject
        rs = RuntimeSubject.from_dict(data)
        created = runtime_db.create_runtime_subject(rs)
        return response(True, created.to_dict(), status=201)
    except RuntimeSubjectsDBError as e:
        return response(False, message=str(e), status=400)

@app.route("/api/runtime-subjects/<string:runtime_subject_id>", methods=["GET"])
def get_runtime_subject(runtime_subject_id: str):
    try:
        rs = runtime_db.get_runtime_subject(runtime_subject_id)
        if not rs:
            return response(False, message="RuntimeSubject not found", status=404)
        return response(True, rs.to_dict())
    except RuntimeSubjectsDBError as e:
        return response(False, message=str(e), status=400)

@app.route("/api/runtime-subjects/<string:runtime_subject_id>", methods=["PUT"])
def replace_runtime_subject(runtime_subject_id: str):
    try:
        data = request.get_json(force=True)
        from .crud import RuntimeSubject
        rs = RuntimeSubject.from_dict(data)
        replaced = runtime_db.replace_runtime_subject(runtime_subject_id, rs)
        if not replaced:
            return response(False, message="RuntimeSubject not found", status=404)
        return response(True, replaced.to_dict())
    except RuntimeSubjectsDBError as e:
        return response(False, message=str(e), status=400)

@app.route("/api/runtime-subjects/<string:runtime_subject_id>", methods=["PATCH"])
def update_runtime_subject(runtime_subject_id: str):
   
    try:
        data = request.get_json(force=True)
        update_fields: Dict[str, Any] = (data or {}).get("update") or {}
        if not isinstance(update_fields, dict):
            raise BadRequest("Body must contain 'update' dict.")
        updated = runtime_db.update_runtime_subject_fields(runtime_subject_id, update_fields)
        if not updated:
            return response(False, message="RuntimeSubject not found", status=404)
        return response(True, updated.to_dict())
    except RuntimeSubjectsDBError as e:
        return response(False, message=str(e), status=400)

@app.route("/api/runtime-subjects/<string:runtime_subject_id>", methods=["DELETE"])
def delete_runtime_subject(runtime_subject_id: str):
    try:
        ok = runtime_db.delete_runtime_subject(runtime_subject_id)
        if not ok:
            return response(False, message="RuntimeSubject not found", status=404)
        return response(True, {"deleted": True})
    except RuntimeSubjectsDBError as e:
        return response(False, message=str(e), status=400)

@app.route("/api/runtime-subjects", methods=["GET"])
def list_runtime_subjects():
    
    try:
        subject_id = request.args.get("subject_id")
        runtime_status = request.args.get("runtime_status")
        limit = int(request.args.get("limit", 50))
        skip = int(request.args.get("skip", 0))

        sort_param = request.args.get("sort")
        sort = None
        if sort_param:
            field, _, direction = sort_param.partition(":")
            sort = [(field, 1 if direction.lower() != "desc" else -1)]

        items = runtime_db.list_runtime_subjects(
            subject_id=subject_id,
            runtime_status=runtime_status,
            limit=limit,
            skip=skip,
            sort=sort,
        )
        return response(True, [i.to_dict() for i in items])
    except RuntimeSubjectsDBError as e:
        return response(False, message=str(e), status=400)

@app.route("/api/runtime-subjects/query", methods=["POST"])
def query_runtime_subjects():
    
    try:
        body = request.get_json(force=True) or {}
        query = body.get("query") or {}
        projection = body.get("projection")
        sort = body.get("sort")
        limit = int(body.get("limit", 50))
        skip = int(body.get("skip", 0))
        items = runtime_db.query_runtime_subjects(query, projection=projection, sort=sort, limit=limit, skip=skip)
        return response(True, [i.to_dict() for i in items])
    except RuntimeSubjectsDBError as e:
        return response(False, message=str(e), status=400)


@app.route("/api/agent-deployers", methods=["POST"])
def deploy_agent_deployer():
  
    try:
        body = request.get_json(force=True) or {}
        kubeconfig = body.get("kubeconfig")
        deployer_id = body.get("deployer_id")
        deployer_name = body.get("deployer_name")
        deployer_cluster_id = body.get("deployer_cluster_id")
        deployer_public_ip = body.get("deployer_public_ip")

        if not all([kubeconfig, deployer_id, deployer_name, deployer_cluster_id]):
            raise BadRequest("Missing one of: kubeconfig, deployer_id, deployer_name, deployer_cluster_id")

        created = create_agent_deployer(
            kubeconfig=kubeconfig,
            deployer_id=deployer_id,
            deployer_name=deployer_name,
            deployer_cluster_id=deployer_cluster_id,
            db=deployers_db,
            logger=logger,
            deployer_public_ip=deployer_public_ip
        )
        return response(True, created.to_dict(), status=200)
    except AgentDeployersDBError as e:
        return response(False, message=str(e), status=400)


@app.route("/api/agent-deployers/<string:deployer_id>", methods=["DELETE"])
def undeploy_agent_deployer(deployer_id: str):
   
    try:
        body = request.get_json(force=True) or {}
        kubeconfig = body.get("kubeconfig")
        if not kubeconfig:
            raise BadRequest("Missing 'kubeconfig' in body.")

        ok = remove_agent_deployer(
            kubeconfig=kubeconfig,
            deployer_id=deployer_id,
            db=deployers_db,
            logger=logger,
        )
        if not ok:
            return response(False, message="AgentDeployer not found", status=404)
        return response(True, {"deleted": True})
    except AgentDeployersDBError as e:
        return response(False, message=str(e), status=400)

# ========== Agent deployer APIs ============
@app.route("/api/deploy-agent/<string:deployer_id>", methods=["POST"])
def deploy_agent(deployer_id: str):
    try:

        req = request.get_json()

        ad = deployers_db.get_deployer(deployer_id)
        if not ad:
            return response(False, message="AgentDeployer not found", status=404)
        
        url: str = ad.deployer_public_url + "/executors/" + req["subject_id"]

        logger.info(f"pushing payload: {req['allocation']}" )
        resp = requests.post(url, json=req['allocation'])
        resp.raise_for_status()

        response_data = resp.json()
        deployment = response_data['deployment']

        executor_svc_node_port = deployment['executor']['node_port']
        scouter_svc_node_port = deployment['scouter']['node_port']

        executor_url = f"http://{ad.deployer_ip}:{executor_svc_node_port}"
        scouter_url = f"http://{ad.deployer_ip}:{scouter_svc_node_port}"

        runtime_info = {
            "executor": executor_url,
            "scouter": scouter_url,
            "deployment_data": deployment
        }

        # save new runtime subject:
        from .schema import RuntimeSubject
        rs = RuntimeSubject.from_dict({
            "runtime_subject_id": req["subject_id"],
            "subject_id": req["subject_id"],
            "runtime_status": "active",
            "runtime_info": runtime_info
        })

        runtime_db.create_runtime_subject(rs)

        return response(True, data=rs.to_dict())

    except Exception as e:
        return response(False, message=str(e), status=400)


@app.route("/api/remove-agent/<string:deployer_id>/<string:subject_id>", methods=["POST"])
def remove_agent(deployer_id: str, subject_id: str):
    try:

        ad = deployers_db.get_deployer(deployer_id)
        if not ad:
            return response(False, message="AgentDeployer not found", status=404)
        
        url: str = ad.deployer_public_url + "/executors/" + subject_id
        resp = requests.delete(url)
        resp.raise_for_status()

        #  remove from runtime DB:
        runtime_db.delete_runtime_subject(subject_id)

        return response(True, data="removed successfully")
        
    except Exception as e:
        return response(False, message=str(e), status=400)


@app.route("/api/agent-deployers/<string:deployer_id>", methods=["GET"])
def get_deployer(deployer_id: str):
    try:
        ad = deployers_db.get_deployer(deployer_id)
        if not ad:
            return response(False, message="AgentDeployer not found", status=404)
        return response(True, ad.to_dict())
    except AgentDeployersDBError as e:
        return response(False, message=str(e), status=400)


@app.route("/api/agent-deployers/<string:deployer_id>", methods=["PUT"])
def replace_deployer(deployer_id: str):
    
    try:
        data = request.get_json(force=True) or {}
        ad = AgentDeployer.from_dict(data)
        res = deployers_db.replace_deployer(deployer_id, ad)
        if not res:
            return response(False, message="AgentDeployer not found", status=404)
        return response(True, res.to_dict())
    except AgentDeployersDBError as e:
        return response(False, message=str(e), status=400)


@app.route("/api/agent-deployers/<string:deployer_id>", methods=["PATCH"])
def update_deployer(deployer_id: str):
   
    try:
        body = request.get_json(force=True) or {}
        update_fields: Dict[str, Any] = body.get("update") or {}
        if not isinstance(update_fields, dict):
            raise BadRequest("Body must contain 'update' dict.")
        res = deployers_db.update_deployer_fields(deployer_id, update_fields)
        if not res:
            return response(False, message="AgentDeployer not found", status=404)
        return response(True, res.to_dict())
    except AgentDeployersDBError as e:
        return response(False, message=str(e), status=400)


@app.route("/api/agent-deployers", methods=["GET"])
def list_deployers():
   
    try:
        cluster_id = request.args.get("cluster_id")
        limit = int(request.args.get("limit", 50))
        skip = int(request.args.get("skip", 0))
        items = deployers_db.list_deployers(cluster_id=cluster_id, limit=limit, skip=skip)
        return response(True, [i.to_dict() for i in items])
    except AgentDeployersDBError as e:
        return response(False, message=str(e), status=400)


@app.route("/api/agent-deployers/query", methods=["POST"])
def query_deployers():
  
    try:
        body = request.get_json(force=True) or {}
        query = body.get("query") or {}
        projection = body.get("projection")
        sort = body.get("sort")
        limit = int(body.get("limit", 50))
        skip = int(body.get("skip", 0))
        items = deployers_db.query_deployers(query, projection=projection, sort=sort, limit=limit, skip=skip)
        return response(True, [i.to_dict() for i in items])
    except AgentDeployersDBError as e:
        return response(False, message=str(e), status=400)

@app.route("/api/workflows", methods=["POST"])
def create_workflow():
    try:
        data = request.get_json(force=True) or {}
        wf = Workflow.from_dict(data)
        created = workflows_db.create_workflow(wf)
        return response(True, created.to_dict())
    except WorkflowsDBError as e:
        return response(False, message=str(e), status=400)
    except Exception as e:
        return response(False, message=str(e), status=400)


@app.route("/api/workflows/<string:workflow_uri>", methods=["GET"])
def get_workflow(workflow_uri: str):
    try:
        wf = workflows_db.get_workflow(workflow_uri)
        if not wf:
            return response(False, message="Workflow not found", status=404)
        return response(True, wf.to_dict())
    except WorkflowsDBError as e:
        return response(False, message=str(e), status=400)


@app.route("/api/workflows/<string:workflow_uri>", methods=["PUT"])
def replace_workflow(workflow_uri: str):
    try:
        data = request.get_json(force=True) or {}
        wf = Workflow.from_dict(data)
        res = workflows_db.replace_workflow(workflow_uri, wf)
        if not res:
            return response(False, message="Workflow not found", status=404)
        return response(True, res.to_dict())
    except WorkflowsDBError as e:
        return response(False, message=str(e), status=400)


@app.route("/api/workflows/<string:workflow_uri>", methods=["PATCH"])
def update_workflow(workflow_uri: str):
    try:
        body = request.get_json(force=True) or {}
        update_fields: Dict[str, Any] = body.get("update") or {}

        if not isinstance(update_fields, dict):
            raise BadRequest("Body must contain 'update' dict.")

        res = workflows_db.update_workflow_fields(workflow_uri, update_fields)
        if not res:
            return response(False, message="Workflow not found", status=404)

        return response(True, res.to_dict())
    except WorkflowsDBError as e:
        return response(False, message=str(e), status=400)


@app.route("/api/workflows/<string:workflow_uri>", methods=["DELETE"])
def delete_workflow(workflow_uri: str):
    try:
        deleted = workflows_db.delete_workflow(workflow_uri)
        if not deleted:
            return response(False, message="Workflow not found", status=404)
        return response(True, data="deleted successfully")
    except WorkflowsDBError as e:
        return response(False, message=str(e), status=400)


@app.route("/api/workflows", methods=["GET"])
def list_workflows():
    try:
        limit = int(request.args.get("limit", 50))
        skip = int(request.args.get("skip", 0))
        items = workflows_db.list_workflows(limit=limit, skip=skip)
        return response(True, [i.to_dict() for i in items])
    except WorkflowsDBError as e:
        return response(False, message=str(e), status=400)


@app.route("/api/workflows/query", methods=["POST"])
def query_workflows():
    try:
        body = request.get_json(force=True) or {}
        query = body.get("query") or {}
        projection = body.get("projection")
        sort = body.get("sort")
        limit = int(body.get("limit", 50))
        skip = int(body.get("skip", 0))

        items = workflows_db.query_workflows(
            query,
            projection=projection,
            sort=sort,
            limit=limit,
            skip=skip,
        )

        return response(True, [i.to_dict() for i in items])
    except WorkflowsDBError as e:
        return response(False, message=str(e), status=400)


# =========================================================
# RUNTIME WORKFLOW CRUD APIs
# Primary Key: id
# =========================================================

@app.route("/api/runtime-workflows", methods=["POST"])
def create_runtime_workflow():
    try:
        data = request.get_json(force=True) or {}
        rt = RuntimeWorkflow.from_dict(data)
        created = runtime_workflows_db.create_runtime(rt)
        return response(True, created.to_dict())
    except RuntimeWorkflowsDBError as e:
        return response(False, message=str(e), status=400)
    except Exception as e:
        return response(False, message=str(e), status=400)


@app.route("/api/runtime-workflows/<string:runtime_id>", methods=["GET"])
def get_runtime_workflow(runtime_id: str):
    try:
        rt = runtime_workflows_db.get_runtime(runtime_id)
        if not rt:
            return response(False, message="RuntimeWorkflow not found", status=404)
        return response(True, rt.to_dict())
    except RuntimeWorkflowsDBError as e:
        return response(False, message=str(e), status=400)


@app.route("/api/runtime-workflows/<string:runtime_id>", methods=["DELETE"])
def delete_runtime_workflow(runtime_id: str):
    try:
        deleted = runtime_workflows_db.delete_runtime(runtime_id)
        if not deleted:
            return response(False, message="RuntimeWorkflow not found", status=404)
        return response(True, data="deleted successfully")
    except RuntimeWorkflowsDBError as e:
        return response(False, message=str(e), status=400)


@app.route("/api/runtime-workflows", methods=["GET"])
def list_runtime_workflows():
    try:
        workflow_uri = request.args.get("workflow_uri")
        cluster_id = request.args.get("cluster_id")
        limit = int(request.args.get("limit", 50))
        skip = int(request.args.get("skip", 0))

        items = runtime_workflows_db.list_runtimes(
            workflow_uri=workflow_uri,
            cluster_id=cluster_id,
            limit=limit,
            skip=skip,
        )

        return response(True, [i.to_dict() for i in items])
    except RuntimeWorkflowsDBError as e:
        return response(False, message=str(e), status=400)

@app.route("/api/deploy-workflow/<string:deployer_id>", methods=["POST"])
def deploy_workflow(deployer_id: str):
    try:
        req: dict = request.get_json() or {}

        workflow_id: str = req.get("workflow_id")
        workflow_uri: str = req.get("workflow_uri")
        cluster_id: str = req.get("cluster_id")
        deployment_name: str = req.get("deployment_name")
        allocation: dict = req.get("allocation", {})

        if not workflow_id or not deployment_name:
            return response(False, message="workflow_id and deployment_name are required", status=400)

        ad = deployers_db.get_deployer(deployer_id)
        if not ad:
            return response(False, message="WorkflowDeployer not found", status=404)

        # Push allocation to deployer
        url: str = ad.deployer_public_url + f"/workflows/{workflow_uri}"

        logger.info(f"[Workflow Deploy] pushing allocation: {allocation}")
        resp = requests.post(url, json={
            **allocation,
            "deployment_name": deployment_name
        })
        resp.raise_for_status()

        response_data = resp.json()
        deployment = response_data["deployment"]

        node_port = deployment["node_port"]
        workflow_url = f"http://{ad.deployer_ip}:{node_port}"

        # Build runtime object
        runtime = RuntimeWorkflow(
            id=workflow_id,
            workflow_uri=workflow_uri,
            cluster_id=cluster_id,
            deployer_id=deployer_id,
            deployment_name=deployment_name,
            url=workflow_url,
        )

        runtime_workflows_db.create_runtime(runtime)

        return response(True, data=runtime.to_dict())

    except Exception as e:
        logger.exception("Workflow deployment failed")
        return response(False, message=str(e), status=400)


@app.route("/api/remove-workflow/<string:deployer_id>/<string:workflow_id>", methods=["POST"])
def remove_workflow(deployer_id: str, workflow_id: str):
    try:
        runtime = runtime_workflows_db.get_runtime(workflow_id)
        if not runtime:
            return response(False, message="RuntimeWorkflow not found", status=404)

        ad = deployers_db.get_deployer(deployer_id)
        if not ad:
            return response(False, message="WorkflowDeployer not found", status=404)

        url: str = ad.deployer_public_url + f"/workflows/{workflow_id}"

        resp = requests.delete(url, json={
            "deployment_name": runtime.deployment_name
        })
        resp.raise_for_status()

        runtime_workflows_db.delete_runtime(workflow_id)

        return response(True, data="Workflow removed successfully")

    except Exception as e:
        logger.exception("Workflow removal failed")
        return response(False, message=str(e), status=400)

def run_server():
    app.run(host='0.0.0.0', port=9000)
