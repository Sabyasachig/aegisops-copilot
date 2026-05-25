# Product Plan

## Problem Statement

Small and mid-size platform teams lose time when incidents bounce between logs, dashboards, tickets, and Slack threads. The real work is not only answering questions; it is coordinating the next best action while preserving accountability.

## Product Goal

AegisOps Copilot helps the on-call engineer move from alert to response faster by combining multi-agent triage, evidence collection, mitigation planning, and human approval in one control plane.

## Primary Users

- SRE and platform engineers
- DevOps and infrastructure teams
- Engineering managers handling incident response
- Support and reliability leads coordinating escalation

## MVP Scope

- Incident dashboard with priority, service, owner, and action state
- Agent workflow that triages incidents and produces a mitigation draft
- Evidence and runbook summaries for each incident
- Human approval checkpoint before proposing risky actions
- Run history and traceability for every agent step

## V1 Enhancements

- Slack and PagerDuty integrations
- Real telemetry connectors for logs, metrics, and traces
- Ticketing sync with Jira or Linear
- Knowledge base retrieval from runbooks and past incidents
- LLM provider switching with Groq as the default testing path
- Feedback loop for response quality and run outcome scoring

## Success Metrics

- Lower mean time to acknowledge
- Lower mean time to mitigate
- Higher incident summary quality
- Higher percentage of incidents with reusable runbooks
- Lower time spent compiling post-incident reports

## Non-Functional Requirements

- Strong observability with LangSmith traces
- Deterministic state transitions in the graph
- Human-in-the-loop gates for sensitive operations
- Clear separation between domain logic, API, and UI
- Easy migration from in-memory demo data to Postgres and Redis
