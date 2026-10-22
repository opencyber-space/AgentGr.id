from core.known_agents import KnownAgents
import os
from dotenv import load_dotenv

# Find .env by walking up to the directory containing .git
def find_git_root(path):
    current = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(current, '.git')):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent

_git_root = find_git_root(__file__)
if _git_root:
    load_dotenv(os.path.join(_git_root, '.env'))
else:
    load_dotenv()

from agents_search.search import AgentSearchRanker

from utils.search_ranking_scorer import AgentRanker
import json
from core.db.schema import Subject


INFERENCE_SERVER_REGISTRY_URL = os.environ.get("INFERENCE_SERVER_REGISTRY_URL", "http://<AIOS-INFERENCE-REGISTRY>/api")
BLOCKS_DB_URL = os.environ["BLOCKS_DB_URL"]
INFERENCE_SERVER_ID = os.environ["INFERENCE_SERVER_URL"]

#Create a custom representation of known agents
def _custom_representation(subject: Subject) -> str:
        s = subject
        identity = s.identity
        metadata = s.metadata
        persona = s.persona

        tags = ", ".join(metadata.subject_search_tags) if metadata.subject_search_tags else "none"
        traits = ", ".join(metadata.subject_traits) if metadata.subject_traits else "none"
        
        #user_feedback = s.runtime.user_feedback
        #user_feedback = persona.config["user_feedback"]
        #user_feedback = ", ".join([f"{k}:{v}" for k, v in user_feedback.items()]) if user_feedback else "none"
        #user_feedback_score = str(AgentScorerUserFeedback({}).score_agent(user_feedback))
        #print("User Feedback Score:", user_feedback_score)

        return f"""
Agent [{identity.subject_name}]
Type: {identity.subject_type or "unknown"}
Version: {identity.subject_version.version}

Description: {metadata.subject_description or "No description."}
Tags: {tags}
Traits: {traits}

Persona Role: {persona.role or "unspecified"}
Goal: {persona.goal or "unspecified"}

""".strip()
#User Feedback Score: {user_feedback_score or "0.0"}


known_agents = KnownAgents(default_compact=True)

# known_agents.add_by_id(subject_id="consensus-synthesizer")
# known_agents.add_by_id(subject_id="con-argument-generator")

known_agents.query_and_add(query={
    "metadata.subject_search_tags": "help-desk2"
},custom_repr_fn=_custom_representation)

print([agent.id for agent in known_agents.list_all()])

print(_custom_representation(known_agents.get("account-agent-2-1").subject))

mgr = AgentSearchRanker()
mgr.register_new_ranker(
    name="default",
    model="qwen3-1-7b-vllm-block",
    inference_server_id=INFERENCE_SERVER_ID,
    aios_url_map={
        "inference_server_url": INFERENCE_SERVER_REGISTRY_URL,
        "blocks_db_url": BLOCKS_DB_URL,
    }
)

# --- Part 1: Use LLM for Domain Matching ---

#user_domain_query = "account/login/access"
user_domain_query = "billing/finance/invoice"
# domain_mathc_weight = 0.70
# feedback_weight = 0.30

# This prompt asks the LLM to do ONE thing: provide a domain match score.
LLM_PROMPT = f"""
You are an expert ranking assistant for a help-desk system. Your task is to evaluate how well each agent's specialty matches a user's problem domain and assign a relevance score.

**Domain Definitions:**
- **billing-agent**: Handles financial matters. Keywords: invoice, payment, charge, refund, subscription cost, billing error.
- **account-agent**: Handles user identity and access. Keywords: login, password, email update, profile settings, account access, forgot password.

**Scoring Guidelines:**
- A score of **1.0** means a perfect match for the agent's primary function.
- A score between **0.1 and 0.5** should be given for a partial or related match. For example, a billing query might be slightly related to an account agent, but it is not its primary function.
- A score of **0.0** means no match.

**User's Desired Domain:**
The user is looking for an agent related to: '{user_domain_query}'.

For each agent, provide a `domain_match_score` from 0.0 (not a match) to 1.0 (perfect match).
Base your score on the agent's description, tags, goal, and persona, considering the domain definitions provided above.

Return a JSON array where each object has an 'id' and a 'score' (your domain_match_score).

**Example Output Format:**
```json
[
  {{"id": "agent-id-1", "score": 0.9}},
  {{"id": "agent-id-2", "score": 0.1}}
]
```
"""

print("--- 1. Getting domain match scores from LLM ---")
domain_match_results = mgr.rank_from_objects(
    name="default",
    objects=known_agents.list_all(),
    query=LLM_PROMPT,
    max_tokens = 1024
)
print(json.dumps(domain_match_results, indent=2))

# --- Part 2: Use Python for Final Weighted Scoring ---

print("\n--- 2. Calculating final weighted scores in Python ---")
feedback_weights = {
    "problem": 0.45,
    "rating": 0.25,
    "thumbs": 0.20,
    "sent": 0.10,
}
# Final score weights
final_score_weights = {
    "domain": 0.80,
    "feedback": 0.20,
}
ranker = AgentRanker(feedback_weights, final_score_weights) # Uses default weights

final_scores = []
for agent_id, domain_score in domain_match_results:
    agent = known_agents.get(agent_id)
    if not agent:
        continue
    
    # Get raw feedback data from the agent's subject
    feedback_data = agent.subject.persona.config.get("user_feedback", {})
    
    # Calculate the final score in Python
    final_score_details = ranker.calculate_final_score(feedback_data, domain_score)
    
    final_scores.append({
        "id": agent_id,
        "final_score": final_score_details["score"],
        "details": final_score_details["details"]
    })

# Sort by the final calculated score
final_scores.sort(key=lambda x: x["final_score"], reverse=True)

print(json.dumps(final_scores, indent=2))
