from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Literal
from dataclasses import asdict, is_dataclass, fields

def _serialize(obj):
    if is_dataclass(obj):       
        out = {}
        for f in fields(obj):
            if not hasattr(obj, f.name):
                continue
            out[f.name] = _serialize(getattr(obj, f.name))
        return out

    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj

def _deserialize_list(data_list, cls):
    return [cls.from_dict(i) if isinstance(i, dict) else i for i in data_list or []]


# ---------- Core ----------
@dataclass
class SubjectVersion:
    version: str
    release_tag: str

    def to_dict(self) -> Dict[str, Any]:
        return {"version": self.version, "release_tag": self.release_tag}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubjectVersion":
        return cls(**data)


@dataclass
class OwnerInfo:
    org_id: Optional[str] = None
    org_name: Optional[str] = None
    team: Optional[str] = None
    owners: List[str] = field(default_factory=list)
    contacts: Dict[str, str] = field(default_factory=dict)

    def to_dict(self):
        return _serialize(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        return cls(**data)


@dataclass
class ResourceProfile:
    device: Literal["cpu", "gpu", "tpu"] = "cpu"
    cpu_cores: float = 1.0
    memory_mb: int = 2048
    storage_mb: int = 0
    gpu_count: int = 0
    gpu_memory_mb: Optional[int] = None
    node_selector: Dict[str, str] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)

    def to_dict(self):
        return _serialize(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        return cls(**data)


# ---------- Capability items ----------
@dataclass
class ContractItem:
    contract_type: str
    contract_id: str
    contract_parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self): return _serialize(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)


@dataclass
class DSLItem:
    dsl_type: str
    dsl_workflow_id: str
    dsl_parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self): return _serialize(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)


@dataclass
class ModelItem:
    llm_type: str
    llm_block_id: str
    llm_selection_query: Dict[str, Any] = field(default_factory=dict)
    llm_parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self): return _serialize(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)


@dataclass
class AddonItem:
    addon_id: str
    addon_type: str
    addon_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self): return _serialize(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)


@dataclass
class ToolItem:
    tool_id: str
    tool_description: str = ""
    tool_execution_mode: Literal["local", "remote"] = "local"
    tool_custom_config: Dict[str, Any] = field(default_factory=dict)
    tool_calling_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self): return _serialize(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)


@dataclass
class MemoryItem:
    memory_id: str
    memory_type: str = ""
    memory_backend: str = ""
    memory_custom_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self): return _serialize(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)


@dataclass
class SubSystemItem:
    sub_system_id: str
    sub_system_type: str = ""
    sub_system_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self): return _serialize(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)


@dataclass
class FunctionItem:
    function_id: str
    function_custom_parameters: Dict[str, Any] = field(default_factory=dict)
    function_calling_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self): return _serialize(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)


# ---------- Grouped configs ----------
@dataclass
class SubjectIdentity:
    subject_id: str = field(init=False)
    subject_name: str = ""
    subject_type: str = ""
    subject_version: SubjectVersion = field(
        default_factory=lambda: SubjectVersion("0.1.0", "dev")
    )

    def to_dict(self):
        return {
            "subject_id": getattr(self, "subject_id", None),
            "subject_name": self.subject_name,
            "subject_type": self.subject_type,
            "subject_version": self.subject_version.to_dict(),
        }

    @classmethod
    def from_dict(cls, data):
        sv = SubjectVersion.from_dict(data.get("subject_version", {}))
        obj = cls(
            subject_name=data.get("subject_name", ""),
            subject_type=data.get("subject_type", ""),
            subject_version=sv,
        )
        if "subject_id" in data:
            obj.subject_id = data["subject_id"]
        return obj

@dataclass
class SubjectStaticInfo:
    container_image_name: str = ''
    static_env: Dict[str, Any] = field(default_factory=dict)
    static_settings: Dict[str, Any] = field(default_factory=dict)
    static_parameters: Dict[str, Any] = field(default_factory=dict)
    static_metadata: Dict[str, Any] = field(default_factory=dict)
    container_registry_info: str = ''  # string, not dict

    def to_dict(self) -> Dict[str, Any]:
        return {
            "container_image_name": self.container_image_name,
            "static_env": self.static_env,
            "static_settings": self.static_settings,
            "static_parameters": self.static_parameters,
            "static_metadata": self.static_metadata,
            "container_registry_info": self.container_registry_info,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubjectStaticInfo":
        return cls(
            container_image_name=data.get("container_image_name", ""),
            static_env=data.get("static_env", {}) or {},
            static_settings=data.get("static_settings", {}) or {},
            static_parameters=data.get("static_parameters", {}) or {},
            static_metadata=data.get("static_metadata", {}) or {},
            container_registry_info=data.get("container_registry_info", ""),
        )


@dataclass
class SubjectMetadata:
    subject_description: str = ""
    subject_search_tags: List[str] = field(default_factory=list)
    subject_traits: List[str] = field(default_factory=list)
    subject_metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self): return _serialize(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)


@dataclass
class AgentPersona:
    role: str = ""
    goal: str = ""
    persona: str = ""
    default_system_message: str = ""
    config: Dict[str, str] = field(default_factory=dict)

    def to_dict(self): return _serialize(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)


@dataclass
class ManagementCommandItem:
    command: str
    command_description: Optional[str] = None
    input_template: Optional[str] = None
    output_template: Optional[str] = None

    def to_dict(self): return _serialize(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)


@dataclass
class PromptingConfig:
    default_system_template: Optional[str] = None
    input_template: Optional[str] = None
    output_template: Optional[str] = None
    prompts_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self): return _serialize(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)


@dataclass
class ExecutionPolicy:
    logging_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    support_delegations: bool = False
    execute_code: bool = False
    enabled_memory_classes: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.logging_level = str(self.logging_level).upper()

    def to_dict(self): return _serialize(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)


@dataclass
class BuiltinModules:
    module_id: str = ""
    module_description: str = ""
    module_input_template: str = ""
    module_output_template: str = ""
    module_management_commands: List[ManagementCommandItem] = field(default_factory=list)

    def to_dict(self):
        return {
            "module_id": self.module_id,
            "module_description": self.module_description,
            "module_input_template": self.module_input_template,
            "module_output_template": self.module_output_template,
            "module_management_commands": [m.to_dict() for m in self.module_management_commands],
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            module_id=data.get("module_id", ""),
            module_description=data.get("module_description", ""),
            module_input_template=data.get("module_input_template", ""),
            module_output_template=data.get("module_output_template", ""),
            module_management_commands=_deserialize_list(
                data.get("module_management_commands"), ManagementCommandItem
            ),
        )


@dataclass
class PolicyItem:
    policy_type: str = ""
    policy_rule_uri: str = ""
    parameters: Dict = field(default_factory=dict)
    settings: Dict = field(default_factory=dict)

    def to_dict(self): return _serialize(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)


@dataclass
class IntegrationConfig:
    policies: List[PolicyItem] = field(default_factory=list)
    dsls: List[DSLItem] = field(default_factory=list)
    models: List[ModelItem] = field(default_factory=list)
    addons: List[AddonItem] = field(default_factory=list)
    contracts: List[ContractItem] = field(default_factory=list)
    subject_tools: List[ToolItem] = field(default_factory=list)
    subject_functions: List[FunctionItem] = field(default_factory=list)
    memory_systems: List[MemoryItem] = field(default_factory=list)
    sub_systems: List[SubSystemItem] = field(default_factory=list)
    builtin_modules: List[BuiltinModules] = field(default_factory=list)

    def to_dict(self):
        return {
            "policies": [p.to_dict() for p in self.policies],
            "dsls": [d.to_dict() for d in self.dsls],
            "models": [m.to_dict() for m in self.models],
            "addons": [a.to_dict() for a in self.addons],
            "contracts": [c.to_dict() for c in self.contracts],
            "subject_tools": [t.to_dict() for t in self.subject_tools],
            "subject_functions": [f.to_dict() for f in self.subject_functions],
            "memory_systems": [m.to_dict() for m in self.memory_systems],
            "sub_systems": [s.to_dict() for s in self.sub_systems],
            "builtin_modules": [b.to_dict() for b in self.builtin_modules],
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            policies=_deserialize_list(data.get("policies"), PolicyItem),
            dsls=_deserialize_list(data.get("dsls"), DSLItem),
            models=_deserialize_list(data.get("models"), ModelItem),
            addons=_deserialize_list(data.get("addons"), AddonItem),
            contracts=_deserialize_list(data.get("contracts"), ContractItem),
            subject_tools=_deserialize_list(data.get("subject_tools"), ToolItem),
            subject_functions=_deserialize_list(data.get("subject_functions"), FunctionItem),
            memory_systems=_deserialize_list(data.get("memory_systems"), MemoryItem),
            sub_systems=_deserialize_list(data.get("sub_systems"), SubSystemItem),
            builtin_modules=_deserialize_list(data.get("builtin_modules"), BuiltinModules),
        )


@dataclass
class RuntimeConfig:
    resources: ResourceProfile = field(default_factory=ResourceProfile)
    management_commands: List[ManagementCommandItem] = field(
        default_factory=list)
    exchanges: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "resources": self.resources.to_dict(),
            "management_commands": [m.to_dict() for m in self.management_commands],
            "exchanges":  self.exchanges
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            resources=ResourceProfile.from_dict(data.get("resources", {})),
            management_commands=_deserialize_list(
                data.get("management_commands"), ManagementCommandItem),
            exchanges=data.get("exchanges", [])
        )


@dataclass
class Subject:
    identity: SubjectIdentity = field(default_factory=SubjectIdentity)
    info: SubjectStaticInfo = field(default_factory=SubjectStaticInfo)
    metadata: SubjectMetadata = field(default_factory=SubjectMetadata)
    persona: AgentPersona = field(default_factory=AgentPersona)
    prompting: PromptingConfig = field(default_factory=PromptingConfig)
    execution: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    integrations: IntegrationConfig = field(default_factory=IntegrationConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    owner: OwnerInfo = field(default_factory=OwnerInfo)

    def to_dict(self):
        return {
            "identity": self.identity.to_dict(),
            "info": self.info.to_dict(),
            "metadata": self.metadata.to_dict(),
            "persona": self.persona.to_dict(),
            "prompting": self.prompting.to_dict(),
            "execution": self.execution.to_dict(),
            "integrations": self.integrations.to_dict(),
            "runtime": self.runtime.to_dict(),
            "owner": self.owner.to_dict(),
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            identity=SubjectIdentity.from_dict(data.get("identity", {})),
            info=SubjectStaticInfo.from_dict(data.get("info", {})),
            metadata=SubjectMetadata.from_dict(data.get("metadata", {})),
            persona=AgentPersona.from_dict(data.get("persona", {})),
            prompting=PromptingConfig.from_dict(data.get("prompting", {})),
            execution=ExecutionPolicy.from_dict(data.get("execution", {})),
            integrations=IntegrationConfig.from_dict(data.get("integrations", {})),
            runtime=RuntimeConfig.from_dict(data.get("runtime", {})),
            owner=OwnerInfo.from_dict(data.get("owner", {})),
        )


@dataclass
class RuntimeSubject:
    runtime_subject_id: str
    subject_id: str
    runtime_info: Dict[str, Any] = field(default_factory=dict)
    runtime_status: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "runtime_subject_id": self.runtime_subject_id,
            "subject_id": self.subject_id,
            "runtime_info": self.runtime_info,
            "runtime_status": self.runtime_status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeSubject":
        return cls(
            runtime_subject_id=data.get("runtime_subject_id", ""),
            subject_id=data.get("subject_id", ""),
            runtime_info=data.get("runtime_info", {}) or {},
            runtime_status=data.get("runtime_status", "") or "",
        )


@dataclass
class AgentDeployer:
    deployer_id: str
    deployer_name: str
    deployer_public_url: str
    deployer_cluster_id: str
    deployer_ip: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deployer_id": self.deployer_id,
            "deployer_name": self.deployer_name,
            "deployer_public_url": self.deployer_public_url,
            "deployer_cluster_id": self.deployer_cluster_id,
            "deployer_ip": self.deployer_ip
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentDeployer":

        deployer_ip = data.get('deployer_ip')
        return cls(
            deployer_id=data.get("deployer_id", ""),
            deployer_name=data.get("deployer_name", ""),
            deployer_public_url=f"http://{deployer_ip}:30777",
            deployer_cluster_id=data.get("deployer_cluster_id", ""),
            deployer_ip=data.get('deployer_ip')
        )
