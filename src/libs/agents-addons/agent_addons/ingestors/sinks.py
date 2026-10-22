import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("EmbeddingsSinks")

class WeaviateSink:
    
    def __init__(self, client, *, vector_property: str = "vector"):
        self.client = client
        self.vector_property = vector_property

    def insert_vectors(self, collection: str, payload: List[Dict[str, Any]]) -> None:
       
        coll = self.client.collections.get(collection)
        objs = []
        for row in payload:
            meta = dict(row["metadata"] or {})
            props = {k: v for k, v in meta.items() if k != "id"}
          
            props["ext_id"] = row["id"]
            objs.append({
                "properties": props,
                "vector": row["values"],
            })
        coll.data.insert_many(objs)

class PineconeSink:
  
    def __init__(self, index):
        self.index = index

    def insert_vectors(self, collection: str, payload: List[Dict[str, Any]]) -> None:
        # pinecone uses the bound index; 'collection' is informational here
        self.index.upsert(vectors=payload)
