from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Literal


# ---------- Core ----------
@dataclass
class SubjectVersion:
    version: str
    release_tag: str


@dataclass
class OwnerInfo:
    org_id: Optional[str] = None
    org_name: Optional[str] = None
    team: Optional[str] = None
    owners: List[str] = field(default_factory=list)         # emails/user IDs
    contacts: Dict[str, str] = field(default_factory=dict)  # {"slack":"...", "email":"..."}


@dataclass
class ResourceProfile:
    device: Literal["cpu", "gpu", "tpu"] = "cpu"
    cpu_cores: float = 1.0                # per replica
    memory_mb: int = 2048                 # per replica
    storage_mb: int = 0                   # per replica
    gpu_count: int = 0                    # per replica
    gpu_memory_mb: Optional[int] = None
    node_selector: Dict[str, str] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)


# ---------- Capability items ----------
@dataclass
class ContractItem:
    contract_type: str
    contract_id: str
    contract_parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DSLItem:
    dsl_type: str
    dsl_workflow_id: str
    dsl_parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelItem:
    llm_type: str
    llm_block_id: str
    llm_selection_query: Dict[str, Any] = field(default_factory=dict)
    llm_parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AddonItem:
    addon_type: str
    addon_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolItem:
    tool_id: str
    tool_description: str = ""
    tool_execution_mode: Literal["local", "remote"] = "local"
    tool_custom_config: Dict[str, Any] = field(default_factory=dict)
    tool_calling_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryItem:
    memory_id: str
    memory_type: str = ""
    memory_backend: str = ""
    memory_custom_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubSystemItem:
    sub_system_id: str
    sub_system_type: str = ""
    sub_system_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FunctionItem:
    function_id: str
    function_custom_parameters: Dict[str, Any] = field(default_factory=dict)
    function_calling_config: Dict[str, Any] = field(default_factory=dict)


# ---------- Grouped configs ----------
# Identity & metadata
@dataclass
class SubjectIdentity:
    subject_id: str = field(init=False)
    subject_name: str = ""
    subject_type: str = ""
    subject_version: SubjectVersion = field(
        default_factory=lambda: SubjectVersion("0.1.0", "dev")
    )


@dataclass
class SubjectMetadata:
    subject_description: str = ""
    subject_search_tags: List[str] = field(default_factory=list)
    subject_traits: List[str] = field(default_factory=list)
    subject_metadata: Dict[str, str] = field(default_factory=dict)


# Agent persona, prompting & execution policy
@dataclass
class AgentPersona:
    role: str = ""                      # function/expertise
    goal: str = ""                      # objective
    persona: str = ""                   # narrative/backstory
    default_system_message: str = ""    # default system prompt


@dataclass
class ManagementCommandItem:
    command: str
    command_description: Optional[str] = None
    input_template: Optional[str] = None
    output_template: Optional[str] = None


@dataclass
class PromptingConfig:
    default_system_template: Optional[str] = None
    input_template: Optional[str] = None
    output_template: Optional[str] = None
    prompts_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPolicy:
    logging_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    support_delegations: bool = False
    execute_code: bool = False
    # enabled memory classes like ["short-term", "long-term", "context"]
    enabled_memory_classes: List[str] = field(default_factory=list)

    def __post_init__(self):
        # Normalize/validate values once
        self.logging_level = str(self.logging_level).upper()  # type: ignore


@dataclass
class BuiltinModules:
    module_id: str = ""
    module_description: str = ""
    module_input_template: str = ""
    module_output_template: str = ""
    module_management_commands: List[ManagementCommandItem] = field(default_factory=list)


# Integrations (runtime bindings)
@dataclass
class IntegrationConfig:
    dsls: List[DSLItem] = field(default_factory=list)
    models: List[ModelItem] = field(default_factory=list)
    addons: List[AddonItem] = field(default_factory=list)
    contracts: List[ContractItem] = field(default_factory=list)
    subject_tools: List[ToolItem] = field(default_factory=list)
    subject_functions: List[FunctionItem] = field(default_factory=list)
    memory_systems: List[MemoryItem] = field(default_factory=list)
    sub_systems: List[SubSystemItem] = field(default_factory=list)
    builtin_modules: List[BuiltinModules] = field(default_factory=list)  # <— surfaced


@dataclass
class RuntimeConfig:
    resources: ResourceProfile = field(default_factory=ResourceProfile)
    management_commands: List[ManagementCommandItem] = field(default_factory=list)


# ---------- Main aggregated Subject ----------
@dataclass
class Subject:
    identity: SubjectIdentity = field(default_factory=SubjectIdentity)
    metadata: SubjectMetadata = field(default_factory=SubjectMetadata)
    persona: AgentPersona = field(default_factory=AgentPersona)
    prompting: PromptingConfig = field(default_factory=PromptingConfig)
    execution: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    integrations: IntegrationConfig = field(default_factory=IntegrationConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    owner: OwnerInfo = field(default_factory=OwnerInfo)  # governance

  
