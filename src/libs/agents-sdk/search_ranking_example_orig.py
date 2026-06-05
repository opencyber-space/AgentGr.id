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

from search_ranking_scorer import AgentScorer
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
        print(s)

        tags = ", ".join(metadata.subject_search_tags) if metadata.subject_search_tags else "none"
        traits = ", ".join(metadata.subject_traits) if metadata.subject_traits else "none"
        
        #user_feedback = s.runtime.user_feedback
        user_feedback = persona.config["user_feedback"]
        #user_feedback = ", ".join([f"{k}:{v}" for k, v in user_feedback.items()]) if user_feedback else "none"
        user_feedback_data = (
            ", ".join(f"{k} {v}" for k, v in user_feedback.items())
            + "."
        )
        print("User Feedback:", user_feedback_data)

        return f"""
Agent [{identity.subject_name}]
Type: {identity.subject_type or "unknown"}
Version: {identity.subject_version.version}

Description: {metadata.subject_description or "No description."}
Tags: {tags}
Traits: {traits}

Persona Role: {persona.role or "unspecified"}
Goal: {persona.goal or "unspecified"}

User Feedback: {user_feedback_data or "unspecified"}
""".strip()


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
SCORING_SPEC = (
    "You MUST follow these rules exactly. Output strict JSON ONLY and nothing else. "
    "1) Normalization rules: problem_solved_percentage_norm = clamp(problem_solved_percentage / 100, 0, 1); "
    "rating_stars_norm = clamp(rating_stars / 5, 0, 1); "
    "thumbs_norm: let up=(value or 0), down=(value or 0); delta=up-down; denom=max(up+down,1); ratio=delta/denom; thumbs_norm=(ratio+1)/2; "
    "sentiment_score: positive=1.0, neutral=0.5, negative=0.0. "
    "2) Feedback component weights: w_problem=0.45, w_rating=0.25, w_thumbs=0.20, w_sent=0.10; normalize if needed so they sum to 1.0. "
    "3) feedback_score = w_problem*problem_solved_percentage_norm + w_rating*rating_stars_norm + w_thumbs*thumbs_norm + w_sent*sentiment_score. "
    "4) Domain match: if item's description/tags/persona contain 'account' or 'access' or 'login', domain_match=1.0 else 0.0. "
    "5) Final score: domain_weight=0.20, feedback_weight=0.80; final_score = domain_weight*domain_match + feedback_weight*feedback_score; clamp to [0,1]; round to 3 decimals. "
    "6) Tie-breaking: if same final_score (3 decimals), then compare feedback_score, then rating_stars_norm, then thumbs_norm, then problem_solved_percentage_norm, then lexicographical id. "
    "7) Output schema: ```json [{ 'id': <str>, 'score': <float>}, { 'id': <str>, 'score': <float>}]```"
    "8) Validation: produce entry for every id, no missing ids, no extra ids, numeric values must be numbers, all outputs rounded to 3 decimals. "
    "9) Edge cases: missing fields treated as 0; if thumbs_up+thumbs_down==0, thumbs_norm defaults to 0.5 via formula; clamp all out-of-range values. "
    "10) STRICT JSON ONLY. If error, return { 'error': '<description>' }."
)

result = mgr.rank_from_objects(
# New prompt to ask the LLM to act as a data extractor, not a calculator.
EXTRACT_PROMPT = """
You are an information extraction assistant.
For each agent provided, extract its user feedback data.
The feedback data includes: 'thumbs_up', 'thumbs_down', 'rating_stars', 'problem_solved_percentage', and 'sentiment'.

Your task is to return a JSON array where each object contains:
1. The agent's 'id'.
2. A 'feedback' object containing the extracted values. If a value is not present, use a default of 0 for numbers and 'neutral' for sentiment.

User Query: "Select the MOST relevant specialist agent for account issues. Prefer agents whose primary domain is account/login/access."

Output strict JSON only, like this:
```json
[
  {"id": "agent-id-1", "feedback": {"thumbs_up": 100, "thumbs_down": 5, "rating_stars": 4.5, "problem_solved_percentage": 95, "sentiment": "positive"}},
  {"id": "agent-id-2", "feedback": {"thumbs_up": 50, "thumbs_down": 10, "rating_stars": 3.8, "problem_solved_percentage": 80, "sentiment": "neutral"}}
]
```
"""

# Use the ranker to get structured data from the LLM
extracted_data_list = mgr.rank_from_objects(
    name="default",
    objects=known_agents.list_all(),
    query = (
        "Select the MOST relevant specialist agent for account issues. "
        "Prefer agents whose primary domain is account/login/access, "
        "NOT generic routing or other domains."
        "Rules for user_feedback is as below: "
        "thumbs_up more is better, thumbs_down less is better, rating_stars more is better, problem_solved_percentage more is better, sentiment positive is better than neutral which is better than negative. "
        "use the mathematical model given in the instruction to score user_feedback and use that to influence your ranking and score calculation."
    ) + SCORING_SPEC,
    query=EXTRACT_PROMPT,
    max_tokens = 1024
)

print(result)
print("--- Data Extracted by LLM ---")
print(json.dumps(extracted_data_list, indent=2))

# Now, use our Python scorer to perform the calculations
scorer = AgentScorer(domain_keywords=["account", "access", "login"])

agents_with_feedback = [{"agent_object": known_agents.get(item['id']), "feedback": item['feedback']} for item in extracted_data_list if 'id' in item and 'feedback' in item]

final_ranking = scorer.rank_agents(agents_with_feedback)

print("\n--- Final Ranking Calculated by Python ---")
print(final_ranking)