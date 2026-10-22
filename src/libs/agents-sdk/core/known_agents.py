import logging
import threading
from typing import Any, Dict, List, Optional, Union, Callable

from .db.schema import Subject
from .db.agents_db import SubjectDBClient


class KnownAgent:
   
    def __init__(
        self,
        subject: Subject,
        *,
        compact: bool = False,
        custom_repr_fn: Optional[Callable[[Subject], str]] = None,
    ) -> None:
        self.subject = subject
        self.compact = compact
        self.custom_repr_fn = custom_repr_fn

    @property
    def id(self) -> str:
        if getattr(self.subject, "identity", None) is not None:
            sid = getattr(self.subject.identity, "subject_id", None)
            if sid:
                return sid

        # fallback
        sid = getattr(self.subject, "subject_id", None) or getattr(self.subject, "id", None)
        if sid is None:
            raise AttributeError("Subject does not have a usable subject_id")
        return sid

    def get_searchable_representation(self) -> str:
        """
        Return a string LLM can use to select the correct agent.

        Priority:
        1. If custom_repr_fn is provided, call it.
        2. Else if compact=True, return compact version.
        3. Else return full rich representation.
        """
        if self.custom_repr_fn:
            return self.custom_repr_fn(self.subject)

        if self.compact:
            return self._compact_representation()

        return self._full_representation()

    # ------------------------------------------------------------------
    # Compact Version (short)
    # ------------------------------------------------------------------

    def _compact_representation(self) -> str:
        s = self.subject
        identity = s.identity
        metadata = s.metadata
        persona = s.persona

        tags = ", ".join(metadata.subject_search_tags) if metadata.subject_search_tags else "none"
        traits = ", ".join(metadata.subject_traits) if metadata.subject_traits else "none"

        return f"""
    
[AGENT]
ID: {self.id}
Agent [{identity.subject_name}] (ID: {self.id})
Type: {identity.subject_type or "unknown"}
Version: {identity.subject_version.version}

Description: {metadata.subject_description or "No description."}
Tags: {tags}
Traits: {traits}

Persona Role: {persona.role or "unspecified"}
Goal: {persona.goal or "unspecified"}
"""

   
    def _full_representation(self) -> str:
        s = self.subject

        identity = s.identity
        metadata = s.metadata
        persona = s.persona
        owner = s.owner
        execution = s.execution
        integrations = s.integrations
        runtime = s.runtime
        res = runtime.resources

        def _join(values):
            return ", ".join(values) if values else "none"

        def _preview(ids, attr, max_n=1000):
            vals = []
            for it in ids[:max_n]:
                v = getattr(it, attr, "")
                if v:
                    vals.append(v)
            if not vals:
                return "none"
            if len(ids) > max_n:
                return f"{', '.join(vals)} (+{len(ids)-max_n} more)"
            return ", ".join(vals)

        tools_preview = _preview(integrations.subject_tools, "tool_id")
        fns_preview = _preview(integrations.subject_functions, "function_id")
        models_preview = _preview(integrations.models, "llm_block_id")
        dsls_preview = _preview(integrations.dsls, "dsl_workflow_id")
        memories_preview = _preview(integrations.memory_systems, "memory_id")
        subsystems_preview = _preview(integrations.sub_systems, "sub_system_id")

        text = f"""

[AGENT]
ID: {self.id}
Name: {identity.subject_name}
Type: {identity.subject_type}
Version: {identity.subject_version.version} ({identity.subject_version.release_tag})

Description:
{metadata.subject_description or "No description"}

Tags: {_join(metadata.subject_search_tags)}
Traits: {_join(metadata.subject_traits)}

Persona:
- Role: {persona.role}
- Goal: {persona.goal}
- Persona Style: {persona.persona}
- Default System Message: {persona.default_system_message or "none"}

Ownership:
- Org/Team: {owner.org_name or owner.org_id}, {owner.team}
- Owners: {_join(owner.owners)}

Execution:
- Logging Level: {execution.logging_level}
- Delegations: {execution.support_delegations}
- Code Execution: {execution.execute_code}
- Enabled Memory Classes: {_join(execution.enabled_memory_classes)}

Runtime:
- Device: {res.device}
- CPU Cores: {res.cpu_cores}
- Memory (MB): {res.memory_mb}
- GPU: {res.gpu_count}, {res.gpu_memory_mb or "n/a"}
- Exchanges: {_join(runtime.exchanges)}

Capabilities:
- Tools ({len(integrations.subject_tools)}): {tools_preview}
- Functions ({len(integrations.subject_functions)}): {fns_preview}
- Models ({len(integrations.models)}): {models_preview}
- DSLs ({len(integrations.dsls)}): {dsls_preview}
- Memories ({len(integrations.memory_systems)}): {memories_preview}
- Subsystems ({len(integrations.sub_systems)}): {subsystems_preview}
- Contracts: {len(integrations.contracts)}
- Policies: {len(integrations.policies)}
- Addons: {len(integrations.addons)}
- Builtin Modules: {len(integrations.builtin_modules)}
"""
        return text



class KnownAgents:
  

    def __init__(
        self,
        *,
        default_compact: bool = False,
        default_custom_repr_fn: Optional[Callable[[Subject], str]] = None,
    ) -> None:
        self.subject_db_client = SubjectDBClient()
        self.logger = logging.getLogger(self.__class__.__name__)

        # Defaults used when creating KnownAgent instances
        self.default_compact = default_compact
        self.default_custom_repr_fn = default_custom_repr_fn

        self._agents: Dict[str, KnownAgent] = {}
        self._lock = threading.Lock()

   
    def _add_known_agent(self, agent: KnownAgent) -> KnownAgent:
        with self._lock:
            self._agents[agent.id] = agent
        return agent

    def _make_known_agent(
        self,
        subject: Subject,
        *,
        compact: Optional[bool] = None,
        custom_repr_fn: Optional[Callable[[Subject], str]] = None,
    ) -> KnownAgent:
        
        if compact is None:
            compact = self.default_compact
        if custom_repr_fn is None:
            custom_repr_fn = self.default_custom_repr_fn

        return KnownAgent(
            subject,
            compact=compact,
            custom_repr_fn=custom_repr_fn,
        )

 
    def add(
        self,
        subject_or_agent: Union[Subject, KnownAgent],
        *,
        compact: Optional[bool] = None,
        custom_repr_fn: Optional[Callable[[Subject], str]] = None,
    ) -> KnownAgent:
      
        if isinstance(subject_or_agent, KnownAgent):
            agent = subject_or_agent
        else:
            agent = self._make_known_agent(
                subject_or_agent,
                compact=compact,
                custom_repr_fn=custom_repr_fn,
            )

        self.logger.debug("Adding agent %s to KnownAgents", agent.id)
        return self._add_known_agent(agent)
    
    def add_by_id(
        self,
        subject_id: str,
        *,
        compact: Optional[bool] = None,
        custom_repr_fn: Optional[Callable[[Subject], str]] = None,
    ) -> Optional[KnownAgent]:
    
        agent = self.get(subject_id)
        if agent is not None:
            return agent

        self.logger.debug("Fetching subject %s from DB via add_by_id", subject_id)
        subject = self.subject_db_client.get_subject(subject_id)
        if subject is None:
            self.logger.warning("Subject %s not found in DB", subject_id)
            return None

        agent = self._make_known_agent(
            subject,
            compact=compact,
            custom_repr_fn=custom_repr_fn,
        )
        return self._add_known_agent(agent)


    def remove(self, agent_id: str) -> bool:
      
        with self._lock:
            if agent_id in self._agents:
                self.logger.debug("Removing agent %s from KnownAgents", agent_id)
                del self._agents[agent_id]
                return True
            else:
                self.logger.debug("Attempted to remove unknown agent %s", agent_id)
                return False

    def get(self, agent_id: str) -> Optional[KnownAgent]:
       
        with self._lock:
            return self._agents.get(agent_id)

    def get_or_fetch(
        self,
        agent_id: str,
        *,
        compact: Optional[bool] = None,
        custom_repr_fn: Optional[Callable[[Subject], str]] = None,
    ) -> Optional[KnownAgent]:
       
        agent = self.get(agent_id)
        if agent is not None:
            return agent

        self.logger.debug("Agent %s not in cache, fetching from DB", agent_id)
        subject = self.subject_db_client.get_subject(agent_id)
        if subject is None:
            self.logger.warning("Subject %s not found in DB", agent_id)
            return None

        return self.add(
            subject,
            compact=compact,
            custom_repr_fn=custom_repr_fn,
        )

    def list_all(self) -> List[KnownAgent]:
        
        with self._lock:
            return list(self._agents.values())

    def query_and_add(
        self,
        query: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, int]] = None,
        sort: Optional[List[Dict[str, Any]]] = None,
        limit: int = 50,
        skip: int = 0,
        *,
        compact: Optional[bool] = None,
        custom_repr_fn: Optional[Callable[[Subject], str]] = None,
    ) -> List[KnownAgent]:
        
        self.logger.debug(
            "Querying subjects with query=%s projection=%s sort=%s limit=%s skip=%s",
            query,
            projection,
            sort,
            limit,
            skip,
        )

        subjects = self.subject_db_client.query(
            query=query,
            projection=projection,
            sort=sort,
            limit=limit,
            skip=skip,
        )

        agents: List[KnownAgent] = []
        for subj in subjects:
            try:
                agent = self._make_known_agent(
                    subj,
                    compact=compact,
                    custom_repr_fn=custom_repr_fn,
                )
                self._add_known_agent(agent)
                agents.append(agent)
            except Exception as e:
                self.logger.exception("Failed to add subject as KnownAgent: %s", e)

        return agents

    def contains(self, agent_id: str) -> bool:
        
        with self._lock:
            return agent_id in self._agents

    # Optional: runtime tuning of defaults
    def set_default_compact(self, compact: bool) -> None:
        self.default_compact = compact

    def set_default_custom_repr_fn(
        self,
        fn: Optional[Callable[[Subject], str]],
    ) -> None:
        self.default_custom_repr_fn = fn
