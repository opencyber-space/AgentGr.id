from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal


# -----------------------------
# Header Section
# -----------------------------

@dataclass
class WorkflowID:
    name: str
    version: str
    release: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "release": self.release,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowID":
        return cls(
            name=data.get("name", ""),
            version=data.get("version", ""),
            release=data.get("release", ""),
        )


@dataclass
class WorkflowMetadata:
    description: str
    owner: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "owner": self.owner,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowMetadata":
        return cls(
            description=data.get("description", ""),
            owner=data.get("owner", ""),
            created_at=data.get("created_at", ""),
        )


@dataclass
class WorkflowHeader:
    workflow_id: WorkflowID
    metadata: WorkflowMetadata
    workflow_uri: str = field(init=False)

    def __post_init__(self):
        self.workflow_uri = (
            f"{self.workflow_id.name}:"
            f"{self.workflow_id.version}-"
            f"{self.workflow_id.release}"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id.to_dict(),
            "workflow_uri": self.workflow_uri,
            "metadata": self.metadata.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowHeader":
        workflow_id = WorkflowID.from_dict(data.get("workflow_id", {}))
        metadata = WorkflowMetadata.from_dict(data.get("metadata", {}))
        return cls(
            workflow_id=workflow_id,
            metadata=metadata,
        )


# -----------------------------
# Node Section
# -----------------------------

@dataclass
class WorkflowNode:
    nodeID: str
    type: Literal["policy", "agent"]
    id: str
    policyType: Optional[Literal["local", "central", "function", "job"]] = None
    settings: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "nodeID": self.nodeID,
            "type": self.type,
            "id": self.id,
            "settings": self.settings,
        }

        if self.policyType is not None:
            data["policyType"] = self.policyType

        if self.parameters:
            data["parameters"] = self.parameters

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowNode":
        return cls(
            nodeID=data.get("nodeID", ""),
            type=data.get("type", "policy"),
            id=data.get("id", ""),
            policyType=data.get("policyType"),
            settings=data.get("settings", {}) or {},
            parameters=data.get("parameters", {}) or {},
        )


# -----------------------------
# Body Section
# -----------------------------

@dataclass
class WorkflowBody:
    nodes: List[WorkflowNode] = field(default_factory=list)
    graph: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "graph": self.graph,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowBody":
        return cls(
            nodes=[WorkflowNode.from_dict(n) for n in data.get("nodes", [])],
            graph=data.get("graph", {}) or {},
        )




@dataclass
class Workflow:
    header: WorkflowHeader
    body: WorkflowBody

    def to_dict(self) -> Dict[str, Any]:
        return {
            "header": self.header.to_dict(),
            "body": self.body.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Workflow":
        return cls(
            header=WorkflowHeader.from_dict(data.get("header", {})),
            body=WorkflowBody.from_dict(data.get("body", {})),
        )

@dataclass
class RuntimeWorkflow:
    id: str
    workflow_uri: str
    cluster_id: str
    deployer_id: str
    deployment_name: str
    url: str


    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workflow_uri": self.workflow_uri,
            "cluster_id": self.cluster_id,
            "deployer_id": self.deployer_id,
            "deployment_name": self.deployment_name,
            "url": self.url
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeWorkflow":
        return cls(
            id=data.get("id", ""),
            workflow_uri=data.get("workflow_uri", ""),
            cluster_id=data.get("cluster_id", ""),
            deployer_id=data.get("deployer_id", ""),
        )