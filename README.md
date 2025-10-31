# 🚀 Intelligent Agents Execution & Delegation Framework

**A modular, LLM-powered system for reasoning, planning, delegating, and executing complex tasks using autonomous agents, tools, DSLs, and real-time coordination infrastructure.**
Scalable, pluggable, and built for modern, decentralized AI workloads.

---

## 🌟 Highlights

### 🧠 Multi-Stage Agent Planning & Reasoning

* Two-phase planning system using LLMs: task decomposition → action selection
* Dynamically creates structured, executable task graphs (`PlannerTask`s)
* Supports context-aware, memory-driven planning with FrameDB integration
* Uses prompt planners to guide selection across DSLs, tools, agents, and LLMs

### 🔀 Delegation & Verification Workflows

* Assigns tasks to agents using **bidding**, **voting**, or **DSL-planned routing**
* Tracks assignment lifecycles and updates via WebSockets and DB watchers
* Supports automated and human-in-the-loop verification with real-time response handling
* Integrates constraint validation and deadline expiry logic for robust fault handling

### ⚙️ Modular Execution Engine

* Executes validated task DAGs with support for parallelism and recursion
* Dynamically dispatches to tool executors, LLMs, DSL workflows, or agent APIs
* Sandboxed code execution for runtime-generated Python logic
* Retry, fallback, and dry-run estimation modes supported

### 🧰 Registry-Driven Tool & DSL Ecosystem

* Unified registry for **tools**, **functions**, and **DSL workflows**
* Supports remote REST/gRPC-based tools and local logic executors
* Provides searchable metadata for LLM-based discoverability and selection
* Allows versioning, validation, and dynamic schema inspection

### 🧠 LLM & Optimizer Abstraction

* Backend-agnostic support for OpenAI, gRPC-based inference services, and org-hosted models
* Supports optimizer selection, capability estimation, and structured prompt generation
* Seamless integration with the behavior planner for intelligent flow construction

### 🔗 Real-Time State, Messaging, and Streaming

* Rate-limited, DSL-aware message ingestion using NATS and WebSocket
* Namespace-aware context caching with Redis and TTL-based auto-expiry
* Real-time streaming of task updates, agent status, and delegation events

---

## ✨ Features

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
| **Agent Context Cache**            | In-memory + Redis key-value store with NATS broadcasting                   |
| **Real-Time Messaging Layer**      | Queue-backed messaging for task execution, delegation, and coordination    |
| **Persistent Task DB**             | MongoDB-backed storage for full task lifecycle across meta/sub/behavior    |
| **Dynamic Subject Registry**       | Stores and queries agent subjects and runtime-subject metadata             |

---

## 📚 Supported Libraries & Technologies

| Category                | Technologies & Tools                                                            |
| ----------------------- | ------------------------------------------------------------------------------- |
| **LLM Integration**     | OpenAI APIs, gRPC inference backends, organizational LLMs                       |
| **Task Orchestration**  | Async Python, DAG engines, dependency tracking, multiprocessing                 |
| **Messaging & Events**  | NATS, WebSockets, Redis Pub/Sub, real-time status tracking                      |
| **Workflow & DSLs**     | Custom DSL interpreters, planner schemas, node-based flow composition           |
| **Storage & Context**   | MongoDB, Redis, FrameDB (Redis-backed distributed memory), S3-compatible stores |
| **Embeddings & Search** | FAISS, Milvus, Weaviate, Qdrant, LanceDB for vector-based retrieval             |
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

## 🧠 Subsystems Overview

| Subsystem                  | Role                                                                |
| -------------------------- | ------------------------------------------------------------------- |
| `behavior_controller`      | Phase 1 (plan) + Phase 2 (select) LLM-powered task orchestration    |
| `executor`                 | Runs validated task graphs, manages parallelism and recursion       |
| `functions_tools_registry` | Registers tools/functions, validates schemas, supports remote/local |
| `dsl_manager`              | Manages DSL workflows, schema description, and planner formatting   |
| `delegation_system`        | Delegates sub-tasks via auction, voting, or plan-and-retrieve       |
| `verification_system`      | Verifies tasks via agents or humans, tracks status via WebSockets   |
| `agent_context_cache`      | Key-value cache with topic-based broadcasting and backup control    |
| `agent_tasks_db`           | Stores and queries tasks across meta → sub → behavior layers        |
| `agent_llm_interface`      | Unified LLM inference + optimizer abstraction                       |
| `code_generator_sdk`       | Dynamically generates and safely executes Python logic              |
| `agents_db`                | Registers and searches subject metadata and runtime instances       |
| `communication_layer`      | NATS and WebSocket-based priority messaging and coordination        |

---

## 📁 Source Tree

```
src/
├── agents_sdk/
│   ├── behavior_controller
│   ├── executor
│   ├── context_cache
│   ├── tasks_db
│   ├── communication
│   ├── delegation
│   ├── verification
│   ├── dsl_manager
│   ├── functions_tools_registry
│   ├── llm_interface
│   ├── embeddings
│   ├── code_generator_sdk
│   └── db
```

---

## 📚 Documentation & Links

* 📖 [Full Documentation](docs/)
* 🧠 [Behavior Planning](./src/agents_sdk/behavior_controller/)
* 🧪 \[Tools, Functions, DSLs]\(./src/agents\_sdk/functions\_tools\_registry/, ./src/agents\_sdk/dsl\_manager/)
* ⚙️ [Task Executor](./src/agents_sdk/executor/)
* 🔁 [Delegation System](./src/agents_sdk/delegation/)
* ✅ [Verification System](./src/agents_sdk/verification/)
* 🧬 [Context Cache](./src/agents_sdk/context_cache/)
* 📊 [Agents DB & Search](./src/agents_sdk/db/)
* 🔍 \[LLM + Code SDKs]\(./src/agents\_sdk/llm\_interface/, ./src/agents\_sdk/code\_generator\_sdk/)

---

## 📜 License

Released under [Apache 2.0 License](./LICENSE).
Use it, extend it, and contribute to open agent infrastructure.

---

## 🗣️ Get Involved

We’re building the most flexible orchestration system for autonomous agents and LLM-integrated AI workloads.

* 💬 Submit proposals for new executor types or DSLs
* ⚒️ Contribute modules, planners, tool integrations
* 🧪 Experiment with LLM-augmented workflows in your pipelines
* 🐛 Report bugs, suggest features, or contribute docs

Let’s build the AI coordination layer for the future—one agent at a time.

---
