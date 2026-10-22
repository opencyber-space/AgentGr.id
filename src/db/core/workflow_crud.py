import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from pymongo import MongoClient, ASCENDING, ReturnDocument
from pymongo.errors import PyMongoError, DuplicateKeyError

logger = logging.getLogger(__name__)

from .workflow_schema import Workflow, RuntimeWorkflow

class WorkflowsDBError(Exception):
    pass


class WorkflowsDB:

    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        db_name: str = "workflows_db",
        collection_name: str = "workflows",
    ):
        mongo_uri = mongo_uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")

        try:
            self.client = MongoClient(mongo_uri)
            self.db = self.client[db_name]
            self.col = self.db[collection_name]
            self._ensure_indexes()
            logger.info("Connected to MongoDB %s/%s", db_name, collection_name)
        except PyMongoError as e:
            logger.exception("MongoDB connection error")
            raise WorkflowsDBError(str(e)) from e

    def _ensure_indexes(self) -> None:
        try:
            self.col.create_index(
                [("header.workflow_uri", ASCENDING)],
                unique=True,
                name="idx_workflow_uri",
            )
        except PyMongoError as e:
            logger.warning("Index creation failed: %s", e)

    # ---------- Converters ----------

    def _wf_to_doc(self, wf: "Workflow") -> Dict[str, Any]:
        doc = wf.to_dict()
        doc["_id"] = wf.header.workflow_uri
        return doc

    def _doc_to_wf(self, doc: Dict[str, Any]) -> "Workflow":
        payload = dict(doc)
        payload.pop("_id", None)
        payload.pop("created_at", None)
        payload.pop("updated_at", None)
        return Workflow.from_dict(payload)

    # ---------- CRUD ----------

    def create_workflow(self, wf: "Workflow") -> "Workflow":
        try:
            doc = self._wf_to_doc(wf)
            now = datetime.utcnow()
            doc["created_at"] = now
            doc["updated_at"] = now
            self.col.insert_one(doc)
            return self._doc_to_wf(doc)
        except DuplicateKeyError:
            raise WorkflowsDBError(
                f"Workflow {wf.header.workflow_uri} already exists"
            )
        except PyMongoError as e:
            raise WorkflowsDBError(str(e)) from e

    def get_workflow(self, workflow_uri: str) -> Optional["Workflow"]:
        try:
            doc = self.col.find_one({"_id": workflow_uri})
            return self._doc_to_wf(doc) if doc else None
        except PyMongoError as e:
            raise WorkflowsDBError(str(e)) from e

    def replace_workflow(
        self, workflow_uri: str, wf: "Workflow"
    ) -> Optional["Workflow"]:
        try:
            wf.header.workflow_uri = workflow_uri
            doc = self._wf_to_doc(wf)
            doc["updated_at"] = datetime.utcnow()

            old = self.col.find_one(
                {"_id": workflow_uri}, projection={"created_at": 1}
            )
            doc["created_at"] = (
                old.get("created_at") if old else doc["updated_at"]
            )

            res = self.col.find_one_and_replace(
                {"_id": workflow_uri},
                doc,
                return_document=ReturnDocument.AFTER,
            )

            return self._doc_to_wf(res) if res else None
        except PyMongoError as e:
            raise WorkflowsDBError(str(e)) from e

    def update_workflow_fields(
        self,
        workflow_uri: str,
        update_fields: Dict[str, Any],
    ) -> Optional["Workflow"]:
        try:
            update = {"$set": dict(update_fields)}
            update["$set"]["updated_at"] = datetime.utcnow()

            res = self.col.find_one_and_update(
                {"_id": workflow_uri},
                update,
                return_document=ReturnDocument.AFTER,
            )

            return self._doc_to_wf(res) if res else None
        except PyMongoError as e:
            raise WorkflowsDBError(str(e)) from e

    def delete_workflow(self, workflow_uri: str) -> bool:
        try:
            res = self.col.delete_one({"_id": workflow_uri})
            return res.deleted_count > 0
        except PyMongoError as e:
            raise WorkflowsDBError(str(e)) from e

    def list_workflows(
        self,
        *,
        limit: int = 50,
        skip: int = 0,
    ) -> List["Workflow"]:
        try:
            cursor = self.col.find({}).skip(skip).limit(limit)
            return [self._doc_to_wf(doc) for doc in cursor]
        except PyMongoError as e:
            raise WorkflowsDBError(str(e)) from e

    def query_workflows(
        self,
        query: Dict[str, Any],
        *,
        projection: Optional[Dict[str, int]] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List["Workflow"]:
        try:
            cursor = self.col.find(query, projection=projection or {})
            if sort:
                cursor = cursor.sort(sort)
            if skip:
                cursor = cursor.skip(skip)
            if limit:
                cursor = cursor.limit(limit)
            return [self._doc_to_wf(doc) for doc in cursor]
        except PyMongoError as e:
            raise WorkflowsDBError(str(e)) from e


class RuntimeWorkflowsDBError(Exception):
    pass


class RuntimeWorkflowsDB:

    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        db_name: str = "workflows_db",
        collection_name: str = "runtime_workflows",
    ):
        mongo_uri = mongo_uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")

        try:
            self.client = MongoClient(mongo_uri)
            self.db = self.client[db_name]
            self.col = self.db[collection_name]
            self._ensure_indexes()
        except PyMongoError as e:
            raise RuntimeWorkflowsDBError(str(e)) from e

    def _ensure_indexes(self) -> None:
        try:
            self.col.create_index(
                [("workflow_uri", ASCENDING)],
                name="idx_workflow_uri",
            )
            self.col.create_index(
                [("cluster_id", ASCENDING)],
                name="idx_cluster_id",
            )
        except PyMongoError:
            pass

    # ---------- Converters ----------

    def _rt_to_doc(self, rt: "RuntimeWorkflow") -> Dict[str, Any]:
        doc = rt.to_dict()
        doc["_id"] = rt.id
        return doc

    def _doc_to_rt(self, doc: Dict[str, Any]) -> "RuntimeWorkflow":
        payload = dict(doc)
        payload.pop("_id", None)
        payload.pop("created_at", None)
        payload.pop("updated_at", None)
        return RuntimeWorkflow.from_dict(payload)

    # ---------- CRUD ----------

    def create_runtime(self, rt: "RuntimeWorkflow") -> "RuntimeWorkflow":
        try:
            doc = self._rt_to_doc(rt)
            now = datetime.utcnow()
            doc["created_at"] = now
            doc["updated_at"] = now
            self.col.insert_one(doc)
            return self._doc_to_rt(doc)
        except DuplicateKeyError:
            raise RuntimeWorkflowsDBError(
                f"RuntimeWorkflow {rt.id} already exists"
            )
        except PyMongoError as e:
            raise RuntimeWorkflowsDBError(str(e)) from e

    def get_runtime(self, runtime_id: str) -> Optional["RuntimeWorkflow"]:
        try:
            doc = self.col.find_one({"_id": runtime_id})
            return self._doc_to_rt(doc) if doc else None
        except PyMongoError as e:
            raise RuntimeWorkflowsDBError(str(e)) from e

    def delete_runtime(self, runtime_id: str) -> bool:
        try:
            res = self.col.delete_one({"_id": runtime_id})
            return res.deleted_count > 0
        except PyMongoError as e:
            raise RuntimeWorkflowsDBError(str(e)) from e

    def list_runtimes(
        self,
        *,
        workflow_uri: Optional[str] = None,
        cluster_id: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List["RuntimeWorkflow"]:
        try:
            query: Dict[str, Any] = {}
            if workflow_uri:
                query["workflow_uri"] = workflow_uri
            if cluster_id:
                query["cluster_id"] = cluster_id

            cursor = self.col.find(query).skip(skip).limit(limit)
            return [self._doc_to_rt(doc) for doc in cursor]
        except PyMongoError as e:
            raise RuntimeWorkflowsDBError(str(e)) from e