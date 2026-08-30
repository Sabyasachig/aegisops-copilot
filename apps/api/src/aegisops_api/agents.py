from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from time import perf_counter
from typing import NotRequired, TypedDict
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from langsmith import traceable
from opentelemetry import trace

from .llm import call_with_fallback
from .logging_config import bind_log_context, get_logger
from .metrics import add_llm_tokens
from .models import Incident, LLMProvider
from .tracing import get_current_trace_id

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)

# Process-local checkpoint store — persists graph state for human-in-the-loop resume.
_approval_checkpointer = MemorySaver()


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
    thread_id: NotRequired[str]  # present when status == "needs_human"


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
    provider: str,
    model_name: str | None,
) -> str:
    started = perf_counter()
    logger.info("llm_call_started", node=role)
    messages = [
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
    with tracer.start_as_current_span(
        "llm.call",
        attributes={
            "ai.provider": provider,
            "ai.node": role,
            "incident.id": state["incident_id"],
        },
    ):
        response, used_provider = call_with_fallback(messages, provider, model_name)

    content = getattr(response, "content", "")
    if isinstance(content, list):
        content = " ".join(str(item) for item in content)
    token_total = _extract_total_tokens(response)
    if token_total is not None:
        add_llm_tokens(token_total, provider=used_provider)
    duration_ms = round((perf_counter() - started) * 1000, 2)
    logger.info("llm_call_completed", node=role, duration_ms=duration_ms, used_provider=used_provider)
    return str(content).strip() or f"{role} produced no textual response."


@lru_cache(maxsize=8)
def build_incident_graph(provider: LLMProvider = "groq", model_name: str | None = None):
    def assess(state: IncidentOpsState) -> dict[str, str]:
        logger.info("node_started", node="assess")
        runbook_text = _generate_role_output(
            "assess",
            "You are the triage agent. Produce a concise risk summary, owner guess, and immediate action.",
            state,
            provider,
            model_name,
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
            provider,
            model_name,
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
            provider,
            model_name,
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
    *,
    resume_approved: bool | None = None,
    resume_thread_id: str | None = None,
) -> IncidentOpsResult:
    def emit(event: str, **payload: str) -> None:
        if event_emitter is not None:
            event_emitter(event, payload)

    # On resume, reuse the original thread_id so the checkpointer can locate
    # the saved graph state.  On a fresh run, derive thread_id from graph_run_id.
    is_resume = resume_approved is not None and resume_thread_id is not None
    graph_run_id = resume_thread_id or f"graph_{uuid4().hex}"

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
        logger.info("workflow_started", provider=provider, model_name=model_name,
                    trace_id=trace_id, is_resume=is_resume)

        # ── Node definitions (closures over graph_run_id / emit) ─────────────

        def assess(state: IncidentOpsState) -> dict[str, str]:
            logger.info("node_started", node="assess")
            emit("node_started", node="assess", run_id=graph_run_id)
            with tracer.start_as_current_span("incident.node.assess"):
                runbook_text = _generate_role_output(
                    "assess",
                    "You are the triage agent. Produce a concise risk summary, owner guess, and immediate action.",
                    state,
                    provider,
                    model_name,
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
                    provider,
                    model_name,
                )
            result = {
                "evidence": evidence_text,
                "next_action": f"Correlate incident {state['incident_id']} against logs, traces, and deployment metadata.",
            }
            logger.info("node_completed", node="evidence")
            emit("node_completed", node="evidence", run_id=graph_run_id)
            return result

        def human_review(state: IncidentOpsState) -> dict[str, str]:
            """Pause execution; engineer must approve before response is drafted."""
            logger.info("node_started", node="human_review")
            emit("node_started", node="human_review", run_id=graph_run_id)
            # interrupt() checkpoints state and raises GraphInterrupt on first pass.
            # On resume, Command(resume=value) is returned here.
            approved = interrupt({
                "message": "Approve to proceed with response drafting, or reject to abort.",
                "evidence": state.get("evidence", ""),
                "runbook": state.get("runbook", ""),
            })
            logger.info("node_completed", node="human_review", approved=approved)
            emit("node_completed", node="human_review", run_id=graph_run_id)
            # Sentinel tells the conditional edge to skip to END on rejection.
            return {} if approved else {"next_action": "__REJECTED__"}

        def draft_response(state: IncidentOpsState) -> dict[str, str]:
            logger.info("node_started", node="response")
            emit("node_started", node="response", run_id=graph_run_id)
            with tracer.start_as_current_span("incident.node.response"):
                response_text = _generate_role_output(
                    "response",
                    "You are the mitigation agent. Draft the safest response plan and explicitly state what requires approval.",
                    state,
                    provider,
                    model_name,
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

        def _route_after_review(state: IncidentOpsState) -> str:
            return "__end__" if state.get("next_action") == "__REJECTED__" else "response"

        # ── Graph assembly with checkpointer ──────────────────────────────────

        graph = StateGraph(IncidentOpsState)
        graph.add_node("assess", assess)
        graph.add_node("evidence", gather_evidence)
        graph.add_node("human_review", human_review)
        graph.add_node("response", draft_response)
        graph.add_node("package", package_outcome)
        graph.add_edge(START, "assess")
        graph.add_edge("assess", "evidence")
        graph.add_edge("evidence", "human_review")
        graph.add_conditional_edges(
            "human_review",
            _route_after_review,
            {"response": "response", "__end__": END},
        )
        graph.add_edge("response", "package")
        graph.add_edge("package", END)
        compiled_graph = graph.compile(checkpointer=_approval_checkpointer)

        config: dict = {"configurable": {"thread_id": graph_run_id}}

        try:
            if is_resume:
                result = compiled_graph.invoke(Command(resume=resume_approved), config=config)
            else:
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
                    },
                    config=config,
                )
        except GraphInterrupt:
            logger.info("workflow_needs_human", graph_run_id=graph_run_id)
            emit("approval_required", run_id=graph_run_id)
            return {
                "graph_run_id": graph_run_id,
                "status": "needs_human",
                "thread_id": graph_run_id,
                "summary": "Awaiting human approval before response drafting.",
                "next_action": "Approve or reject via POST /api/runs/{run_id}/approve or /reject.",
            }

        # ── Result packaging ──────────────────────────────────────────────────

        if result.get("next_action") == "__REJECTED__":
            workflow_status = "rejected"
            emit("workflow_rejected", run_id=graph_run_id, status="rejected")
        else:
            workflow_status = "done"
            emit("workflow_done", run_id=graph_run_id, status="done")

        payload: IncidentOpsResult = {
            "graph_run_id": graph_run_id,
            "status": workflow_status,
            "summary": result.get("response_draft") or result.get("summary", ""),
            "next_action": result.get("next_action", "Await human approval"),
        }
        if trace_id is not None:
            payload["trace_id"] = trace_id
        logger.info("workflow_completed", graph_run_id=graph_run_id,
                    status=workflow_status, trace_id=trace_id)
        return payload
