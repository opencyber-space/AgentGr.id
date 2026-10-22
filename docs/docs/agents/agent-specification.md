# Agent Specification

This document defines the schema for describing an “Agent” (a **Subject**) — its identity, static deployment info, metadata, persona, prompting rules, execution policy, integrations (policies/tools/models/etc.), runtime resources, and governance.

The schema is implemented by the dataclasses in the subjects service (`db/core/schema.py`). Subjects are stored through the subjects API (`POST /api/subjects`, see [Creating an Agent](agent-creation.md)).

It’s designed for:

* **Declarative configuration** (files, DB rows, or APIs)
* **Deterministic execution** (stable defaults, explicit types)
* **Modularity** (drop-in capabilities and subsystems)
* **Extensibility** (safe addition of new items/sections)

---

## What this spec gives you

* **Separation of concerns**
  Identity vs. persona vs. policy vs. runtime resources vs. governance are cleanly scoped.
* **Composable capabilities**
  Tools, functions, DSLs, models, memory systems, subsystems, and addons plug in uniformly.
* **Prompting ergonomics**
  Consistent system/input/output templates and per-prompt overrides.
* **Execution safety**
  Explicit logging level, code-execution toggle, and memory-class controls.
* **Runtime portability**
  Per-replica resource profile, node selectors, and env for any orchestrator.
* **Governance & ownership**
  Contact/owner metadata kept distinct for audits and approvals.

---

## Full agent specification structure

```python
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
    addon_id: str
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


@dataclass
class SubjectStaticInfo:
    container_image_name: str = ""      # agent container image deployed for each instance
    static_env: Dict[str, Any] = field(default_factory=dict)
    static_settings: Dict[str, Any] = field(default_factory=dict)
    static_parameters: Dict[str, Any] = field(default_factory=dict)
    static_metadata: Dict[str, Any] = field(default_factory=dict)
    container_registry_info: str = ""   # string, not dict


# Agent persona, prompting & execution policy
@dataclass
class AgentPersona:
    role: str = ""                      # function/expertise
    goal: str = ""                      # objective
    persona: str = ""                   # narrative/backstory
    default_system_message: str = ""    # default system prompt
    config: dict = field(default_factory=dict)


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


@dataclass
class PolicyItem:
    policy_type: str = ""               # e.g. "rate_limiter", "load_balancer"
    policy_rule_uri: str = ""           # policy in the Policy DB
    parameters: Dict = field(default_factory=dict)
    settings: Dict = field(default_factory=dict)


# Integrations (runtime bindings)
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


@dataclass
class RuntimeConfig:
    resources: ResourceProfile = field(default_factory=ResourceProfile)
    management_commands: List[ManagementCommandItem] = field(default_factory=list)
    exchanges: List[str] = field(default_factory=list)   # job exchange IDs


# ---------- Main aggregated Subject ----------
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
    owner: OwnerInfo = field(default_factory=OwnerInfo)  # governance

```

---

## Top-Level Layout

```json
{
  "identity": { ... },
  "info": { ... },
  "metadata": { ... },
  "persona": { ... },
  "prompting": { ... },
  "execution": { ... },
  "integrations": { ... },
  "runtime": { ... },
  "owner": { ... }
}
```


Below, each section lists: **Field**, **Type**, **Required?**, **Default**, **Description**.

> **Payload rules (subjects API):**
>
> - Every section is optional, but `identity.subject_version` (with both `version` and `release_tag`) must always be present. Without it the request fails.
> - Unknown fields inside a section are rejected: the section is built with `Class(**data)`, so an unexpected key causes an error.
> - A `null` section value is not accepted; omit the section instead.

---

## 1) identity — SubjectIdentity

| Field            | Type                  | Required? | Default                                   | Description                                            |
| ---------------- | --------------------- | --------: | ----------------------------------------- | ------------------------------------------------------ |
| subject\_id      | `str` (set post-init) |        No | —                                         | Unique ID of the subject. If omitted on create, the subjects service assigns a MongoDB ObjectId string. Used as the agent's `SUBJECT_ID` and as the `id` of workflow agent nodes. |
| subject\_name    | `str`                 |        No | `""`                                      | Human-friendly name for the agent.                     |
| subject\_type    | `str`                 |        No | `""`                                      | Category/class (e.g., `"researcher"`, `"assistant"`).  |
| subject\_version | `SubjectVersion`      |        No | `{"version":"0.1.0","release_tag":"dev"}` | Semver + release tag for this agent build.             |

**SubjectVersion**

| Field        | Type  | Required? | Default | Description                                   |
| ------------ | ----- | --------: | ------- | --------------------------------------------- |
| version      | `str` |       Yes | —       | Semantic version (e.g., `"1.2.3"`).           |
| release\_tag | `str` |       Yes | —       | Channel or label (e.g., `"dev"`, `"stable"`). |

---

## 2) info — SubjectStaticInfo

| Field                     | Type            | Required? | Default | Description                                                                 |
| ------------------------- | --------------- | --------: | ------- | --------------------------------------------------------------------------- |
| container\_image\_name    | `str`           |        No | `""`    | Container image of the agent. The deployer runs this image for every agent instance, so it is required before deploying the agent. |
| static\_env               | `Dict[str,Any]` |        No | `{}`    | Static environment values for the agent.                                    |
| static\_settings          | `Dict[str,Any]` |        No | `{}`    | Static settings.                                                            |
| static\_parameters        | `Dict[str,Any]` |        No | `{}`    | Static parameters.                                                          |
| static\_metadata          | `Dict[str,Any]` |        No | `{}`    | Static metadata.                                                            |
| container\_registry\_info | `str`           |        No | `""`    | Registry information (a string, not an object).                             |

---

## 3) metadata — SubjectMetadata

| Field                 | Type            | Required? | Default | Description                                        |
| --------------------- | --------------- | --------: | ------- | -------------------------------------------------- |
| subject\_description  | `str`           |        No | `""`    | Narrative description of the agent.                |
| subject\_search\_tags | `List[str]`     |        No | `[]`    | Searchable tags for discovery.                     |
| subject\_traits       | `List[str]`     |        No | `[]`    | Behavioral traits (e.g., `"concise"`, `"formal"`). |
| subject\_metadata     | `Dict[str,str]` |        No | `{}`    | Freeform key-value metadata (small strings).       |

---

## 4) persona — AgentPersona

| Field                    | Type  | Required? | Default | Description                                                 |
| ------------------------ | ----- | --------: | ------- | ----------------------------------------------------------- |
| role                     | `str` |        No | `""`    | The agent’s function/expertise.                             |
| goal                     | `str` |        No | `""`    | Primary objective guiding decisions.                        |
| persona                  | `str` |        No | `""`    | Backstory/narrative for tone and consistency.               |
| default\_system\_message | `str` |        No | `""`    | Baseline system prompt; applied when no template overrides. |
| config                   | `dict` |       No | `{}`    | Free-form persona configuration.                            |

---

## 5) prompting — PromptingConfig & ManagementCommandItem

| Field                     | Type            | Required? | Default | Description                                     |
| ------------------------- | --------------- | --------: | ------- | ----------------------------------------------- |
| default\_system\_template | `Optional[str]` |        No | `None`  | Jinja-like template for the system prompt.      |
| input\_template           | `Optional[str]` |        No | `None`  | Template for user/input formatting.             |
| output\_template          | `Optional[str]` |        No | `None`  | Template for agent outputs.                     |
| prompts\_config           | `Dict[str,Any]` |        No | `{}`    | Named prompt snippets/vars for advanced setups. |

**ManagementCommandItem** (used in `runtime.management_commands` or inside modules)

| Field                | Type            | Required? | Default | Description                                 |
| -------------------- | --------------- | --------: | ------- | ------------------------------------------- |
| command              | `str`           |       Yes | —       | Command name (e.g., `"reset"`, `"warmup"`). |
| command\_description | `Optional[str]` |        No | `None`  | Human-friendly description.                 |
| input\_template      | `Optional[str]` |        No | `None`  | Template for command input.                 |
| output\_template     | `Optional[str]` |        No | `None`  | Template for command output.                |

---

## 6) execution — ExecutionPolicy

| Field                    | Type                                                      | Required? | Default  | Description                                                                    |
| ------------------------ | --------------------------------------------------------- | --------: | -------- | ------------------------------------------------------------------------------ |
| logging\_level           | `"CRITICAL" \| "ERROR" \| "WARNING" \| "INFO" \| "DEBUG"` |        No | `"INFO"` | Runtime log verbosity.                                                         |
| support\_delegations     | `bool`                                                    |        No | `False`  | Allow the agent to delegate tasks to other agents/tools.                       |
| execute\_code            | `bool`                                                    |        No | `False`  | Permit code execution (use cautiously).                                        |
| enabled\_memory\_classes | `List[str]`                                               |        No | `[]`     | Memory tiers the agent may use (e.g., `["short-term","long-term","context"]`). |

---

## 7) integrations — IntegrationConfig

This is the “plug-in board” for capabilities.

| Field              | Type                   | Required? | Default | Description                                               |
| ------------------ | ---------------------- | --------: | ------- | --------------------------------------------------------- |
| policies           | `List[PolicyItem]`     |        No | `[]`    | Policies used by the agent executor (pre-check, rate limit, backlog, load balancing, autoscaling). |
| dsls               | `List[DSLItem]`        |        No | `[]`    | Registered DSL workflows.                                 |
| models             | `List[ModelItem]`      |        No | `[]`    | Model/LLM backends and parameters.                        |
| addons             | `List[AddonItem]`      |        No | `[]`    | Sidecar features (analytics, guards, etc.).               |
| contracts          | `List[ContractItem]`   |        No | `[]`    | Contract modules and parameters.                          |
| subject\_tools     | `List[ToolItem]`       |        No | `[]`    | Tools the agent can call (local/remote).                  |
| subject\_functions | `List[FunctionItem]`   |        No | `[]`    | Functions callable by the agent (strong typing optional). |
| memory\_systems    | `List[MemoryItem]`     |        No | `[]`    | Memory providers (vector DBs, caches).                    |
| sub\_systems       | `List[SubSystemItem]`  |        No | `[]`    | External subsystems (routing, evaluators, schedulers).    |
| builtin\_modules   | `List[BuiltinModules]` |        No | `[]`    | First-class modules shipped with the platform.            |

**PolicyItem**

| Field             | Type   | Required? | Default | Description                                                    |
| ----------------- | ------ | --------: | ------- | -------------------------------------------------------------- |
| policy\_type      | `str`  |        No | `""`    | Which executor hook the policy plugs into (see below).         |
| policy\_rule\_uri | `str`  |        No | `""`    | URI of the policy in the Policy DB.                            |
| parameters        | `Dict` |        No | `{}`    | Policy parameters.                                             |
| settings          | `Dict` |        No | `{}`    | Policy settings.                                               |

The agent executor looks up these `policy_type` values (the first matching policy is used). A hook with no policy uses its built-in default.

| `policy_type`        | Used by the executor for                                  |
| -------------------- | --------------------------------------------------------- |
| `message_prechecker` | Accept/reject incoming tasks                              |
| `rate_limiter`       | Per-session rate limiting                                 |
| `message_backlog`    | Deciding whether to backlog a task                        |
| `load_balancer`      | Choosing which agent instance receives a task             |
| `autoscaler`         | Scaling agent instances up or down                        |

**DSLItem**

| Field             | Type            | Required? | Default | Description                     |
| ----------------- | --------------- | --------: | ------- | ------------------------------- |
| dsl\_type         | `str`           |       Yes | —       | E.g., `"graph"`, `"dag"`.       |
| dsl\_workflow\_id | `str`           |       Yes | —       | Registry/workflow identifier.   |
| dsl\_parameters   | `Dict[str,Any]` |        No | `{}`    | Runtime parameters / overrides. |

**ModelItem**

| Field                 | Type            | Required? | Default | Description                                   |
| --------------------- | --------------- | --------: | ------- | --------------------------------------------- |
| llm\_type             | `str`           |       Yes | —       | Model family/type (`"hf"`, `"openai"`, etc.). |
| llm\_block\_id        | `str`           |       Yes | —       | Concrete deployment or block id.              |
| llm\_selection\_query | `Dict[str,Any]` |        No | `{}`    | Query for dynamic model selection.            |
| llm\_parameters       | `Dict[str,Any]` |        No | `{}`    | Generation params (temperature, top\_p, …).   |

**AddonItem**

| Field         | Type            | Required? | Default | Description                                       |
| ------------- | --------------- | --------: | ------- | ------------------------------------------------- |
| addon\_id     | `str`           |       Yes | —       | Addon ID.                                         |
| addon\_type   | `str`           |       Yes | —       | Addon kind (e.g., `"guardrails"`, `"analytics"`). |
| addon\_config | `Dict[str,Any]` |        No | `{}`    | Configuration map.                                |

**ToolItem**

| Field                 | Type                  | Required? | Default   | Description                                       |
| --------------------- | --------------------- | --------: | --------- | ------------------------------------------------- |
| tool\_id              | `str`                 |       Yes | —         | Tool registry ID.                                 |
| tool\_description     | `str`                 |        No | `""`      | Human-readable description.                       |
| tool\_execution\_mode | `"local" \| "remote"` |        No | `"local"` | Where the tool executes.                          |
| tool\_custom\_config  | `Dict[str,Any]`       |        No | `{}`      | Tool-specific config (auth, timeouts, etc.).      |
| tool\_calling\_config | `Dict[str,Any]`       |        No | `{}`      | Function-calling schema, arg hints, safety flags. |

**FunctionItem**

| Field                        | Type            | Required? | Default | Description                         |
| ---------------------------- | --------------- | --------: | ------- | ----------------------------------- |
| function\_id                 | `str`           |       Yes | —       | Function registry ID.               |
| function\_custom\_parameters | `Dict[str,Any]` |        No | `{}`    | Input defaults/overrides.           |
| function\_calling\_config    | `Dict[str,Any]` |        No | `{}`    | JSON schema / arg mapping / safety. |

**MemoryItem**

| Field                  | Type            | Required? | Default | Description                                         |
| ---------------------- | --------------- | --------: | ------- | --------------------------------------------------- |
| memory\_id             | `str`           |       Yes | —       | Memory system ID.                                   |
| memory\_type           | `str`           |        No | `""`    | Logical type (`"short-term"`, `"long-term"`, etc.). |
| memory\_backend        | `str`           |        No | `""`    | Engine/driver (e.g., `"weaviate"`, `"redis"`).      |
| memory\_custom\_config | `Dict[str,Any]` |        No | `{}`    | Index names, TTLs, dimensions, etc.                 |

**SubSystemItem**

| Field               | Type            | Required? | Default | Description                              |
| ------------------- | --------------- | --------: | ------- | ---------------------------------------- |
| sub\_system\_id     | `str`           |       Yes | —       | Subsystem ID.                            |
| sub\_system\_type   | `str`           |        No | `""`    | Category (router, evaluator, scheduler). |
| sub\_system\_config | `Dict[str,Any]` |        No | `{}`    | Config map.                              |

**ContractItem**

| Field                | Type            | Required? | Default | Description                          |
| -------------------- | --------------- | --------: | ------- | ------------------------------------ |
| contract\_type       | `str`           |       Yes | —       | Contract class/kind.                 |
| contract\_id         | `str`           |       Yes | —       | Registry/deployment ID.              |
| contract\_parameters | `Dict[str,Any]` |        No | `{}`    | Parameters for evaluation/execution. |

**BuiltinModules**

| Field                        | Type                          | Required? | Default | Description                        |
| ---------------------------- | ----------------------------- | --------: | ------- | ---------------------------------- |
| module\_id                   | `str`                         |        No | `""`    | Built-in module ID.                |
| module\_description          | `str`                         |        No | `""`    | Description of functionality.      |
| module\_input\_template      | `str`                         |        No | `""`    | Input template for the module.     |
| module\_output\_template     | `str`                         |        No | `""`    | Output template for the module.    |
| module\_management\_commands | `List[ManagementCommandItem]` |        No | `[]`    | Module-scoped management commands. |

---

## 8) runtime — RuntimeConfig & ResourceProfile

| Field                | Type                          | Required? | Default      | Description                                       |
| -------------------- | ----------------------------- | --------: | ------------ | ------------------------------------------------- |
| resources            | `ResourceProfile`             |        No | See defaults | Per-replica compute/storage and scheduling hints. |
| management\_commands | `List[ManagementCommandItem]` |        No | `[]`         | Global management commands for this agent.        |
| exchanges            | `List[str]`                   |        No | `[]`         | Job exchange IDs the agent registers with.        |

**ResourceProfile**

| Field           | Type                      | Required? | Default | Description                            |
| --------------- | ------------------------- | --------: | ------- | -------------------------------------- |
| device          | `"cpu" \| "gpu" \| "tpu"` |        No | `"cpu"` | Execution device type.                 |
| cpu\_cores      | `float`                   |        No | `1.0`   | vCPU per replica.                      |
| memory\_mb      | `int`                     |        No | `2048`  | Memory (MB) per replica.               |
| storage\_mb     | `int`                     |        No | `0`     | Ephemeral/storage (MB) per replica.    |
| gpu\_count      | `int`                     |        No | `0`     | GPUs per replica.                      |
| gpu\_memory\_mb | `Optional[int]`           |        No | `None`  | GPU memory hint (MB).                  |
| node\_selector  | `Dict[str,str]`           |        No | `{}`    | Scheduler affinity hints (labels).     |
| env             | `Dict[str,str]`           |        No | `{}`    | Environment variables for the process. |

---

## 9) owner — OwnerInfo (Governance)

| Field     | Type            | Required? | Default | Description                                    |
| --------- | --------------- | --------: | ------- | ---------------------------------------------- |
| org\_id   | `Optional[str]` |        No | `None`  | Organization ID.                               |
| org\_name | `Optional[str]` |        No | `None`  | Organization name.                             |
| team      | `Optional[str]` |        No | `None`  | Team name/slug.                                |
| owners    | `List[str]`     |        No | `[]`    | Owner user IDs/emails.                         |
| contacts  | `Dict[str,str]` |        No | `{}`    | Contact channels (e.g., `"slack"`, `"email"`). |

---

## Minimal JSON Example

```json
{
  "identity": {
    "subject_name": "Policy Researcher",
    "subject_type": "researcher",
    "subject_version": { "version": "1.0.0", "release_tag": "stable" }
  },
  "info": {
    "container_image_name": "registry.example.org/agents/policy-researcher:latest"
  },
  "metadata": {
    "subject_description": "Analyzes policy proposals and drafts briefs",
    "subject_search_tags": ["policy", "analysis"],
    "subject_traits": ["concise", "evidence-driven"]
  },
  "persona": {
    "role": "Policy Analyst",
    "goal": "Summarize and critique policy drafts",
    "persona": "Pragmatic, neutral, cites sources",
    "default_system_message": "Answer with citations and balanced tone."
  },
  "prompting": {
    "default_system_template": "You are {{role}}. Goal: {{goal}}.",
    "prompts_config": { "citation_style": "APA" }
  },
  "execution": {
    "logging_level": "INFO",
    "support_delegations": true,
    "execute_code": false,
    "enabled_memory_classes": ["short-term", "context"]
  },
  "integrations": {
    "policies": [
      { "policy_type": "rate_limiter", "policy_rule_uri": "policies/rate-limiter:1.0-stable", "parameters": { "max_requests_per_minute": 60 } }
    ],
    "models": [
      { "llm_type": "hf", "llm_block_id": "llama3-70b", "llm_parameters": {"temperature": 0.2} }
    ],
    "subject_tools": [
      { "tool_id": "web-search", "tool_execution_mode": "remote" }
    ],
    "memory_systems": [
      { "memory_id": "weaviate-prod", "memory_backend": "weaviate" }
    ]
  },
  "runtime": {
    "resources": { "device": "gpu", "gpu_count": 1, "memory_mb": 8192 },
    "management_commands": [
      { "command": "warmup", "command_description": "Prime caches" }
    ]
  },
  "owner": {
    "org_name": "ExampleOrg",
    "owners": ["owner@example.org"],
    "contacts": {"slack":"#agents","email":"owner@example.org"}
  }
}
```

---

