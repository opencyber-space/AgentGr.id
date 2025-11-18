from core.known_agents import KnownAgents
from agents_search.search import AgentSearchSelector


INFERENCE_SERVER_REGISTRY_URL = "http://<AIOS-INFERENCE-REGISTRY>/api"
BLOCKS_DB_URL = "http://34.58.1.86:30100"
INFERENCE_SERVER_ID = "http://35.232.150.117:31504"


known_agents = KnownAgents(default_compact=False)

# known_agents.add_by_id(subject_id="consensus-synthesizer")
# known_agents.add_by_id(subject_id="con-argument-generator")

known_agents.query_and_add(query={
    "metadata.subject_search_tags": "help-desk"
})

print([agent.id for agent in known_agents.list_all()])

mgr = AgentSearchSelector()
mgr.register_new_selector(
    name="default",
    model="qwen3-1-7b-vllm-block",
    inference_server_id=INFERENCE_SERVER_ID,
    aios_url_map={
        "inference_server_url": INFERENCE_SERVER_REGISTRY_URL,
        "blocks_db_url": BLOCKS_DB_URL,
    }
)

chosen_id = mgr.search_from_objects(
    name="default",
    objects=known_agents.list_all(),
    query="For tech related",
)

print("Chosen ID:", chosen_id)