import requests
from agent_workflows import AgentWorkflowEngine
from agent_workflows.abstract import AgentWorkflowModule

from agents_llm import AIGridClient
from agents_llm.custom import OpenAIBlockInferenceSystem

class HackerNewsFetchModule(AgentWorkflowModule):

    def __init__(self):
        super().__init__(name="fetch_hn")

    def _execute(self, workflow_state, input_data):

        query = input_data.get("query", "AI")

        top_ids = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json"
        ).json()[:10]

        articles = []

        for story_id in top_ids:
            item = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
            ).json()

            if item and query.lower() in item.get("title", "").lower():
                articles.append({
                    "title": item["title"],
                    "url": item.get("url"),
                    "score": item.get("score")
                })

        return {"articles": articles}

    def get_description(self):
        return "Fetches top Hacker News stories filtered by keyword."

    def get_input_structure(self):
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }

    def get_output_structure(self):
        return {
            "type": "object",
            "properties": {
                "articles": {"type": "array"}
            },
            "required": ["articles"]
        }

class SummarizeModule(AgentWorkflowModule):

    def __init__(self, llm_client):
        super().__init__(name="summarize_articles")
        self.llm = llm_client

    def _execute(self, workflow_state, input_data):

        documents = input_data["documents"]

        combined_text = "\n\n".join(
            f"{d['title']} - {d.get('url','')}"
            for d in documents
        )

        prompt = f"""
Summarize these Hacker News stories in 5 bullet points:

{combined_text}
"""

        waiter = self.llm.async_chat_completions(
            session_id="summarize-node",
            messages=[{"role": "user", "content": prompt}],
            data={"mode": "chat"}
        )

        summary = waiter.wait()

        return {"summary": summary}

    def get_description(self):
        return "Summarizes a list of documents."

    def get_input_structure(self):
        return {
            "type": "object",
            "properties": {
                "documents": {"type": "array"}
            },
            "required": ["documents"]
        }

    def get_output_structure(self):
        return {
            "type": "object",
            "properties": {
                "summary": {"type": "string"}
            },
            "required": ["summary"]
        }

class ReportFormatterModule(AgentWorkflowModule):

    def __init__(self):
        super().__init__(name="format_report")

    def _execute(self, workflow_state, input_data):

        summary = input_data["summary"]

        report = {
            "title": "AI Industry Executive Report",
            "sections": [
                {
                    "heading": "Key Insights",
                    "content": summary
                }
            ]
        }

        return {"report": report}

    def get_description(self):
        return "Formats summary into structured executive report."

    def get_input_structure(self):
        return {
            "type": "object",
            "properties": {
                "summary": {"type": "string"}
            },
            "required": ["summary"]
        }

    def get_output_structure(self):
        return {
            "type": "object",
            "properties": {
                "report": {"type": "object"}
            },
            "required": ["report"]
        }

openai_block = OpenAIBlockInferenceSystem(
        model="gpt-4o-mini",
        api_key="",
        default_system_prompt="You are a precise selection engine."
    )

client = AIGridClient()
client.add_custom_block(name="default", system=openai_block)

def llm_output_parser(output):
    return output['choices'][0]['message']['content']

engine = AgentWorkflowEngine(
    llm_client=client,
    modules={
        "fetch_hn": HackerNewsFetchModule(),
        "summarize_articles": SummarizeModule(client),
        "format_report": ReportFormatterModule()
    },
    enable_validation=True,
    enable_tracing=True,
    cache_ttl=600,
    llm_output_parser=llm_output_parser
)

state = engine.run(
    "Fetch top Hacker News stories about AI and generate executive report"
)

print(state.to_dict())