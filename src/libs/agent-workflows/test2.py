import requests
import json

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
        ).json()[:20]

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


class TechnicalTrendModule(AgentWorkflowModule):

    def __init__(self, llm_client):
        super().__init__(name="extract_technical")
        self.llm = llm_client

    def _execute(self, workflow_state, input_data):

        articles = input_data["articles"]

        combined = "\n".join(a["title"] for a in articles)

        prompt = f"""
From these Hacker News AI articles,
extract technical trends and innovations:

{combined}

Return 5 concise bullet points.
"""

        waiter = self.llm.async_chat_completions(
            session_id="tech-trends",
            messages=[{"role": "user", "content": prompt}],
            data={"mode": "chat"}
        )

        result = waiter.wait()

        return {"technical_trends": result['choices'][0]['message']['content']}

    def get_description(self):
        return "Extracts technical AI trends."

    def get_input_structure(self):
        return {
            "type": "object",
            "properties": {"articles": {"type": "array"}},
            "required": ["articles"]
        }

    def get_output_structure(self):
        return {
            "type": "object",
            "properties": {"technical_trends": {"type": "string"}},
            "required": ["technical_trends"]
        }


class BusinessTrendModule(AgentWorkflowModule):

    def __init__(self, llm_client):
        super().__init__(name="extract_business")
        self.llm = llm_client

    def _execute(self, workflow_state, input_data):

        articles = input_data["articles"]

        combined = "\n".join(a["title"] for a in articles)

        prompt = f"""
From these Hacker News AI articles,
extract business and market trends:

{combined}

Return 5 concise bullet points.
"""

        waiter = self.llm.async_chat_completions(
            session_id="business-trends",
            messages=[{"role": "user", "content": prompt}],
            data={"mode": "chat"}
        )

        result = waiter.wait()

        return {"business_trends": result['choices'][0]['message']['content']}

    def get_description(self):
        return "Extracts AI business trends."

    def get_input_structure(self):
        return {
            "type": "object",
            "properties": {"articles": {"type": "array"}},
            "required": ["articles"]
        }

    def get_output_structure(self):
        return {
            "type": "object",
            "properties": {"business_trends": {"type": "string"}},
            "required": ["business_trends"]
        }


class RiskScoringModule(AgentWorkflowModule):

    def __init__(self, llm_client):
        super().__init__(name="risk_score")
        self.llm = llm_client

    def _execute(self, workflow_state, input_data):

        tech = input_data["technical_trends"]
        biz = input_data["business_trends"]

        prompt = f"""
Given these technical trends:

{tech}

And these business trends:

{biz}

Assess strategic risk level for AI companies.
Return:
- risk_score (0-100)
- short explanation
"""

        waiter = self.llm.async_chat_completions(
            session_id="risk-score",
            messages=[{"role": "user", "content": prompt}],
            data={"mode": "chat"}
        )

        result = waiter.wait()

        return {"risk_assessment": result['choices'][0]['message']['content']}

    def get_description(self):
        return "Computes AI strategic risk score."

    def get_input_structure(self):
        return {
            "type": "object",
            "properties": {
                "technical_trends": {"type": "string"},
                "business_trends": {"type": "string"}
            },
            "required": ["technical_trends", "business_trends"]
        }

    def get_output_structure(self):
        return {
            "type": "object",
            "properties": {"risk_assessment": {"type": "string"}},
            "required": ["risk_assessment"]
        }


class StrategicReportModule(AgentWorkflowModule):

    def __init__(self):
        super().__init__(name="format_report")

    def _execute(self, workflow_state, input_data):

        return {
            "board_report": {
                "title": "AI Strategic Board Report",
                "technical_trends": input_data["technical_trends"],
                "business_trends": input_data["business_trends"],
                "risk_assessment": input_data["risk_assessment"]
            }
        }

    def get_description(self):
        return "Generates board-level strategic report."

    def get_input_structure(self):
        return {
            "type": "object",
            "properties": {
                "technical_trends": {"type": "string"},
                "business_trends": {"type": "string"},
                "risk_assessment": {"type": "string"}
            },
            "required": [
                "technical_trends",
                "business_trends",
                "risk_assessment"
            ]
        }

    def get_output_structure(self):
        return {
            "type": "object",
            "properties": {"board_report": {"type": "object"}},
            "required": ["board_report"]
        }


openai_block = OpenAIBlockInferenceSystem(
    model="gpt-4o-mini",
    api_key="",
    default_system_prompt="You are a precise workflow planner."
)

client = AIGridClient()
client.add_custom_block(name="default", system=openai_block)


def llm_output_parser(output):
    return output['choices'][0]['message']['content']


engine = AgentWorkflowEngine(
    llm_client=client,
    modules={
        "fetch_hn": HackerNewsFetchModule(),
        "extract_technical": TechnicalTrendModule(client),
        "extract_business": BusinessTrendModule(client),
        "risk_score": RiskScoringModule(client),
        "format_report": StrategicReportModule()
    },
    enable_validation=False,
    enable_tracing=True,
    cache_ttl=600,
    llm_output_parser=llm_output_parser
)



state = engine.run(
    "Analyze top Hacker News AI stories and produce a board-level strategic risk report"
)

print("\nFINAL STATE:\n")
print(state.to_dict())