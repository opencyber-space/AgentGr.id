import uuid
from typing import Any, Dict, Optional, List


from .db.schema import Subject
from .db.exchange import ExchangeSubjects


def _stable_subject_id(s: Subject) -> str:
    sid = getattr(s.identity, "subject_id", None)
    if isinstance(sid, str) and sid.strip():
        return sid
    basis = f"{s.identity.subject_name}::{s.identity.subject_version.version}".strip() or "unnamed::0.0.0"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, basis))

def _summarize_list(items, fields: List[str]) -> List[Dict[str, Any]]:
    out = []
    for it in items or []:
        d = {}
        for f in fields:
            v = getattr(it, f, None)
            if v not in (None, "", [], {}):
                d[f] = v
        out.append(d)
    return out

def subject_to_exchange_subject(
    subject: Subject,
    *,
    subject_page_base: Optional[str] = None,  
    api_base: Optional[str] = None,            
    docs_base: Optional[str] = None          
) -> ExchangeSubjects:
    sid = _stable_subject_id(subject)

    subject_uri = f"{subject_page_base.rstrip('/')}/{sid}" if subject_page_base else ""
    subject_urls: Dict[str, Any] = {}


    # ----- Core identit -----
    ident = subject.identity
    meta = subject.metadata
    persona = subject.persona
    execp = subject.execution
    integ = subject.integrations
    owner = subject.owner

    # ----- Capabilities summary (IDs and key fields only; good for search/discovery) -----
    capabilities: Dict[str, Any] = {
        "models": _summarize_list(
            integ.models,
            ["llm_type", "llm_block_id", "llm_selection_query", "llm_parameters"],
        ),
        "functions": _summarize_list(
            integ.subject_functions,
            ["function_id", "function_custom_parameters", "function_calling_config"],
        ),
        "tools": _summarize_list(
            integ.subject_tools,
            ["tool_id", "tool_description", "tool_execution_mode", "tool_custom_config", "tool_calling_config"],
        ),
        "policies": _summarize_list(
            integ.policies,
            ["policy_type", "policy_rule_uri", "parameters", "settings"],
        ),
        "dsls": _summarize_list(
            integ.dsls,
            ["dsl_type", "dsl_workflow_id", "dsl_parameters"],
        ),
        "addons": _summarize_list(
            integ.addons,
            ["addon_id", "addon_type", "addon_config"],
        ),
        "contracts": _summarize_list(
            integ.contracts,
            ["contract_type", "contract_id", "contract_parameters"],
        ),
        "memory_systems": _summarize_list(
            integ.memory_systems,
            ["memory_id", "memory_type", "memory_backend", "memory_custom_config"],
        ),
        "sub_systems": _summarize_list(
            integ.sub_systems,
            ["sub_system_id", "sub_system_type", "sub_system_config"],
        ),
        "builtin_modules": [
            {
                "module_id": m.module_id,
                "module_description": m.module_description,
                "management_commands": _summarize_list(
                    m.module_management_commands,
                    ["command", "command_description", "input_template", "output_template"],
                ),
            }
            for m in (integ.builtin_modules or [])
        ],
        "counts": {
            "models": len(integ.models or []),
            "functions": len(integ.subject_functions or []),
            "tools": len(integ.subject_tools or []),
            "policies": len(integ.policies or []),
            "dsls": len(integ.dsls or []),
            "addons": len(integ.addons or []),
            "contracts": len(integ.contracts or []),
            "memory_systems": len(integ.memory_systems or []),
            "sub_systems": len(integ.sub_systems or []),
            "builtin_modules": len(integ.builtin_modules or []),
        },
    }

    # ----- Runtime + management surface (useful for ops filters/search) -----
    runtime_surface: Dict[str, Any] = {
        "resources": subject.runtime.resources.to_dict(),
        "management_commands": _summarize_list(
            subject.runtime.management_commands,
            ["command", "command_description", "input_template", "output_template"],
        ),
    }

    # ----- Prompting surface (helps consumers understand default behavior) -----
    prompting_surface: Dict[str, Any] = {
        "templates": {
            "default_system_template": subject.prompting.default_system_template,
            "input_template": subject.prompting.input_template,
            "output_template": subject.prompting.output_template,
        },
        "prompts_config": subject.prompting.prompts_config or {},
    }

    # ----- Owner/Org info (for listing, filtering, and contact) -----
    owner_surface: Dict[str, Any] = {
        "org_id": owner.org_id,
        "org_name": owner.org_name,
        "team": owner.team,
        "owners": owner.owners or [],
        "contacts": owner.contacts or {},
    }

    # ----- Execution policy (discoverability: can it delegate? execute code? etc.) -----
    execution_surface: Dict[str, Any] = {
        "logging_level": execp.logging_level,
        "support_delegations": execp.support_delegations,
        "execute_code": execp.execute_code,
        "enabled_memory_classes": execp.enabled_memory_classes or [],
    }

    # ----- Persona (public summary) -----
    persona_surface: Dict[str, Any] = {
        "role": persona.role,
        "goal": persona.goal,
        "persona": persona.persona,
        # Expose the default system message only if you intend this to be public.
        "default_system_message": persona.default_system_message,
    }

    # ----- Public search/discovery metadata -----
    subject_metadata: Dict[str, Any] = {
        "name": ident.subject_name,
        "type": ident.subject_type,
        "version": ident.subject_version.version,
        "release_tag": ident.subject_version.release_tag,
        "description": meta.subject_description,
        "tags": meta.subject_search_tags or [],
        "traits": meta.subject_traits or [],
        "owner": owner_surface,
        "persona": persona_surface,
        "execution": execution_surface,
        "runtime": runtime_surface,
        "prompting": prompting_surface,
        "capabilities": capabilities,
        # Add a few convenient, flattened fields for indexing/sorting:
        "_sort_keys": {
            "name_lc": (ident.subject_name or "").lower(),
            "type_lc": (ident.subject_type or "").lower(),
            "org_lc": (owner.org_name or "").lower() if owner.org_name else "",
            "version": ident.subject_version.version,
            "release_tag": ident.subject_version.release_tag,
        },
    }

    return ExchangeSubjects(
        subject_id=sid,
        subject_uri=subject_uri,
        subject_metadata=subject_metadata,
        subject_urls=subject_urls,
    )
