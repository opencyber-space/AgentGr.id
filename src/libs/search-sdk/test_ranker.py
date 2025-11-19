from agents_search.search import AgentSearchRanker, AgentSearchPolicyExecutor

INFERENCE_SERVER_REGISTRY_URL = "http://<AIOS-INFERENCE-REGISTRY>/api"
BLOCKS_DB_URL = "http://34.58.1.86:30100"
INFERENCE_SERVER_ID = "http://35.232.150.117:31504"


# ------- Dummy Document Class --------
class MyDoc:
    def __init__(self, doc_id, title, body):
        self.id = doc_id
        self.title = title
        self.body = body

    def get_searchable_representation(self) -> str:
        return f"{self.title}\n{self.body}"


# ------- Example Data --------
docs = [
    MyDoc("A1", "Intro to LLMs", "This covers basics."),
    MyDoc("B2", "Advanced RAG", "Deep dive into retrieval-augmented generation."),
]


# ------- Initialize the Ranker Manager --------
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


# ------- Perform Ranking --------
ranked = mgr.rank_from_objects(
    name="default",
    objects=docs,
    query="Rank documents by relevance to 'retrieval-augmented generation'",
)

print("Ranking Results:")
for doc_id, score in ranked:
    print(f"  {doc_id}: {score:.4f}")
