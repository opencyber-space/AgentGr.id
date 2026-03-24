# Legal Contract Review Pipeline — End-to-End User Guide

> A complete walkthrough for setting up, deploying, and running the Legal Contract Review multi-agent workflow.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Pipeline Architecture](#2-pipeline-architecture)
3. [Agent Reference](#3-agent-reference)
4. [Step 1 — Write the Agent Code](#4-step-1--write-the-agent-code)
5. [Step 2 — Author the Workflow Spec](#5-step-2--author-the-workflow-spec)
6. [Step 3 — Register the Workflow](#6-step-3--register-the-workflow)
7. [Step 4 — Deploy the Workflow Controller](#7-step-4--deploy-the-workflow-controller)
8. [Step 5 — Execute a Task](#8-step-5--execute-a-task)
9. [Understanding the Output](#9-understanding-the-output)
10. [Error Handling](#10-error-handling)
11. [End-to-End Checklist](#11-end-to-end-checklist)

---

## 1. Overview

The **Legal Contract Review Pipeline** is a five-agent static workflow that takes raw contract text as input and produces a structured legal memo with risk findings, compliance analysis, redline suggestions, and a final recommendation.

**What it does, end to end:**

```
Raw contract text
        ↓
  Extract clauses          (clause-extractor-agent)
        ↓
  Identify risks           (risk-identifier-agent)
        ↓
  Check compliance         (compliance-checker-agent)
        ↓
  Advise on redlines       (negotiation-advisor-agent)
        ↓
  Produce legal memo       (legal-memo-agent)
```

**Infrastructure used:**

| Component | Address |
|---|---|
| Workflow Service | `http://35.223.239.192:30721` |
| Agent Delegate API | `http://35.223.239.192:30725` |
| Policy DB | `http://34.58.1.86:30102` |
| Execute Endpoint | `http://35.223.239.192:30712` |

---

## 2. Pipeline Architecture

### Execution Flow

The pipeline is **static and linear** — each agent runs sequentially and passes its full output to the next agent.

```
┌─────────────────────────┐
│   clause-extractor-agent │  ← receives: { "text": "<contract>" }
└────────────┬────────────┘
             ↓
┌─────────────────────────┐
│   risk-identifier-agent  │  ← receives: clauses{}
└────────────┬────────────┘
             ↓
┌──────────────────────────┐
│  compliance-checker-agent │  ← receives: clauses{} + risks[]
└────────────┬─────────────┘
             ↓
┌───────────────────────────┐
│  negotiation-advisor-agent │  ← receives: risks[] + compliance_findings[]
└────────────┬──────────────┘
             ↓
┌─────────────────────────┐
│     legal-memo-agent     │  ← receives: full accumulated payload
└─────────────────────────┘
             ↓
      Legal Memo Output
```

### Accumulated Payload

Each agent carries forward all upstream fields plus its own additions. By the time `legal-memo-agent` runs, the full payload is:

| Field | Added By |
|---|---|
| `raw_contract` | clause-extractor-agent |
| `clauses` | clause-extractor-agent |
| `clause_count` | clause-extractor-agent |
| `risks` | risk-identifier-agent |
| `overall_risk_score` | risk-identifier-agent |
| `high_risk_count` | risk-identifier-agent |
| `compliance_findings` | compliance-checker-agent |
| `non_compliant_count` | compliance-checker-agent |
| `redlines` | negotiation-advisor-agent |
| `negotiation_stance` | negotiation-advisor-agent |

---

## 3. Agent Reference

| Agent | `nodeID` | `id` | Role |
|---|---|---|---|
| Clause Extractor | `clause-extractor-agent` | `w1-clause-1` | Extracts and categorises contract clauses |
| Risk Identifier | `risk-identifier-agent` | `w1-risk-1` | Scores each clause for risk (1–10) |
| Compliance Checker | `compliance-checker-agent` | `w1-comp-1` | Checks clauses against GDPR, CCPA, Delaware law |
| Negotiation Advisor | `negotiation-advisor-agent` | `w1-nego-1` | Produces redline suggestions |
| Legal Memo | `legal-memo-agent` | `w1-memo-1` | Drafts the final legal memo |

All agents use model: `aios:qwen3-1-7b-vllm-block`

---

## 4. Step 1 — Write the Agent Code

Each agent is a Python class implementing two methods: `on_preprocess` (input validation) and `on_data` (core logic). All agents follow the same structure.

### 4.1 Clause Extractor Agent

**File:** `clause_extractor_agent.py`

**Input:** `{ "text": "<raw contract string>" }`  
**Output:** `{ raw_contract, clauses{}, clause_count }`  
**Guards:** Skips if `text` is missing or fewer than 20 characters.

```python
import logging
from typing import List, Optional

from openai import OpenAIError

from core.agent_executor import AgentResult, AgentTask, Context
from core.main import main
from llm import call_llm_json

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a legal clause extraction specialist.

Given a contract text, extract and categorise every clause into the following categories:
- payment
- termination
- liability
- data_ownership
- sla
- renewal
- jurisdiction

Respond ONLY with a valid JSON object in this exact format, no preamble, no markdown:
{
  "clauses": {
    "payment":        "<verbatim or summarised clause text, or null if not found>",
    "termination":    "<verbatim or summarised clause text, or null if not found>",
    "liability":      "<verbatim or summarised clause text, or null if not found>",
    "data_ownership": "<verbatim or summarised clause text, or null if not found>",
    "sla":            "<verbatim or summarised clause text, or null if not found>",
    "renewal":        "<verbatim or summarised clause text, or null if not found>",
    "jurisdiction":   "<verbatim or summarised clause text, or null if not found>"
  },
  "clause_count": <number of non-null clauses found>
}
""".strip()


class ClauseExtractorAgent:

    def __init__(self, subject, context: Context) -> None:
        self.subject = subject
        self.context = context

    def on_preprocess(self, task: AgentTask) -> Optional[List[AgentTask]]:
        text = task.job_data.get("text")
        if not text or not isinstance(text, str):
            log.warning("Task %s missing or invalid 'text' — skipping.", task.task_id)
            return None
        if len(text.strip()) < 20:
            log.warning("Task %s 'text' too short (%d chars) — skipping.", task.task_id, len(text.strip()))
            return None
        return [task]

    def get_muxer(self):
        return None

    def on_data(self, task: AgentTask) -> AgentResult:
        try:
            raw_contract = task.job_data["text"]
            user_message = f"Extract and categorise all clauses from this contract:\n\n{raw_contract}"

            try:
                parsed = call_llm_json(SYSTEM_PROMPT, user_message)
            except OpenAIError as e:
                log.error("Task %s — OpenAI API error: %s", task.task_id, e)
                return AgentResult(task_id=task.task_id, is_error=True,
                                   error_data={"stage": "on_data", "message": f"OpenAI error: {e}"})
            except ValueError as e:
                log.error("Task %s — JSON parse error: %s", task.task_id, e)
                return AgentResult(task_id=task.task_id, is_error=True,
                                   error_data={"stage": "on_data", "message": f"JSON parse error: {e}"})

            clauses      = parsed.get("clauses", {})
            clause_count = parsed.get("clause_count", sum(1 for v in clauses.values() if v))

            log.info("Task %s — extracted %d clause(s)", task.task_id, clause_count)

            return AgentResult(
                task_id=task.task_id,
                job_output={"raw_contract": raw_contract, "clauses": clauses, "clause_count": clause_count},
                job_output_metadata={"clause_count": clause_count},
                is_error=False,
            )

        except Exception as e:
            log.exception("Task %s — unexpected error: %s", task.task_id, e)
            return AgentResult(task_id=task.task_id, is_error=True,
                               error_data={"stage": "on_data", "message": str(e)})


main(ClauseExtractorAgent)
```

---

### 4.2 Risk Identifier Agent

**File:** `risk_identifier_agent.py`

**Input:** `{ clauses{}, raw_contract }`  
**Output:** adds `risks[]`, `overall_risk_score` (1–10), `high_risk_count`  
**Guards:** Skips if `clauses` is missing or all values are null.

```python
import json
import logging
from typing import List, Optional

from openai import OpenAIError

from core.agent_executor import AgentResult, AgentTask, Context
from core.main import main
from llm import call_llm_json

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a senior legal risk analyst specialising in commercial contracts.

You will be given a set of extracted contract clauses. For each clause present,
identify any risks and assign:
- clause_type: the category of the clause
- severity: HIGH, MEDIUM, or LOW
- score: integer 1-10 (10 = most dangerous)
- finding: a concise one-line description of the risk
- reasoning: 2-3 sentences explaining why this is risky

Also compute an overall_risk_score (1-10) as a weighted average across all risks.

Respond ONLY with a valid JSON object, no preamble, no markdown:
{
  "risks": [
    {
      "clause_type": "<category>",
      "severity":    "HIGH|MEDIUM|LOW",
      "score":       <1-10>,
      "finding":     "<finding>",
      "reasoning":   "<reasoning>"
    }
  ],
  "overall_risk_score": <1-10>,
  "high_risk_count":    <int>
}
""".strip()


class RiskIdentifierAgent:

    def __init__(self, subject, context: Context) -> None:
        self.subject = subject
        self.context = context

    def get_muxer(self):
        return None

    def on_preprocess(self, task: AgentTask) -> Optional[List[AgentTask]]:
        clauses = task.job_data.get("clauses")
        if not clauses or not isinstance(clauses, dict):
            log.warning("Task %s missing or invalid 'clauses' — skipping.", task.task_id)
            return None
        if not {k: v for k, v in clauses.items() if v}:
            log.warning("Task %s has no non-null clauses — skipping.", task.task_id)
            return None
        return [task]

    def on_data(self, task: AgentTask) -> AgentResult:
        try:
            clauses      = task.job_data["clauses"]
            raw_contract = task.job_data.get("raw_contract", "")
            user_message = "Identify risks in the following contract clauses:\n\n" + json.dumps(clauses, indent=2)

            try:
                parsed = call_llm_json(SYSTEM_PROMPT, user_message)
            except OpenAIError as e:
                log.error("Task %s — OpenAI API error: %s", task.task_id, e)
                return AgentResult(task_id=task.task_id, is_error=True,
                                   error_data={"stage": "on_data", "message": f"OpenAI error: {e}"})
            except ValueError as e:
                log.error("Task %s — JSON parse error: %s", task.task_id, e)
                return AgentResult(task_id=task.task_id, is_error=True,
                                   error_data={"stage": "on_data", "message": f"JSON parse error: {e}"})

            risks           = parsed.get("risks", [])
            overall_score   = parsed.get("overall_risk_score", 0)
            high_risk_count = parsed.get("high_risk_count", sum(1 for r in risks if r.get("severity") == "HIGH"))

            log.info("Task %s — %d risk(s), score=%s, high=%d", task.task_id, len(risks), overall_score, high_risk_count)

            return AgentResult(
                task_id=task.task_id,
                job_output={"raw_contract": raw_contract, "clauses": clauses,
                            "risks": risks, "overall_risk_score": overall_score, "high_risk_count": high_risk_count},
                job_output_metadata={"risk_count": len(risks), "overall_risk_score": overall_score,
                                     "high_risk_count": high_risk_count},
                is_error=False,
            )

        except Exception as e:
            log.exception("Task %s — unexpected error: %s", task.task_id, e)
            return AgentResult(task_id=task.task_id, is_error=True,
                               error_data={"stage": "on_data", "message": str(e)})


main(RiskIdentifierAgent)
```

---

### 4.3 Compliance Checker Agent

**File:** `compliance_checker_agent.py`

**Input:** `{ risks[], clauses{}, raw_contract, overall_risk_score, high_risk_count }`  
**Output:** adds `compliance_findings[]`, `non_compliant_count`  
**Guards:** Skips if `risks` is missing or not a list.

```python
import json
import logging
from typing import List, Optional

from openai import OpenAIError

from core.agent_executor import AgentResult, AgentTask, Context
from core.main import main
from llm import call_llm_json

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a regulatory compliance attorney specialising in GDPR, CCPA, and Delaware contract law.

You will receive a list of identified contract risks. For each risk, determine whether
the associated clause is compliant with applicable regulations.

For each finding provide:
- clause_type: the clause category
- regulation:  the specific regulation or legal standard (e.g. "GDPR Article 28", "CCPA Section 1798.100")
- status:      one of NON_COMPLIANT, AT_RISK, or COMPLIANT
- detail:      2-3 sentences explaining the compliance determination

Respond ONLY with a valid JSON object, no preamble, no markdown:
{
  "compliance_findings": [
    {
      "clause_type": "<category>",
      "regulation":  "<regulation name and section>",
      "status":      "NON_COMPLIANT|AT_RISK|COMPLIANT",
      "detail":      "<explanation>"
    }
  ],
  "non_compliant_count": <int>
}
""".strip()


class ComplianceCheckerAgent:

    def __init__(self, subject, context: Context) -> None:
        self.subject = subject
        self.context = context

    def on_preprocess(self, task: AgentTask) -> Optional[List[AgentTask]]:
        risks = task.job_data.get("risks")
        if not risks or not isinstance(risks, list):
            log.warning("Task %s missing or invalid 'risks' — skipping.", task.task_id)
            return None
        return [task]

    def get_muxer(self):
        return None

    def on_data(self, task: AgentTask) -> AgentResult:
        try:
            risks             = task.job_data["risks"]
            clauses           = task.job_data.get("clauses", {})
            raw_contract      = task.job_data.get("raw_contract", "")
            overall_score     = task.job_data.get("overall_risk_score", 0)
            high_risk_count   = task.job_data.get("high_risk_count", 0)

            user_message = ("Check the following contract risks for regulatory compliance:\n\n"
                            + json.dumps(risks, indent=2))

            try:
                parsed = call_llm_json(SYSTEM_PROMPT, user_message)
            except OpenAIError as e:
                log.error("Task %s — OpenAI API error: %s", task.task_id, e)
                return AgentResult(task_id=task.task_id, is_error=True,
                                   error_data={"stage": "on_data", "message": f"OpenAI error: {e}"})
            except ValueError as e:
                log.error("Task %s — JSON parse error: %s", task.task_id, e)
                return AgentResult(task_id=task.task_id, is_error=True,
                                   error_data={"stage": "on_data", "message": f"JSON parse error: {e}"})

            compliance_findings = parsed.get("compliance_findings", [])
            non_compliant_count = parsed.get("non_compliant_count",
                sum(1 for f in compliance_findings if f.get("status") == "NON_COMPLIANT"))

            log.info("Task %s — %d finding(s), %d non-compliant",
                     task.task_id, len(compliance_findings), non_compliant_count)

            return AgentResult(
                task_id=task.task_id,
                job_output={"raw_contract": raw_contract, "clauses": clauses, "risks": risks,
                            "overall_risk_score": overall_score, "high_risk_count": high_risk_count,
                            "compliance_findings": compliance_findings, "non_compliant_count": non_compliant_count},
                job_output_metadata={"compliance_findings_count": len(compliance_findings),
                                     "non_compliant_count": non_compliant_count},
                is_error=False,
            )

        except Exception as e:
            log.exception("Task %s — unexpected error: %s", task.task_id, e)
            return AgentResult(task_id=task.task_id, is_error=True,
                               error_data={"stage": "on_data", "message": str(e)})


main(ComplianceCheckerAgent)
```

---

### 4.4 Negotiation Advisor Agent

**File:** `negotiation_advisor_agent.py`

**Input:** `{ risks[], compliance_findings[], clauses{}, raw_contract, overall_risk_score, high_risk_count, non_compliant_count }`  
**Output:** adds `redlines[]`, `negotiation_stance`  
**Guards:** Skips if either `risks` or `compliance_findings` is missing.

```python
import json
import logging
from typing import List, Optional

from openai import OpenAIError

from core.agent_executor import AgentResult, AgentTask, Context
from core.main import main
from llm import call_llm_json

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a commercial contract negotiation specialist representing the client's interests.

You will receive identified risks and compliance findings for a contract.
For each significant issue, produce a concrete redline — a specific suggested replacement
clause that protects the client.

For each redline provide:
- clause_type:  the clause category
- priority:     HIGH, MEDIUM, or LOW
- original:     the problematic language or clause summary
- suggested:    the specific replacement language to propose
- rationale:    1-2 sentences explaining how this protects the client

Also provide an overall negotiation_stance:
- REJECT:               if the contract is fundamentally unacceptable
- NEGOTIATE:            if meaningful redlines can make it acceptable
- ACCEPT_WITH_CHANGES:  if only minor tweaks are needed

Respond ONLY with a valid JSON object, no preamble, no markdown:
{
  "redlines": [
    {
      "clause_type": "<category>",
      "priority":    "HIGH|MEDIUM|LOW",
      "original":    "<problematic language>",
      "suggested":   "<replacement language>",
      "rationale":   "<rationale>"
    }
  ],
  "negotiation_stance": "REJECT|NEGOTIATE|ACCEPT_WITH_CHANGES"
}
""".strip()


class NegotiationAdvisorAgent:

    def __init__(self, subject, context: Context) -> None:
        self.subject = subject
        self.context = context

    def get_muxer(self):
        return None

    def on_preprocess(self, task: AgentTask) -> Optional[List[AgentTask]]:
        if not task.job_data.get("risks") or not isinstance(task.job_data.get("risks"), list):
            log.warning("Task %s missing 'risks' — skipping.", task.task_id)
            return None
        if not task.job_data.get("compliance_findings") or not isinstance(task.job_data.get("compliance_findings"), list):
            log.warning("Task %s missing 'compliance_findings' — skipping.", task.task_id)
            return None
        return [task]

    def on_data(self, task: AgentTask) -> AgentResult:
        try:
            risks               = task.job_data["risks"]
            compliance_findings = task.job_data["compliance_findings"]
            clauses             = task.job_data.get("clauses", {})
            raw_contract        = task.job_data.get("raw_contract", "")
            overall_score       = task.job_data.get("overall_risk_score", 0)
            high_risk_count     = task.job_data.get("high_risk_count", 0)
            non_compliant_count = task.job_data.get("non_compliant_count", 0)

            user_message = ("Produce redlines for the following risks and compliance findings:\n\n"
                            "RISKS:\n" + json.dumps(risks, indent=2)
                            + "\n\nCOMPLIANCE FINDINGS:\n" + json.dumps(compliance_findings, indent=2))

            try:
                parsed = call_llm_json(SYSTEM_PROMPT, user_message)
            except OpenAIError as e:
                log.error("Task %s — OpenAI API error: %s", task.task_id, e)
                return AgentResult(task_id=task.task_id, is_error=True,
                                   error_data={"stage": "on_data", "message": f"OpenAI error: {e}"})
            except ValueError as e:
                log.error("Task %s — JSON parse error: %s", task.task_id, e)
                return AgentResult(task_id=task.task_id, is_error=True,
                                   error_data={"stage": "on_data", "message": f"JSON parse error: {e}"})

            redlines           = parsed.get("redlines", [])
            negotiation_stance = parsed.get("negotiation_stance", "NEGOTIATE")

            log.info("Task %s — %d redline(s), stance=%s", task.task_id, len(redlines), negotiation_stance)

            return AgentResult(
                task_id=task.task_id,
                job_output={"raw_contract": raw_contract, "clauses": clauses, "risks": risks,
                            "overall_risk_score": overall_score, "high_risk_count": high_risk_count,
                            "compliance_findings": compliance_findings, "non_compliant_count": non_compliant_count,
                            "redlines": redlines, "negotiation_stance": negotiation_stance},
                job_output_metadata={"redline_count": len(redlines), "negotiation_stance": negotiation_stance},
                is_error=False,
            )

        except Exception as e:
            log.exception("Task %s — unexpected error: %s", task.task_id, e)
            return AgentResult(task_id=task.task_id, is_error=True,
                               error_data={"stage": "on_data", "message": str(e)})


main(NegotiationAdvisorAgent)
```

---

### 4.5 Legal Memo Agent

**File:** `legal_memo_agent.py`

**Input:** `{ risks[], compliance_findings[], redlines[], clauses{}, overall_risk_score, high_risk_count, non_compliant_count, negotiation_stance }`  
**Output:** `{ memo{}, overall_risk_score, negotiation_stance }`  
**Guards:** Skips if any of `risks`, `compliance_findings`, or `redlines` is missing.

```python
import json
import logging
from typing import List, Optional

from openai import OpenAIError

from core.agent_executor import AgentResult, AgentTask, Context
from core.main import main
from llm import call_llm_json

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a senior legal counsel drafting an internal memo for a client's legal team.

You will receive a full contract analysis including extracted clauses, identified risks,
compliance findings, and proposed redlines.

Produce a concise, professional legal memo with the following sections:
- executive_summary:    2-3 sentences summarising the overall situation and recommendation
- key_risks:            prose paragraph covering the most critical risks
- compliance_issues:    prose paragraph covering any regulatory compliance concerns
- recommended_redlines: prose paragraph summarising the most important redlines to push for
- recommendation:       one of REJECT, NEGOTIATE, or ACCEPT_WITH_CHANGES
- next_steps:           3-5 concrete, actionable next steps as a newline-separated list

Respond ONLY with a valid JSON object, no preamble, no markdown:
{
  "memo": {
    "executive_summary":    "<text>",
    "key_risks":            "<text>",
    "compliance_issues":    "<text>",
    "recommended_redlines": "<text>",
    "recommendation":       "REJECT|NEGOTIATE|ACCEPT_WITH_CHANGES",
    "next_steps":           "<text>"
  }
}
""".strip()


class LegalMemoAgent:

    def __init__(self, subject, context: Context) -> None:
        self.subject = subject
        self.context = context

    def on_preprocess(self, task: AgentTask) -> Optional[List[AgentTask]]:
        for field in ("risks", "compliance_findings", "redlines"):
            if not task.job_data.get(field):
                log.warning("Task %s missing '%s' — skipping.", task.task_id, field)
                return None
        return [task]

    def get_muxer(self):
        return None

    def on_data(self, task: AgentTask) -> AgentResult:
        try:
            risks               = task.job_data["risks"]
            compliance_findings = task.job_data["compliance_findings"]
            redlines            = task.job_data["redlines"]
            clauses             = task.job_data.get("clauses", {})
            overall_score       = task.job_data.get("overall_risk_score", 0)
            high_risk_count     = task.job_data.get("high_risk_count", 0)
            non_compliant_count = task.job_data.get("non_compliant_count", 0)
            negotiation_stance  = task.job_data.get("negotiation_stance", "NEGOTIATE")

            user_message = (
                "Draft a legal memo based on the following contract analysis.\n\n"
                "CLAUSES:\n"                  + json.dumps(clauses, indent=2)
                + "\n\nRISKS:\n"              + json.dumps(risks, indent=2)
                + "\n\nCOMPLIANCE FINDINGS:\n"+ json.dumps(compliance_findings, indent=2)
                + "\n\nPROPOSED REDLINES:\n"  + json.dumps(redlines, indent=2)
                + f"\n\nNEGOTIATION STANCE: {negotiation_stance}"
                + f"\nOVERALL RISK SCORE: {overall_score}/10"
                + f"\nHIGH RISK CLAUSES: {high_risk_count}"
                + f"\nNON-COMPLIANT CLAUSES: {non_compliant_count}"
            )

            try:
                parsed = call_llm_json(SYSTEM_PROMPT, user_message)
            except OpenAIError as e:
                log.error("Task %s — OpenAI API error: %s", task.task_id, e)
                return AgentResult(task_id=task.task_id, is_error=True,
                                   error_data={"stage": "on_data", "message": f"OpenAI error: {e}"})
            except ValueError as e:
                log.error("Task %s — JSON parse error: %s", task.task_id, e)
                return AgentResult(task_id=task.task_id, is_error=True,
                                   error_data={"stage": "on_data", "message": f"JSON parse error: {e}"})

            memo = parsed.get("memo", {})

            log.info("Task %s — memo generated | recommendation=%s",
                     task.task_id, memo.get("recommendation", "N/A"))

            return AgentResult(
                task_id=task.task_id,
                job_output={"memo": memo, "overall_risk_score": overall_score,
                            "negotiation_stance": negotiation_stance},
                job_output_metadata={"recommendation": memo.get("recommendation"),
                                     "overall_risk_score": overall_score},
                is_error=False,
            )

        except Exception as e:
            log.exception("Task %s — unexpected error: %s", task.task_id, e)
            return AgentResult(task_id=task.task_id, is_error=True,
                               error_data={"stage": "on_data", "message": str(e)})


main(LegalMemoAgent)
```

---

## 5. Step 2 — Author the Workflow Spec

Save the following as `spec.json` in your working directory.

```json
{
  "header": {
    "workflow_id": {
      "name":    "legal-contract-review-pipeline-1",
      "version": "1.0.0",
      "release": "stable"
    },
    "metadata": {
      "description": "Multi-agent pipeline to review contracts, flag risks and produce a legal memo",
      "owner":       "legal-ops-team",
      "created_at":  "2026-03-09"
    }
  },
  "body": {
    "nodes": [
      {
        "nodeID": "clause-extractor-agent",
        "type":   "agent",
        "id":     "w1-clause-1",
        "settings": { "model_name": "aios:qwen3-1-7b-vllm-block" }
      },
      {
        "nodeID": "risk-identifier-agent",
        "type":   "agent",
        "id":     "w1-risk-1",
        "settings": { "model_name": "aios:qwen3-1-7b-vllm-block" }
      },
      {
        "nodeID": "compliance-checker-agent",
        "type":   "agent",
        "id":     "w1-comp-1",
        "settings": { "model_name": "aios:qwen3-1-7b-vllm-block" }
      },
      {
        "nodeID": "negotiation-advisor-agent",
        "type":   "agent",
        "id":     "w1-nego-1",
        "settings": { "model_name": "aios:qwen3-1-7b-vllm-block" }
      },
      {
        "nodeID": "legal-memo-agent",
        "type":   "agent",
        "id":     "w1-memo-1",
        "settings": { "model_name": "aios:qwen3-1-7b-vllm-block" }
      }
    ],
    "graph": {
      "clause-extractor-agent":    ["risk-identifier-agent"],
      "risk-identifier-agent":     ["compliance-checker-agent"],
      "compliance-checker-agent":  ["negotiation-advisor-agent"],
      "negotiation-advisor-agent": ["legal-memo-agent"]
    }
  }
}
```

**The `workflow_uri` derived from this header is:**

```
legal-contract-review-pipeline-1:1.0.0-stable
```

You will need this exact string in the next step.

---

## 6. Step 3 — Register the Workflow

Register the spec with the workflow service. This stores it in the database under its `workflow_uri`.

```bash
curl -X POST \
  -d @./spec.json \
  http://35.223.239.192:30721/api/workflows
```

> **Check:** The service should return a success response. If you see a `WorkflowSpecError`, check for duplicate `nodeID` values or graph references that don't match a defined node.

---

## 7. Step 4 — Deploy the Workflow Controller

Deploy a live controller instance that knows where to find the agents and policy engine.

```bash
curl -X POST \
  http://35.223.239.192:30721/api/deploy-workflow/deployer-111 \
  -H "Content-Type: application/json" \
  -d '{
    "deployment_name": "legal-contract-review",
    "workflow_id":     "legal-review-001",
    "workflow_uri":    "legal-contract-review-pipeline-1:1.0.0-stable",
    "allocation": {
      "policy_db_url":    "http://34.58.1.86:30102",
      "delegate_api_url": "http://35.223.239.192:30725"
    }
  }'
```

**Field reference:**

| Field | Value | Notes |
|---|---|---|
| `deployment_name` | `legal-contract-review` | Human-readable label |
| `workflow_id` | `legal-review-001` | Unique instance identifier |
| `workflow_uri` | `legal-contract-review-pipeline-1:1.0.0-stable` | Must match the registered spec exactly |
| `policy_db_url` | `http://34.58.1.86:30102` | Rules engine endpoint |
| `delegate_api_url` | `http://35.223.239.192:30725` | Agent execution endpoint |

> **Critical:** The `workflow_uri` must be an exact match — including name, version, and release. A mismatch causes a `WorkflowDBError`.

---

## 8. Step 5 — Execute a Task

Submit a contract for review. Pass the raw contract text in the `text` field.

```bash
curl -X POST \
  http://35.223.239.192:30712/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Contract: SaaS Subscription Agreement between Acme Corp (vendor) and RetailCo (client). Key clauses: auto-renewal at 15% price increase, no SLA guarantees, data ownership ambiguous, termination requires 180-day notice, liability cap at $5,000 regardless of contract value ($2M/year). Jurisdiction: Delaware, USA."
  }'
```

**Input requirements:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `text` | string | Yes | Raw contract text. Must be at least 20 characters. |

> **Note:** The `clause-extractor-agent` is the entry node — it is the only agent that reads from `text`. All subsequent agents read from the structured output produced by their upstream agent.

---

## 9. Understanding the Output

The final output comes from `legal-memo-agent` and contains:

```json
{
  "memo": {
    "executive_summary":    "High-level summary and overall recommendation.",
    "key_risks":            "Prose covering the most critical identified risks.",
    "compliance_issues":    "Prose covering GDPR, CCPA, or Delaware law concerns.",
    "recommended_redlines": "Prose summarising the most important clauses to renegotiate.",
    "recommendation":       "REJECT | NEGOTIATE | ACCEPT_WITH_CHANGES",
    "next_steps":           "Step 1\nStep 2\nStep 3"
  },
  "overall_risk_score": 8,
  "negotiation_stance": "NEGOTIATE"
}
```

**Recommendation values:**

| Value | Meaning |
|---|---|
| `REJECT` | Contract is fundamentally unacceptable — do not proceed |
| `NEGOTIATE` | Meaningful redlines can make it acceptable |
| `ACCEPT_WITH_CHANGES` | Only minor tweaks needed |

---

## 10. Error Handling

All agents use the same three-level error handling pattern:

| Error Type | Cause | Behaviour |
|---|---|---|
| `on_preprocess` returns `None` | Required input field missing or invalid | Agent is skipped — no output produced |
| `OpenAIError` | LLM API call failed | Returns `AgentResult(is_error=True)` with error details |
| `ValueError` | LLM response could not be parsed as JSON | Returns `AgentResult(is_error=True)` with error details |
| `Exception` | Any other unexpected error | Logged with full traceback, returns `AgentResult(is_error=True)` |

**Cascade behaviour:** If an agent returns `is_error=True`, the next agent's `on_preprocess` will find its required fields missing and skip — this propagates cleanly through the pipeline without crashing the executor.

---

## 11. End-to-End Checklist

```
□  1. All five agent Python files are written and deployed to the agent runtime
□  2. spec.json is saved with the correct header and graph
□  3. Workflow registered:
       curl -X POST -d @./spec.json http://35.223.239.192:30721/api/workflows
□  4. Controller deployed:
       curl -X POST http://35.223.239.192:30721/api/deploy-workflow/deployer-111 ...
       workflow_uri = "legal-contract-review-pipeline-1:1.0.0-stable"
□  5. Task submitted:
       curl -X POST http://35.223.239.192:30712/api/execute ...
       body = { "text": "<contract text>" }
□  6. Output reviewed — check memo.recommendation and overall_risk_score
```