# 🌐 AgentGrid: Open Agentic Web 

**AgentGrid is the third generation of agent architectures (Gen-3).**  
It subsumes strengths of **Gen-1: AI Agents** (autonomous intelligent entities) and **Gen-2: Multi-Agent Systems (MAS)** (distributed problem solvers), while overcoming their limits.  

Where Gen-1 solves as lone agent and Gen-2 organizes coordinated teams, **AgentGrid operationalizes a decentralized society of agents** like the **Internet of agents** - billions of interconnected agents that can discover each other, negotiate, form ad-hoc collaborations, exchange knowledge, and coordinate actions across open environments.  

**Key Idea:** AgentGrid is foundational infrastructure for the **Open Agentic Web** - enabling agents to pursue individual and collective goals under shared norms, policies, and guarantees. It transforms isolated agents into participants of a large, cooperative, and dynamic ecosystem that spans trust, adversarial settings, and large-scale distributed problem solving.  

---

### 🧩 A Simple Analogy

- **Gen-1 (AI Agent):** Like a **skilled individual worker** - they can perceive, decide, act, and learn, but they work mostly alone.  
- **Gen-2 (MAS):** Like a **project team** - several workers with different roles (planner, doer, verifier) coordinating through set rules to solve a shared problem.  
- **Gen-3 (AgentGrid):** Like a **Civilization** - billions of people, organizations, and services interacting freely: forming organizations, coalitions, negotiating contracts, delegating tasks, sharing knowledge, competing and collaborating at scale. No central control, yet society functions through shared norms, infrastructure, and governance.  

AgentGrid is this **Civilization for AI agents** - a digital society where diverse agents can meet, trust, collaborate, and evolve collective intelligence.  

---

🚧 **Project Status: Alpha**  
_Not production-ready. See [Project Status](#project-status) for details._

---

## 🌍 AgentGrid as a Digital Civilization

AgentGrid does everything a single agent can do: be goal driven, perceive its environment, reason, plan, decide, act through tools, and learn from feedback to pursue goals under constraints.  

It also provides everything a Multi-Agent System (MAS) can do:  
- Coordinate autonomous agents to achieve outcomes no single agent can.  
- Solve distributed problems where each agent has incomplete information, no global control, and decentralized data.  
- Organize agents into roles (planner, doer, verifier, broker), exchanging intents, proposals, and receipts.  
- Leverage composition, workflows and orchestration. 
- Collaborate by uniform protocols
- Use LLMs as agent “brains,” and tools for actuation.

But **AgentGrid goes beyond both**. It delivers what an open environment - a true *society of agents* or *Internet of Agents* demands:  


## 🌐 What AgentGrid Delivers  

AgentGrid integrates with several key projects, each contributing a unique piece of the Open Agentic Web: 

| Capability | Brief Description |
|------------|------------------|
| **🔍 Discovery** | Agents must find and recognize each other across vast, dynamic networks. |
| **📡 Communication Systems** | Decentralized communication mesh with diverse channels and messaging for rich, asynchronous, large-scale interaction. |
| **📜 Open Protocols** | Flexible, interoperable standards for any transaction — no enforced uniformity, since billion-scale ecosystems cannot rely on a single format. |
| **🔐 Trust & Identity** | Verifiable identity, reputation, and guarantees even in adversarial conditions. |
| **💱 Economy & Exchange** | Marketplaces, task exchanges, and resource-sharing infrastructures for trade, pricing, and value transfer among agents. |
| **🤝 Negotiation & Contracts** | Mechanisms to form, validate, and enforce agreements at scale. |
| **🏛️ Collective Governance** | Norms, institutions, and policy frameworks that balance autonomy with shared order. |
| **🌍 Civilizational Systems** | Meta-structures (law, culture, governance) that sustain large-scale cooperation across heterogeneous agents. |
| **🔗 Knowledge & Context Sharing** | Seamless exchange of data, context, and insights across diverse agents and environments. |
| **👥 Agency & Coalitions** | Ability for agents to join or form agencies, roles, groups, and alliances for common or competitive goals. |
| **🧭 Strategies Decision & Behavior** | Adaptive mechanisms for deliberation, decision, competition, cooperation, or divergence in complex settings. |
| **⚖️ Scalability** | Billions of heterogeneous agents interacting without central control. |



---

## 🏗️ Core Building Blocks of AgentGrid  

The **AgentGrid** is not a single system but a **constellation of key projects** that together form the foundation of the Open Agentic Web.  

The **AgentGrid** is built upon the following key projects, each contributing a unique piece of the Open Agentic Web:  

| Project        | Intuitive Brief |
|----------------|-----------------|
| 🤖 **AIOS**        | Operating system for AI & agents; runtime, orchestration, and execution environment. |
| 🛡️ **PolicyGrid**  | Trust and governance layer; aligns AI & agents with shared norms, ethics, and rules. |
| 🎮 **OpenArcade**  | Framework to shape agent populations; enables strategies for interaction, collaboration, cooperation, negotiation, and social decision-making. |
| 🔌 **ServiceGrid** | Service, tool discovery and composition; connects agents to distributed services & tools. |
| 🔐 **Xchange.id**  | Decentralized task exchange for agents & AI; routes tasks to specialist agents or agencies. |
| 🌐 **OpenMe.sh**   | Open, protocol-native communication mesh; enables signaling, message exchange, and shared context across groups, orgs, and geographies. |
| 📜 **ContractGr.id** | Contracts and agreements for AI-first society; formalizes negotiation, commitments, and enforcement. |
| 🔗 **Pervasive.Link** | Meta-protocol that binds heterogeneous systems; encodes, translates protocols, context, languages, and strategies into interoperable structures. |
| 🚉 **OpenHub.ai**  | Market hub for decentralized intelligence; backbone for sourcing, distribution, and routing of networked intelligence. |
| 🏛️ **AgencyGr.id** | Societal layer; defines roles, structures, and institutions for collective organization. |


---

## 📚 Contents

* **Getting Started**

  * [Specifying an Agent](agents/agent-specification.md)
  * [Creating an Agent](agents/agent-creation.md)
  * [Using LLMs and other AI models](agents/agent-llm-interface.md)
  * [Using Memory](agents/agent-memory.md)
  * [Managing and calling DSL Workflows](agents/agent-dsl-manager.md)
  * [Generating runtime code using Code Generator SDK](agents/agent-code-generator.md)
  * [Calling Functions and Tools](agents/agent-tools.md)
  * [Using Embedding Models](agents/agent-eembeddings.md)
  * [Accessing Graph Databases](agents/agent-graph-storage.md)
  * [Accessing Vector Databases](agents/agent-vector-storage.md)
  * [Chat and P2P Communication with other agents](agents/agent-chat-p2p.md)
  * [A2A - Agent to Agent Communication Protocol](agents/a2a.md)
  * [Accessing S3 Compatible Object Storage](agents/agent-object-storage.md)

---

* **Advanced**
  * [DSL Workflows for Agents](agents/workflows/index.md)
  * [Task Delegation, Behavior Planning, Verification](agents/agent-sub-systems.md)
  * [Association with other Agents](agents/agent-association.md)
  * [Configuration Store](agents/agent-config-store.md)
  * [Metrics](agents/agent-metrics.md)

---

* **Advanced Agent Memories**

  * [Overview](agents/advanced-memories/index.md)
  * [Agentic Memory](agents/advanced-memories/agentic-memory.md) — episodic, semantic, procedural, reflective, reward and context KV memory
  * [Agent FS](agents/advanced-memories/agent-fs.md)
  * [Learner](agents/advanced-memories/learner.md)
  * [Incorporator & Feedback](agents/advanced-memories/incorporator.md)
  * [Deployment](agents/advanced-memories/deployment.md)
  * [End-to-End Example](agents/advanced-memories/end-to-end.md)

---

* **Concepts**

  * [Agent Context Cache](agents/concepts/agent-context-cache.md)
  * [Agent LLM Interaction](agents/concepts/agent-llm-interaction.md)
  * [Agent Planning System](agents/concepts/agent-planning-system.md)
  * [Agent Task Delegation](agents/concepts/agent-task-delegation.md)
  * [Agent Verification System](agents/concepts/agent-verification-system.md)
  * [Agent Workflow Execution](agents/concepts/agent-workflow-execution.md)
  * [Behavior Controller](agents/concepts/behaviour-controller.md)
  * [Communication System](agents/concepts/communication-system.md)

---

## 🔗 Links

* 🌐 [Website](https://www.agentgr.id)
* 📄 [Vision Paper](https://resources.agentgr.id/)
* 📚 [Documentation](https://docs.agentgr.id)
* 💻 [GitHub](https://github.com/opencyber-space/AgentGr.id)

---

## 🏗 Architecture Diagrams

* 🧠 [Agent Context Cache](images/agent-context-cache.png)
* 🤖 [LLM Interface](images/ai-instance-sdk.png)
* 📌 [Task Delegation](images/delegation-agents.png)
* ✅ [Verification System Client](images/agents-verification.png)
* 🎛 [Behavior Controller Sub-System](images/behavior-controller.png)
* 📡 [Agent Communication Fanout](images/agent-communication.png)


---

## 🌟 Highlights

### 🧠 Multi-Stage Agent Planning & Reasoning

* Nested workflow driven planning system
* Mindlink support - contextually link diverse AI systems as dynamic and on-demand minds for agents.
* Dynamically creates structured, executable task graphs (`PlannerTask`s)
* Supports context-aware, memory-driven planning with MemoryGrid integration
* Uses planners to guide selection across DSLs, tools, agents, and LLMs

### 🔀 Delegation & Verification Workflows

* Assigns tasks to agents using **bidding**, **voting**, or **DSL-planned routing**
* Tracks assignment lifecycles and updates via WebSockets and DB watchers
* Supports automated and human-in-the-loop verification with real-time response handling
* Integrates constraint validation and deadline expiry logic for robust fault handling

### ⚙️ Modular Execution Engine

* Executes validated task DAGs & cyclic graphs with support for parallelism and recursion
* Dynamically dispatches to tool executors, LLMs, DSL workflows, or agent APIs
* Sandboxed code execution for runtime-generated Python logic
* Retry, fallback, and dry-run estimation modes supported

### 🧰 Registry-Driven Tool & DSL Ecosystem

* Unified registry for **tools**, **functions**, and **DSL workflows**
* Supports remote REST/gRPC-based tools and local logic executors
* Provides searchable metadata & metrics for LLM-based discoverability and selection
* Allows versioning, validation, and dynamic schema inspection

### 🧠 LLM & Optimizer Abstraction

* Backend-agnostic support for OpenAI, AIOS blocks over gRPC/REST, AIOS vDAGs, and custom backends
* Supports optimizer selection, capability estimation, and structured prompt generation
* Seamless integration with the behavior planner for intelligent flow construction

### 🔗 Real-Time State, Messaging, and Streaming

* Policy-driven, rate-limited task ingestion over HTTP and NATS, load-balanced to agent instances via Redis
* Namespace-aware context stores (in-process or Redis, with TTLs) and NATS-broadcast context caching
* Real-time streaming of task updates, agent status, and delegation events

---

## ✨ Select Features

| Feature                            | Description                                                                |
| ---------------------------------- | -------------------------------------------------------------------------- |
| **LLM-Aided Multi-Stage Planning** | Decompose job goals into structured, executable planner tasks              |
| **Flexible DAG Execution**         | Dependency-aware task DAG runner with retry, fallback, and dry-run support |
| **Delegation Strategies**          | Bidding, voting, or direct DSL delegation to runtime agents                |
| **Live Verification System**       | Agent and human verification workflows with WebSocket-based updates        |
| **Tool/Function Management**       | Register, validate, and run local/remote execution assets                  |
| **DSL-Driven Orchestration**       | Compose and execute reusable, schema-validated DSL workflows               |
| **Code Generation Sandbox**        | Securely generate and execute LLM-produced Python logic at runtime         |
| **Metadata-First Registries**      | Rich metadata support for planner selection, versioning, and schema lookup |
| **Agent Context Cache**            | In-memory key-value store with NATS broadcasting                           |
| **Real-Time Messaging Layer**      | Queue-backed messaging for task execution, delegation, and coordination    |
| **Persistent Task DB**             | MongoDB-backed storage for full task lifecycle across meta/sub/behavior    |
| **Dynamic Subject Registry**       | Stores and queries agent subjects and runtime-subject metadata             |

---

## 📚 Supported Libraries & Technologies

| Category                | Technologies & Tools                                                            |
| ----------------------- | ------------------------------------------------------------------------------- |
| **LLM Integration**     | OpenAI APIs, AIOS inference servers (gRPC/REST), AIOS vDAGs                     |
| **Task Orchestration**  | Async Python, DAG engines, dependency tracking, multiprocessing                 |
| **Messaging & Events**  | NATS, WebSockets, Redis Pub/Sub, real-time status tracking                      |
| **Workflow & DSLs**     | Custom DSL interpreters, planner schemas, node-based flow composition           |
| **Storage & Context**   | MongoDB, Redis, PostgreSQL/TimescaleDB, ArangoDB, FrameDB, S3-compatible stores |
| **Embeddings & Search** | Weaviate and Pinecone for vector-based retrieval; OpenAI and AIOS embeddings    |
| **Execution & Infra**   | Kubernetes-native, microservice-compatible, sandboxed Python execution          |

---

## 📦 Use Cases

| Use Case                          | What It Solves                                                 |
| --------------------------------- | -------------------------------------------------------------- |
| **LLM-Driven Workflow Execution** | Auto-generates execution plans and executes structured graphs  |
| **Multi-Agent Delegation**        | Routes sub-tasks to agents via policy-driven delegation logic  |
| **Human/Agent Verification**      | Tracks and verifies responses from external systems or users   |
| **Tool and DSL Integration**      | Enables reusable, discoverable, versioned execution assets     |
| **Code Generation in Production** | Safely executes dynamic logic from LLMs with import extraction |
| **Real-Time Observability**       | Streams task, delegation, and agent updates to dashboards      |

---

# Project Status 🚧

> ⚠️ **Development Status**  
> The project is nearing full completion of version 1.0.0, with minor updates & optimization still being delivered.
> 
> ⚠️ **Alpha Release**  
> Early access version. Use for testing only. Breaking changes may occur.  
>
> 🧪 **Testing Phase**  
> Features are under active validation. Expect occasional issues and ongoing refinements.  
>
> ⛔ **Not Production-Ready**  
> We do not recommend using this in production (or relying on it) right now. 
> 
> 🔄 **Compatibility**  
> APIs, schemas, and configuration may change without notice.  
>
> 💬 **Feedback Welcome**  
> Early feedback helps us stabilize future releases.  


---

## 📢 Communications

1. 📧 Email: [community@opencyberspace.org](mailto:community@opencyberspace.org)  
2. 💬 Discord: [OpenCyberspace](https://discord.gg/W24vZFNB)  
3. 🐦 X (Twitter): [@opencyberspace](https://x.com/opencyberspace)

---

## 🤝 Join Us!

AIGrid is **community-driven**. Theory, Protocol, implementations - All contributions are welcome.

### Get Involved

- 💬 [Join our Discord](https://discord.gg/W24vZFNB)  
- 📧 Email us: [community@opencyberspace.org](mailto:community@opencyberspace.org)