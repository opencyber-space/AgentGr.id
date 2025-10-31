import logging
import os
from typing import List, Dict

from openai import OpenAI
from agents_embeddings.custom import OpenAIEmbeddingsGenerator   
from agents_embeddings.embeddings import AgentEmbeddingsManager      


def main():
    logging.basicConfig(level=logging.INFO)

    # 1) Build your own OpenAI client (optional; else OpenAIEmbeddingsGenerator creates one)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # 2) Create a custom OpenAI embeddings generator
    custom_gen = OpenAIEmbeddingsGenerator(
        model="text-embedding-3-small",
        client=client,
        logger=logging.getLogger("custom_openai_gen"),
    )

    # 3) Create the manager and register the *custom* generator
    mgr = AgentEmbeddingsManager()
    mgr.register_custom_generator(
        name="openai-custom",
        generator=custom_gen,
        overwrite=True,  # set to False to protect from accidental overwrite
    )

    # 4) Inference: embed plain texts
    texts = ["hello world", "embeddings are useful", "cats vs dogs"]
    text_vecs: List[List[float]] = mgr.embed_texts(
        name="openai-custom",
        texts=texts,
        batch_size=0,  # 0 => single request; set >0 to chunk
    )
    print("Text embeddings dims:", len(text_vecs[0]), "for first vector")

    # 5) Inference: embed objects exposing get_searchable_representation()
    class Doc:
        def __init__(self, doc_id: str, title: str, body: str):
            self.id = doc_id
            self.title = title
            self.body = body
        def get_searchable_representation(self) -> str:
            return f"{self.title}\n{self.body}"

    docs = [
        Doc("d1", "Intro LLMs", "This covers basics of large language models."),
        Doc("d2", "Advanced RAG", "Deep-dive into retrieval augmented generation."),
    ]

    doc_vecs: Dict[str, List[float]] = mgr.embed_objects(
        name="openai-custom",
        objects=docs,
        id_attr="id",
        rep_method="get_searchable_representation",
        batch_size=0,
    )
    for doc_id, vec in doc_vecs.items():
        print(f"{doc_id}: {len(vec)} dims")


if __name__ == "__main__":
    main()
