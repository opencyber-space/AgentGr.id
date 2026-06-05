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

from agents_search.search import AgentSearchSelector

from core.db.schema import Subject

#HOW TO RUN
#SUBJECT_DB_URL=... python3 search_test_example.py


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



#known_agents = KnownAgents(default_compact=True)
known_agents = KnownAgents(default_compact=False)

# known_agents.add_by_id(subject_id="consensus-synthesizer")
# known_agents.add_by_id(subject_id="con-argument-generator")

# known_agents.query_and_add(query={
#     "metadata.subject_search_tags": "help-desk"
# })

# known_agents.query_and_add(query={
#     "metadata.subject_search_tags": "help-desk"
# },custom_repr_fn=_custom_representation)

known_agents.query_and_add(query={
    "metadata.subject_search_tags": "marketing"
},custom_repr_fn=_custom_representation)



print([agent.id for agent in known_agents.list_all()])

mgr = AgentSearchSelector()
mgr.register_new_selector(
    name="default",
    model="qwen3-1-7b-vllm-block",
    #system_message = "You are agent selector system which compares agents based on user requirement and select one agent for the users query.",
    inference_server_id=INFERENCE_SERVER_ID,
    aios_url_map={
        "inference_server_url": INFERENCE_SERVER_REGISTRY_URL,
        "blocks_db_url": BLOCKS_DB_URL,
    }
)

# chosen_id = mgr.search_from_objects(
#     name="default",
#     objects=known_agents.list_all(),
#     query="For tech related",
# )

# chosen_id = mgr.search_from_objects(
#     name="default",
#     objects=known_agents.list_all(),
#     query="select tech  issue agent for help desk",
# )
# print("Chosen ID:", chosen_id)

chosen_id = mgr.search_from_objects(
    name="default",
    objects=known_agents.list_all(),
    #query="marketing campaign reviewer for brand and cultural context",
    query="social media campaigner for target audience and strategy"
)
print("Chosen ID:", chosen_id)

