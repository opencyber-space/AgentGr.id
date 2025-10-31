# example_selection_e2e.py
from dataclasses import dataclass
from typing import List

# Your infrastructure
from agents_llm import AIGridClient
from agents_llm import OpenAIBlockInferenceSystem


# --- Sample entity type -------------------------------------------------------
@dataclass
class Shoe:
    id: str
    title: str
    tags: List[str]
    brand: str

    def get_searchable_representation(self) -> str:
        # Keep this short & info-dense. It’s what the LLM sees per item.
        return f"title={self.title}; brand={self.brand}; tags={','.join(self.tags)}"


def main():
   
    openai_block = OpenAIBlockInferenceSystem(
        model="gpt-4o-mini",
        api_key="",
        default_system_prompt="You are a precise selection engine."
    )

    client = AIGridClient()
    client.add_custom_block(name="selector", system=openai_block)

    # 2) Build some candidate entities
    entities = [
        Shoe(id="A1", title="Red Running Shoes",  tags=["running", "mens", "daily"],   brand="FleetRun"),
        Shoe(id="B2", title="Blue Trail Shoes",   tags=["trail", "outdoor", "grip"],   brand="TerraStep"),
        Shoe(id="C3", title="Black Formal Shoes", tags=["formal", "office", "mens"],   brand="Eleganz"),
    ]

    # 3) Create the selection engine
    engine = client.create_selector(name="selector", base_query="")

 
    result = engine.select(
        entities=entities,
        user_query="I need men's running shoes suitable for daily jogging.",
        session_id="sess-001",
        extra_data={
            "temperature": 0.0,
            "max_tokens": 512,
        },
    )

    print("Selected ID:", result.selected_id)   # e.g. "A1"
    print("Raw JSON:", result.raw_json)         # e.g. {"id": "A1"}


if __name__ == "__main__":
    main()
