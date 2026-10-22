# subjects_db.py
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from bson import ObjectId
from pymongo import MongoClient, ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError



from .schema import Subject, RuntimeSubject, AgentDeployer

logger = logging.getLogger("subjects.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


def _now_utc() -> datetime:
    return datetime.utcnow()


def _coerce_subject_id(subject_id: Optional[str]) -> str:
    
    return subject_id or str(ObjectId())


def _clean_dict(d: Dict[str, Any]) -> Dict[str, Any]:    
    if not isinstance(d, dict):
        return d
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            v2 = _clean_dict(v)
            if v2 or v2 == {}:
                out[k] = v2
        elif isinstance(v, list):
            out[k] = [(_clean_dict(i) if isinstance(i, dict) else i) for i in v]
        else:
            if v is not None:
                out[k] = v
    return out


class SubjectsDBError(Exception):
    pass


class RuntimeSubjectsDBError(Exception):
    pass


class AgentDeployersDBError(Exception):
    pass

class SubjectsDB:
   

    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        db_name: str = "subjects_db",
        collection_name: str = "subjects",
        *,
        connect_timeout_ms: int = 10000,
        server_selection_timeout_ms: int = 10000,
        appname: str = "subjects-db-client",
    ):
        mongo_uri = mongo_uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        try:
            self.client = MongoClient(
                mongo_uri,
                appname=appname,
                connectTimeoutMS=connect_timeout_ms,
                serverSelectionTimeoutMS=server_selection_timeout_ms,
                uuidRepresentation="standard",
            )
            self.db = self.client[db_name]
            self.col = self.db[collection_name]
            self._ensure_indexes()
            logger.info("Connected to MongoDB %s/%s", db_name, collection_name)
        except PyMongoError as e:
            logger.exception("MongoDB connection error")
            raise SubjectsDBError(f"MongoDB connection error: {e}") from e

    # ---------- Indexes ----------
    def _ensure_indexes(self) -> None:
        """
        Ensures we have the right indexes. _id is unique by default.
        """
        try:
            # Useful filters: identity.subject_type, metadata.subject_search_tags
            self.col.create_index([("identity.subject_type", ASCENDING)], name="idx_subject_type")
            self.col.create_index([("metadata.subject_search_tags", ASCENDING)], name="idx_subject_tags")
            # Optional text index on name/description/tags if you want text search:
            # self.col.create_index(
            #     [("identity.subject_name", "text"), ("metadata.subject_description", "text"), ("metadata.subject_search_tags", "text")],
            #     name="idx_text",
            # )
        except PyMongoError as e:
            logger.warning("Failed to create indexes: %s", e)

    # ---------- Serialization helpers ----------
    def _subject_to_doc(self, subject: "Subject") -> Dict[str, Any]:
     
        sid = _coerce_subject_id(getattr(subject.identity, "subject_id", None))
        subject.identity.subject_id = sid

        doc = subject.to_dict()
        doc = _clean_dict(doc)
        doc["_id"] = sid
        return doc

    def _doc_to_subject(self, doc: Dict[str, Any]) -> "Subject":
        """
        Convert Mongo doc back to Subject dataclass.
        """
        # The payload in DB is the Subject fields at root + metadata like _id/created_at/updated_at.
        # We'll strip known meta fields before rehydrating.
        payload = dict(doc)
        payload.pop("_id", None)           # mirror of identity.subject_id
        payload.pop("created_at", None)
        payload.pop("updated_at", None)
        return Subject.from_dict(payload)
    
    def _doc_to_rs(self, doc: Dict[str, Any]) -> RuntimeSubject:
        payload = dict(doc)
        payload.pop("_id", None)
        payload.pop("created_at", None)
        payload.pop("updated_at", None)
        return Subject.from_dict(payload)

    # ---------- CRUD ----------
    def create_subject(self, subject: "Subject") -> "Subject":
        
        try:
            doc = self._subject_to_doc(subject)
            now = _now_utc()
            doc["created_at"] = now
            doc["updated_at"] = now
            self.col.insert_one(doc)
            logger.info("Created subject id=%s", doc["_id"])
            return self._doc_to_subject(doc)
        except DuplicateKeyError:
            sid = getattr(subject.identity, "subject_id", None)
            logger.exception("Subject already exists id=%s", sid)
            raise SubjectsDBError(f"Subject already exists: {sid}")
        except PyMongoError as e:
            logger.exception("Failed to create subject")
            raise SubjectsDBError(f"Failed to create subject: {e}") from e

    def upsert_subject(self, subject: "Subject") -> "Subject":
        
        try:
            doc = self._subject_to_doc(subject)
            doc["updated_at"] = _now_utc()
            existing = self.col.find_one({"_id": doc["_id"]})
            if not existing:
                doc["created_at"] = doc["updated_at"]
            result = self.col.find_one_and_replace(
                {"_id": doc["_id"]},
                doc,
                upsert=True,
                return_document=ReturnDocument.AFTER
            )
            logger.info("Upserted subject id=%s (created=%s)", doc["_id"], str(not bool(existing)))
            return self._doc_to_subject(result)
        except PyMongoError as e:
            logger.exception("Failed to upsert subject")
            raise SubjectsDBError(f"Failed to upsert subject: {e}") from e

    def get_subject(self, subject_id: str) -> Optional["Subject"]:
        try:
            doc = self.col.find_one({"_id": subject_id})
            if not doc:
                return None
            return self._doc_to_subject(doc)
        except PyMongoError as e:
            logger.exception("Failed to fetch subject id=%s", subject_id)
            raise SubjectsDBError(f"Failed to fetch subject: {e}") from e

    def replace_subject(self, subject_id: str, subject: "Subject") -> Optional["Subject"]:
        
        try:
            # force the target id
            subject.identity.subject_id = subject_id
            new_doc = self._subject_to_doc(subject)
            new_doc["updated_at"] = _now_utc()
            # preserve original created_at if exists
            old = self.col.find_one({"_id": subject_id}, projection={"created_at": 1})
            if old and "created_at" in old:
                new_doc["created_at"] = old["created_at"]
            else:
                new_doc["created_at"] = new_doc["updated_at"]

            doc = self.col.find_one_and_replace(
                {"_id": subject_id},
                new_doc,
                upsert=False,
                return_document=ReturnDocument.AFTER
            )
            if not doc:
                return None
            logger.info("Replaced subject id=%s", subject_id)
            return self._doc_to_subject(doc)
        except PyMongoError as e:
            logger.exception("Failed to replace subject id=%s", subject_id)
            raise SubjectsDBError(f"Failed to replace subject: {e}") from e

    def update_subject_fields(self, subject_id: str, update_fields: Dict[str, Any]) -> Optional["Subject"]:
     
        try:
            if not update_fields:
                return self.get_subject(subject_id)

            update = {"$set": dict(update_fields)}
            update["$set"]["updated_at"] = _now_utc()

            doc = self.col.find_one_and_update(
                {"_id": subject_id},
                update,
                return_document=ReturnDocument.AFTER
            )
            if not doc:
                return None
            logger.info("Updated subject id=%s fields=%s", subject_id, list(update_fields.keys()))
            return self._doc_to_subject(doc)
        except PyMongoError as e:
            logger.exception("Failed to update subject id=%s", subject_id)
            raise SubjectsDBError(f"Failed to update subject: {e}") from e

    def delete_subject(self, subject_id: str) -> bool:
        try:
            res = self.col.delete_one({"_id": subject_id})
            ok = res.deleted_count > 0
            logger.info("Deleted subject id=%s -> %s", subject_id, ok)
            return ok
        except PyMongoError as e:
            logger.exception("Failed to delete subject id=%s", subject_id)
            raise SubjectsDBError(f"Failed to delete subject: {e}") from e

    # ---------- Listing & Search ----------

    def query_subjects(
        self,
        query: Dict[str, Any],
        *,
        projection: Optional[Dict[str, int]] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List[RuntimeSubject]:
       
        try:
            cursor = self.col.find(query, projection=projection or {})
            if sort:
                cursor = cursor.sort(sort)
            if skip:
                cursor = cursor.skip(skip)
            if limit:
                cursor = cursor.limit(limit)
            return [self._doc_to_rs(doc) for doc in cursor]
        except PyMongoError as e:
            logger.exception("Generic query (runtime_subjects) failed: %s", e)
            raise RuntimeSubjectsDBError(f"Failed query: {e}") from e


    def list_subjects(
        self,
        *,
        subject_type: Optional[str] = None,
        search_tags_any: Optional[Iterable[str]] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List["Subject"]:
        """
        Basic listing with optional filters.
        - subject_type: exact match on identity.subject_type
        - search_tags_any: any tag in metadata.subject_search_tags
        """
        try:
            query: Dict[str, Any] = {}
            if subject_type:
                query["identity.subject_type"] = subject_type
            if search_tags_any:
                query["metadata.subject_search_tags"] = {"$in": list(search_tags_any)}

            cursor = self.col.find(query).skip(max(0, int(skip))).limit(max(0, int(limit)))
            out: List["Subject"] = []
            for doc in cursor:
                out.append(self._doc_to_subject(doc))
            return out
        except PyMongoError as e:
            logger.exception("Failed to list subjects")
            raise SubjectsDBError(f"Failed to list subjects: {e}") from e

    def search_by_text(
        self,
        text: str,
        *,
        limit: int = 50,
        skip: int = 0,
        fields: Optional[List[str]] = None,
    ) -> List["Subject"]:
      
        try:
            fields = fields or ["identity.subject_name", "metadata.subject_description"]
            regex_any = {"$regex": text, "$options": "i"}
            query = {"$or": [{f: regex_any for f in fields}]}
            cursor = self.col.find(query).skip(max(0, int(skip))).limit(max(0, int(limit)))
            return [self._doc_to_subject(doc) for doc in cursor]
        except PyMongoError as e:
            logger.exception("Failed regex search")
            raise SubjectsDBError(f"Failed search: {e}") from e

    def subject_exists(self, subject_id: str) -> bool:
        try:
            return self.col.count_documents({"_id": subject_id}, limit=1) == 1
        except PyMongoError as e:
            logger.exception("Failed exists check id=%s", subject_id)
            raise SubjectsDBError(f"Failed exists check: {e}") from e


class RuntimeSubjectsDB:
    """
    MongoDB-backed repository for RuntimeSubject.

    - Primary key: runtime_subject_id (also mirrored to _id)
    - Secondary keys: subject_id, runtime_status
    - Audit fields: created_at, updated_at (UTC)
    """

    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        db_name: str = "subjects_db",
        collection_name: str = "runtime_subjects",
        *,
        connect_timeout_ms: int = 10000,
        server_selection_timeout_ms: int = 10000,
        appname: str = "runtime-subjects-db-client",
    ):
        mongo_uri = mongo_uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        try:
            self.client = MongoClient(
                mongo_uri,
                appname=appname,
                connectTimeoutMS=connect_timeout_ms,
                serverSelectionTimeoutMS=server_selection_timeout_ms,
                uuidRepresentation="standard",
            )
            self.db = self.client[db_name]
            self.col = self.db[collection_name]
            self._ensure_indexes()
            logger.info("Connected to MongoDB %s/%s", db_name, collection_name)
        except PyMongoError as e:
            logger.exception("MongoDB connection error")
            raise RuntimeSubjectsDBError(f"MongoDB connection error: {e}") from e

    def _ensure_indexes(self) -> None:
        try:
            self.col.create_index([("subject_id", ASCENDING)], name="idx_subject_id")
            self.col.create_index([("runtime_status", ASCENDING)], name="idx_runtime_status")
            # For quick lookups by (subject_id, status)
            self.col.create_index(
                [("subject_id", ASCENDING), ("runtime_status", ASCENDING)],
                name="idx_subject_status",
            )
        except PyMongoError as e:
            logger.warning("Failed to create indexes: %s", e)

    # --------- Serialization ---------
    def _rs_to_doc(self, rs: RuntimeSubject) -> Dict[str, Any]:
        doc = _clean_dict(rs.to_dict())
        doc["_id"] = rs.runtime_subject_id  # mirror primary key
        return doc

    def _doc_to_rs(self, doc: Dict[str, Any]) -> RuntimeSubject:
        payload = dict(doc)
        payload.pop("_id", None)
        payload.pop("created_at", None)
        payload.pop("updated_at", None)
        return RuntimeSubject.from_dict(payload)

    # -------------- CRUD --------------
    def create_runtime_subject(self, rs: RuntimeSubject) -> RuntimeSubject:
        try:
            if not rs.runtime_subject_id:
                raise RuntimeSubjectsDBError("runtime_subject_id must be provided")
            doc = self._rs_to_doc(rs)
            now = _now_utc()
            doc["created_at"] = now
            doc["updated_at"] = now
            self.col.insert_one(doc)
            logger.info("Created runtime_subject id=%s subject_id=%s", rs.runtime_subject_id, rs.subject_id)
            return self._doc_to_rs(doc)
        except DuplicateKeyError:
            logger.exception("RuntimeSubject already exists id=%s", rs.runtime_subject_id)
            raise RuntimeSubjectsDBError(f"RuntimeSubject already exists: {rs.runtime_subject_id}")
        except PyMongoError as e:
            logger.exception("Failed to create runtime_subject")
            raise RuntimeSubjectsDBError(f"Failed to create runtime_subject: {e}") from e

    def upsert_runtime_subject(self, rs: RuntimeSubject) -> RuntimeSubject:
        try:
            if not rs.runtime_subject_id:
                raise RuntimeSubjectsDBError("runtime_subject_id must be provided")
            doc = self._rs_to_doc(rs)
            doc["updated_at"] = _now_utc()
            existing = self.col.find_one({"_id": doc["_id"]})
            if not existing:
                doc["created_at"] = doc["updated_at"]
            result = self.col.find_one_and_replace(
                {"_id": doc["_id"]},
                doc,
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            logger.info(
                "Upserted runtime_subject id=%s (created=%s)",
                rs.runtime_subject_id,
                str(not bool(existing)),
            )
            return self._doc_to_rs(result)
        except PyMongoError as e:
            logger.exception("Failed to upsert runtime_subject")
            raise RuntimeSubjectsDBError(f"Failed to upsert runtime_subject: {e}") from e

    def get_runtime_subject(self, runtime_subject_id: str) -> Optional[RuntimeSubject]:
        try:
            doc = self.col.find_one({"_id": runtime_subject_id})
            return self._doc_to_rs(doc) if doc else None
        except PyMongoError as e:
            logger.exception("Failed to fetch runtime_subject id=%s", runtime_subject_id)
            raise RuntimeSubjectsDBError(f"Failed to fetch runtime_subject: {e}") from e

    def replace_runtime_subject(self, runtime_subject_id: str, rs: RuntimeSubject) -> Optional[RuntimeSubject]:
        try:
            if not rs.runtime_subject_id:
                rs.runtime_subject_id = runtime_subject_id
            elif rs.runtime_subject_id != runtime_subject_id:
                # Keep behavior strict & predictable
                raise RuntimeSubjectsDBError("ID mismatch between argument and object")

            new_doc = self._rs_to_doc(rs)
            new_doc["updated_at"] = _now_utc()
            old = self.col.find_one({"_id": runtime_subject_id}, projection={"created_at": 1})
            new_doc["created_at"] = (old or {}).get("created_at", new_doc["updated_at"])

            doc = self.col.find_one_and_replace(
                {"_id": runtime_subject_id},
                new_doc,
                upsert=False,
                return_document=ReturnDocument.AFTER,
            )
            if not doc:
                return None
            logger.info("Replaced runtime_subject id=%s", runtime_subject_id)
            return self._doc_to_rs(doc)
        except PyMongoError as e:
            logger.exception("Failed to replace runtime_subject id=%s", runtime_subject_id)
            raise RuntimeSubjectsDBError(f"Failed to replace runtime_subject: {e}") from e

    def update_runtime_subject_fields(self, runtime_subject_id: str, update_fields: Dict[str, Any]) -> Optional[RuntimeSubject]:
        """
        Partial update using dot-notation fields.
        Examples:
          {"runtime_status": "running"}
          {"runtime_info.last_heartbeat": 1726200000, "runtime_info.node": "node-3"}
        """
        try:
            if not update_fields:
                return self.get_runtime_subject(runtime_subject_id)

            update = {"$set": dict(update_fields)}
            update["$set"]["updated_at"] = _now_utc()

            doc = self.col.find_one_and_update(
                {"_id": runtime_subject_id},
                update,
                return_document=ReturnDocument.AFTER,
            )
            if not doc:
                return None
            logger.info("Updated runtime_subject id=%s fields=%s", runtime_subject_id, list(update_fields.keys()))
            return self._doc_to_rs(doc)
        except PyMongoError as e:
            logger.exception("Failed to update runtime_subject id=%s", runtime_subject_id)
            raise RuntimeSubjectsDBError(f"Failed to update runtime_subject: {e}") from e

    def delete_runtime_subject(self, runtime_subject_id: str) -> bool:
        try:
            res = self.col.delete_one({"_id": runtime_subject_id})
            ok = res.deleted_count > 0
            logger.info("Deleted runtime_subject id=%s -> %s", runtime_subject_id, ok)
            return ok
        except PyMongoError as e:
            logger.exception("Failed to delete runtime_subject id=%s", runtime_subject_id)
            raise RuntimeSubjectsDBError(f"Failed to delete runtime_subject: {e}") from e

    # -------------- Listing & Query --------------
    def list_runtime_subjects(
        self,
        *,
        subject_id: Optional[str] = None,
        runtime_status: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[RuntimeSubject]:
        """
        Basic listing with filters on subject_id & runtime_status.
        """
        try:
            query: Dict[str, Any] = {}
            if subject_id:
                query["subject_id"] = subject_id
            if runtime_status:
                query["runtime_status"] = runtime_status

            cursor = self.col.find(query)
            if sort:
                cursor = cursor.sort(sort)
            if skip:
                cursor = cursor.skip(skip)
            if limit:
                cursor = cursor.limit(limit)

            return [self._doc_to_rs(doc) for doc in cursor]
        except PyMongoError as e:
            logger.exception("Failed to list runtime_subjects")
            raise RuntimeSubjectsDBError(f"Failed to list runtime_subjects: {e}") from e

    def query_runtime_subjects(
        self,
        query: Dict[str, Any],
        *,
        projection: Optional[Dict[str, int]] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List[RuntimeSubject]:
        """
        Execute a raw MongoDB query dict for runtime_subjects.
        """
        try:
            cursor = self.col.find(query, projection=projection or {})
            if sort:
                cursor = cursor.sort(sort)
            if skip:
                cursor = cursor.skip(skip)
            if limit:
                cursor = cursor.limit(limit)
            return [self._doc_to_rs(doc) for doc in cursor]
        except PyMongoError as e:
            logger.exception("Generic query (runtime_subjects) failed: %s", e)
            raise RuntimeSubjectsDBError(f"Failed query: {e}") from e

    # -------------- Utilities --------------
    def runtime_subject_exists(self, runtime_subject_id: str) -> bool:
        try:
            return self.col.count_documents({"_id": runtime_subject_id}, limit=1) == 1
        except PyMongoError as e:
            logger.exception("Failed exists check id=%s", runtime_subject_id)
            raise RuntimeSubjectsDBError(f"Failed exists check: {e}") from e

    def count_by_status(self, *, subject_id: Optional[str] = None) -> Dict[str, int]:
        
        try:
            match: Dict[str, Any] = {}
            if subject_id:
                match["subject_id"] = subject_id
            pipeline = [
                {"$match": match},
                {"$group": {"_id": "$runtime_status", "count": {"$sum": 1}}},
            ]
            out: Dict[str, int] = {}
            for item in self.col.aggregate(pipeline):
                out[str(item["_id"])] = int(item["count"])
            return out
        except PyMongoError as e:
            logger.exception("Failed to count by status")
            raise RuntimeSubjectsDBError(f"Failed to count by status: {e}") from e


class AgentDeployersDB:
   
    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        db_name: str = "subjects_db",
        collection_name: str = "agent_deployers",
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
            raise AgentDeployersDBError(str(e)) from e

    def _ensure_indexes(self) -> None:
        try:
            self.col.create_index([("deployer_cluster_id", ASCENDING)], name="idx_cluster_id")
        except PyMongoError as e:
            logger.warning("Index creation failed: %s", e)

    def _ad_to_doc(self, ad: "AgentDeployer") -> Dict[str, Any]:
        doc = ad.to_dict()
        doc["_id"] = ad.deployer_id
        return doc

    def _doc_to_ad(self, doc: Dict[str, Any]) -> "AgentDeployer":
        payload = dict(doc)
        payload.pop("_id", None)
        payload.pop("created_at", None)
        payload.pop("updated_at", None)
        return AgentDeployer.from_dict(payload)

    # ---------- CRUD ----------
    def create_deployer(self, ad: "AgentDeployer") -> "AgentDeployer":
        try:
            doc = self._ad_to_doc(ad)
            now = datetime.utcnow()
            doc["created_at"] = now
            doc["updated_at"] = now
            self.col.insert_one(doc)
            return self._doc_to_ad(doc)
        except DuplicateKeyError:
            raise AgentDeployersDBError(f"Deployer {ad.deployer_id} already exists")
        except PyMongoError as e:
            raise AgentDeployersDBError(str(e)) from e

    def get_deployer(self, deployer_id: str) -> Optional["AgentDeployer"]:
        try:
            doc = self.col.find_one({"_id": deployer_id})
            return self._doc_to_ad(doc) if doc else None
        except PyMongoError as e:
            raise AgentDeployersDBError(str(e)) from e

    def replace_deployer(self, deployer_id: str, ad: "AgentDeployer") -> Optional["AgentDeployer"]:
        try:
            ad.deployer_id = deployer_id
            doc = self._ad_to_doc(ad)
            doc["updated_at"] = datetime.utcnow()
            old = self.col.find_one({"_id": deployer_id}, projection={"created_at": 1})
            if old:
                doc["created_at"] = old.get("created_at")
            else:
                doc["created_at"] = doc["updated_at"]

            res = self.col.find_one_and_replace({"_id": deployer_id}, doc, return_document=ReturnDocument.AFTER)
            return self._doc_to_ad(res) if res else None
        except PyMongoError as e:
            raise AgentDeployersDBError(str(e)) from e

    def update_deployer_fields(self, deployer_id: str, update_fields: Dict[str, Any]) -> Optional["AgentDeployer"]:
        try:
            update = {"$set": dict(update_fields)}
            update["$set"]["updated_at"] = datetime.utcnow()
            res = self.col.find_one_and_update({"_id": deployer_id}, update, return_document=ReturnDocument.AFTER)
            return self._doc_to_ad(res) if res else None
        except PyMongoError as e:
            raise AgentDeployersDBError(str(e)) from e

    def delete_deployer(self, deployer_id: str) -> bool:
        try:
            res = self.col.delete_one({"_id": deployer_id})
            return res.deleted_count > 0
        except PyMongoError as e:
            raise AgentDeployersDBError(str(e)) from e

    def list_deployers(self, *, cluster_id: Optional[str] = None, limit: int = 50, skip: int = 0) -> List["AgentDeployer"]:
        try:
            query: Dict[str, Any] = {}
            if cluster_id:
                query["deployer_cluster_id"] = cluster_id
            cursor = self.col.find(query).skip(skip).limit(limit)
            return [self._doc_to_ad(doc) for doc in cursor]
        except PyMongoError as e:
            raise AgentDeployersDBError(str(e)) from e

    def query_deployers(
        self,
        query: Dict[str, Any],
        *,
        projection: Optional[Dict[str, int]] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List["AgentDeployer"]:
        try:
            cursor = self.col.find(query, projection=projection or {})
            if sort:
                cursor = cursor.sort(sort)
            if skip:
                cursor = cursor.skip(skip)
            if limit:
                cursor = cursor.limit(limit)
            return [self._doc_to_ad(doc) for doc in cursor]
        except PyMongoError as e:
            raise AgentDeployersDBError(str(e)) from e