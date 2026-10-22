# Workflow System

A declarative, AI-native workflow orchestration framework for building scalable, composable, and adaptive execution pipelines.

---

## 1. Introduction

The Workflow System is a JSON-based Domain Specific Language (DSL) and execution engine designed to orchestrate complex pipelines composed of:

- Deterministic policies
- AI agents
- Nested workflows

Each workflow defines **what to execute**, **how to execute it**, and **how execution flows between steps**.

At runtime, a workflow is interpreted by the workflow executor (`AgentDSLWorkflowExecutor`, in the `agents-dsl-workflow` library). Each deployed workflow runs as its own executor service, which coordinates execution across policy executors, the agent Delegate API, and nested sub-workflow executors.

The system supports two execution paradigms:

- **Static Workflows** — Predefined DAG-based execution
- **Dynamic Workflows** — Runtime decision-making via router agents

This enables use cases ranging from simple pipelines to advanced multi-agent, decision-driven systems.

---

## 2. Key Features

### Declarative Workflow Definition
Workflows are defined as structured JSON with clear separation of identity (`header`) and execution logic (`body`). This ensures portability, validation, and consistency.

---

### Strong Versioning and Identity
Each workflow is uniquely identified using:

```

{name}:{version}-{release}

```

This allows:
- Immutable workflow versions
- Safe upgrades and rollbacks
- Reliable referencing across systems

---

### Multiple Execution Primitives

Workflows support three core node types:

- **Policy Nodes** — Deterministic logic (rules, APIs, jobs)
- **Agent Nodes** — AI-driven execution via delegate APIs
- **Workflow Nodes** — Nested workflows for composition

---

### Static and Dynamic Execution Models

**Static (DAG-based):**
- Predefined execution graph
- Topological ordering (Kahn's algorithm)
- Fan-out / fan-in dependencies

**Dynamic (Router-based):**
- Execution determined at runtime
- Controlled by a router agent
- Enables conditional branching, loops, and adaptive flows

---

### Dependency Handling

- Fan-out (one node feeding many) and fan-in (many nodes feeding one) graphs
- Automatic input resolution:
  - No parent → the workflow's initial input
  - Single parent → that parent's output
  - Multiple parents → a list of the parents' outputs

> Nodes are executed **one at a time**. In a static workflow they run in topological order; in a dynamic workflow the nodes of a router batch run one after another, in the order the router listed them.

---

### Progressive Data Enrichment

Execution follows a cumulative data model:

- The initial input is passed to the entry node(s)
- Each node receives its upstream output and can enrich or transform it
- The execution result is a map of `nodeID → output` for every node that ran

---

### Composability

Workflows can call other workflows as nodes, enabling:

- Modular design
- Reusability
- Hierarchical orchestration

---

### Long-Running Task Support

Using job-based policies (`policyType: "job"`):
- The job is submitted to an external job executor
- The executor polls for completion (`poll_interval`, `max_retries`)
- External compute integration

---

### AI-Native Orchestration

Agents can:
- Execute tasks
- Route workflows dynamically
- Make decisions based on context

This enables advanced use cases like:
- Multi-agent systems
- LLM pipelines
- Autonomous workflows

---

### End-to-End Lifecycle

Workflows follow a complete lifecycle:

1. Author workflow JSON  
2. Register workflow (`POST /api/workflows`)  
3. Deploy a workflow executor (`POST /api/deploy-workflow/<deployer_id>`)  
4. Execute tasks (`POST <executor_url>/api/execute`)  

---

## 3. Table of contents

Use the following documents to understand and work with the system:

- [Workflow Schema Reference](./schema.md)
- [Creating Workflows — User Guide](./creating_workflow.md)
- [Workflow Onboarding Guide](./onboarding_workflow.md)
- [Sample Workflow — Legal Contract Review Pipeline](./writing_sample_workflow.md)

---

## 4. Summary

The Workflow System provides a unified framework for building:

- Deterministic pipelines
- AI-driven workflows
- Adaptive, decision-based execution systems

By combining declarative definitions with dynamic execution capabilities, it enables scalable and flexible orchestration across a wide range of applications.
