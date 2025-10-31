from agents_search.search import AgentSearchSelector

INFERENCE_SERVER_REGISTRY_URL = "http://<AIOS-INFERENCE-REGISTRY>/api"
BLOCKS_DB_URL = "http://34.58.1.86:30100"
INFERENCE_SERVER_ID = "http://35.232.150.117:31504"


class MyDoc:
    def __init__(self, doc_id, title, body):
        self.id = doc_id
        self.title = title
        self.body = body

    def get_searchable_representation(self) -> str:
        return f"{self.title}\n{self.body}"


docs = [
    MyDoc("A1", "Intro to LLMs", "This covers basics."),
    MyDoc("B2", "Advanced RAG", "Deep dive into retrieval-augmented generation."),
]

mgr = AgentSearchSelector()
mgr.register_new_selector(
    name="default",
    model="magistral-small-2506-llama-cpp-block",
    inference_server_id=INFERENCE_SERVER_ID,
    aios_url_map={
        "inference_server_url": INFERENCE_SERVER_REGISTRY_URL,
        "blocks_db_url": BLOCKS_DB_URL,
    }
)

chosen_id = mgr.search_from_objects(
    name="default",
    objects=docs,
    query="Pick the one about retrieval-augmented generation",
)

print("Chosen ID:", chosen_id)
