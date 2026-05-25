from __future__ import annotations

from functools import lru_cache
from typing import TypedDict

from typing_extensions import NotRequired
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langsmith import traceable

from .llm import get_chat_model
from .models import Incident, LLMProvider


class IncidentOpsState(TypedDict):
    incident_id: str
    title: str
    service: str
    severity: str
    summary: str
    owner: str
    evidence: NotRequired[str]
    hypothesis: NotRequired[str]
    response_draft: NotRequired[str]
    runbook: NotRequired[str]
    next_action: NotRequired[str]


class IncidentOpsResult(TypedDict):
    graph_run_id: str
    status: str
    summary: str
    next_action: str


def _generate_role_output(role: str, system_prompt: str, state: IncidentOpsState, model) -> str:
    response = model.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=(
                    f"Incident ID: {state['incident_id']}\n"
                    f"Title: {state['title']}\n"
                    f"Service: {state['service']}\n"
                    f"Severity: {state['severity']}\n"
                    f"Owner: {state['owner']}\n"
                    f"Summary: {state['summary']}"
                )
            ),
        ]
    )

    content = getattr(response, "content", "")
    if isinstance(content, list):
        content = " ".join(str(item) for item in content)
    return str(content).strip() or f"{role} produced no textual response."


@lru_cache(maxsize=8)
def build_incident_graph(provider: LLMProvider = "groq", model_name: str | None = None):
    model = get_chat_model(provider=provider, model_name=model_name)

    def assess(state: IncidentOpsState) -> dict[str, str]:
        runbook_text = _generate_role_output(
            "assess",
            "You are the triage agent. Produce a concise risk summary, owner guess, and immediate action.",
            state,
            model,
        )
        return {
            "runbook": runbook_text,
            "next_action": f"Pull telemetry for {state['service']} and compare it with the latest deploy history."
        }

    def gather_evidence(state: IncidentOpsState) -> dict[str, str]:
        evidence_text = _generate_role_output(
            "evidence",
            "You are the evidence agent. Summarize likely observability signals, deploy clues, and missing data.",
            state,
            model,
        )
        return {
            "evidence": evidence_text,
            "next_action": f"Correlate incident {state['incident_id']} against logs, traces, and deployment metadata."
        }

    def draft_response(state: IncidentOpsState) -> dict[str, str]:
        response_text = _generate_role_output(
            "response",
            "You are the mitigation agent. Draft the safest response plan and explicitly state what requires approval.",
            state,
            model,
        )
        return {
            "hypothesis": response_text,
            "response_draft": (
                f"Impact: {state['summary']}\n"
                f"Evidence: {state.get('evidence', '')}\n"
                f"Runbook: {state.get('runbook', '')}\n"
                f"Mitigation: {response_text}"
            ),
            "next_action": "Present the mitigation draft to the human approver before any irreversible action."
        }

    def package_outcome(state: IncidentOpsState) -> dict[str, str]:
        return {
            "next_action": "Await human approval and keep the evidence packet attached to the incident record."
        }

    graph = StateGraph(IncidentOpsState)
    graph.add_node("assess", assess)
    graph.add_node("evidence", gather_evidence)
    graph.add_node("response", draft_response)
    graph.add_node("package", package_outcome)
    graph.add_edge(START, "assess")
    graph.add_edge("assess", "evidence")
    graph.add_edge("evidence", "response")
    graph.add_edge("response", "package")
    graph.add_edge("package", END)
    return graph.compile()


@traceable(name="incident-ops.run", run_type="chain")
def run_incident_workflow(incident: Incident, provider: LLMProvider = "groq", model_name: str | None = None) -> IncidentOpsResult:
    graph = build_incident_graph(provider=provider, model_name=model_name)
    graph_run_id = f"graph_{uuid4().hex}"
    result = graph.invoke(
        {
            "incident_id": incident.id,
            "title": incident.title,
            "service": incident.service,
            "severity": incident.severity,
            "summary": incident.summary,
            "owner": incident.owner,
            "evidence": "",
            "hypothesis": "",
            "response_draft": "",
            "runbook": "",
            "next_action": "",
        }
    )

    return {
        "graph_run_id": graph_run_id,
        "status": "done",
        "summary": result.get("response_draft") or result.get("summary", ""),
        "next_action": result.get("next_action", "Await human approval")
    }
