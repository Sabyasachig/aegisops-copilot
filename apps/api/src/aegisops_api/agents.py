from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from time import perf_counter
from typing import NotRequired, TypedDict
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langsmith import traceable
from opentelemetry import trace

from .llm import get_chat_model
from .logging_config import bind_log_context, get_logger
from .metrics import add_llm_tokens
from .models import Incident, LLMProvider
from .tracing import get_current_trace_id

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)


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
    trace_id: NotRequired[str]


def _extract_total_tokens(response) -> int | None:
    usage_metadata = getattr(response, "usage_metadata", None)
    if isinstance(usage_metadata, dict):
        total = usage_metadata.get("total_tokens")
        if isinstance(total, int):
            return total
        input_tokens = usage_metadata.get("input_tokens")
        output_tokens = usage_metadata.get("output_tokens")
        if isinstance(input_tokens, int) and isinstance(output_tokens, int):
            return input_tokens + output_tokens

    response_metadata = getattr(response, "response_metadata", None)
    if isinstance(response_metadata, dict):
        token_usage = response_metadata.get("token_usage")
        if isinstance(token_usage, dict):
            total = token_usage.get("total_tokens")
            if isinstance(total, int):
                return total
            prompt_tokens = token_usage.get("prompt_tokens")
            completion_tokens = token_usage.get("completion_tokens")
            if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
                return prompt_tokens + completion_tokens
    return None


def _generate_role_output(
    role: str,
    system_prompt: str,
    state: IncidentOpsState,
    model,
    provider: str,
) -> str:
    started = perf_counter()
    logger.info("llm_call_started", node=role)
    with tracer.start_as_current_span(
        "llm.call",
        attributes={
            "ai.provider": provider,
            "ai.node": role,
            "incident.id": state["incident_id"],
        },
    ):
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
    token_total = _extract_total_tokens(response)
    if token_total is not None:
        add_llm_tokens(token_total, provider=provider)
    duration_ms = round((perf_counter() - started) * 1000, 2)
    logger.info("llm_call_completed", node=role, duration_ms=duration_ms)
    return str(content).strip() or f"{role} produced no textual response."


@lru_cache(maxsize=8)
def build_incident_graph(provider: LLMProvider = "groq", model_name: str | None = None):
    model = get_chat_model(provider=provider, model_name=model_name)

    def assess(state: IncidentOpsState) -> dict[str, str]:
        logger.info("node_started", node="assess")
        runbook_text = _generate_role_output(
            "assess",
            "You are the triage agent. Produce a concise risk summary, owner guess, and immediate action.",
            state,
            model,
            provider,
        )
        result = {
            "runbook": runbook_text,
            "next_action": f"Pull telemetry for {state['service']} and compare it with the latest deploy history.",
        }
        logger.info("node_completed", node="assess")
        return result

    def gather_evidence(state: IncidentOpsState) -> dict[str, str]:
        logger.info("node_started", node="evidence")
        evidence_text = _generate_role_output(
            "evidence",
            "You are the evidence agent. Summarize likely observability signals, deploy clues, and missing data.",
            state,
            model,
            provider,
        )
        result = {
            "evidence": evidence_text,
            "next_action": f"Correlate incident {state['incident_id']} against logs, traces, and deployment metadata.",
        }
        logger.info("node_completed", node="evidence")
        return result

    def draft_response(state: IncidentOpsState) -> dict[str, str]:
        logger.info("node_started", node="response")
        response_text = _generate_role_output(
            "response",
            "You are the mitigation agent. Draft the safest response plan and explicitly state what requires approval.",
            state,
            model,
            provider,
        )
        result = {
            "hypothesis": response_text,
            "response_draft": (
                f"Impact: {state['summary']}\n"
                f"Evidence: {state.get('evidence', '')}\n"
                f"Runbook: {state.get('runbook', '')}\n"
                f"Mitigation: {response_text}"
            ),
            "next_action": "Present the mitigation draft to the human approver before any irreversible action.",
        }
        logger.info("node_completed", node="response")
        return result

    def package_outcome(state: IncidentOpsState) -> dict[str, str]:
        logger.info("node_started", node="package")
        result = {
            "next_action": "Await human approval and keep the evidence packet attached to the incident record."
        }
        logger.info("node_completed", node="package")
        return result

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
def run_incident_workflow(
    incident: Incident,
    provider: LLMProvider = "groq",
    model_name: str | None = None,
    user_id: str | None = None,
    event_emitter: Callable[[str, dict[str, str]], None] | None = None,
) -> IncidentOpsResult:
    def emit(event: str, **payload: str) -> None:
        if event_emitter is not None:
            event_emitter(event, payload)

    graph_run_id = f"graph_{uuid4().hex}"

    with tracer.start_as_current_span(
        "incident.workflow",
        attributes={
            "incident.id": incident.id,
            "ai.provider": provider,
        },
    ):
        trace_id = get_current_trace_id()
        bind_log_context(incident_id=incident.id, user_id=user_id, run_id=graph_run_id)
        if trace_id is not None:
            bind_log_context(trace_id=trace_id)
        logger.info("workflow_started", provider=provider, model_name=model_name, trace_id=trace_id)

        # Rebuild with event hooks for this invocation.
        model = get_chat_model(provider=provider, model_name=model_name)

        def assess(state: IncidentOpsState) -> dict[str, str]:
            logger.info("node_started", node="assess")
            emit("node_started", node="assess", run_id=graph_run_id)
            with tracer.start_as_current_span("incident.node.assess"):
                runbook_text = _generate_role_output(
                    "assess",
                    "You are the triage agent. Produce a concise risk summary, owner guess, and immediate action.",
                    state,
                    model,
                    provider,
                )
            result = {
                "runbook": runbook_text,
                "next_action": f"Pull telemetry for {state['service']} and compare it with the latest deploy history.",
            }
            logger.info("node_completed", node="assess")
            emit("node_completed", node="assess", run_id=graph_run_id)
            return result

        def gather_evidence(state: IncidentOpsState) -> dict[str, str]:
            logger.info("node_started", node="evidence")
            emit("node_started", node="evidence", run_id=graph_run_id)
            with tracer.start_as_current_span("incident.node.evidence"):
                evidence_text = _generate_role_output(
                    "evidence",
                    "You are the evidence agent. Summarize likely observability signals, deploy clues, and missing data.",
                    state,
                    model,
                    provider,
                )
            result = {
                "evidence": evidence_text,
                "next_action": f"Correlate incident {state['incident_id']} against logs, traces, and deployment metadata.",
            }
            logger.info("node_completed", node="evidence")
            emit("node_completed", node="evidence", run_id=graph_run_id)
            return result

        def draft_response(state: IncidentOpsState) -> dict[str, str]:
            logger.info("node_started", node="response")
            emit("node_started", node="response", run_id=graph_run_id)
            with tracer.start_as_current_span("incident.node.response"):
                response_text = _generate_role_output(
                    "response",
                    "You are the mitigation agent. Draft the safest response plan and explicitly state what requires approval.",
                    state,
                    model,
                    provider,
                )
            result = {
                "hypothesis": response_text,
                "response_draft": (
                    f"Impact: {state['summary']}\n"
                    f"Evidence: {state.get('evidence', '')}\n"
                    f"Runbook: {state.get('runbook', '')}\n"
                    f"Mitigation: {response_text}"
                ),
                "next_action": "Present the mitigation draft to the human approver before any irreversible action.",
            }
            logger.info("node_completed", node="response")
            emit("node_completed", node="response", run_id=graph_run_id)
            return result

        def package_outcome(state: IncidentOpsState) -> dict[str, str]:
            logger.info("node_started", node="package")
            emit("node_started", node="package", run_id=graph_run_id)
            with tracer.start_as_current_span("incident.node.package"):
                result = {
                    "next_action": "Await human approval and keep the evidence packet attached to the incident record."
                }
            logger.info("node_completed", node="package")
            emit("node_completed", node="package", run_id=graph_run_id)
            return result

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
        compiled_graph = graph.compile()
        result = compiled_graph.invoke(
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

        payload = {
            "graph_run_id": graph_run_id,
            "status": "done",
            "summary": result.get("response_draft") or result.get("summary", ""),
            "next_action": result.get("next_action", "Await human approval"),
        }
        if trace_id is not None:
            payload["trace_id"] = trace_id
        emit("workflow_done", run_id=graph_run_id, status="done")
        logger.info(
            "workflow_completed",
            graph_run_id=graph_run_id,
            trace_id=trace_id,
        )
        return payload
