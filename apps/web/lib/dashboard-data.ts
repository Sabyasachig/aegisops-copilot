export interface DashboardMetric {
  label: string;
  value: string;
  delta: string;
  tone: "positive" | "caution" | "critical" | "neutral";
}

export interface IncidentOverview {
  id: string;
  title: string;
  service: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  status: "triage" | "investigating" | "mitigating" | "resolved";
  owner: string;
  summary: string;
  updatedAt: string;
  nextAction: string;
}

export interface AgentStage {
  name: string;
  description: string;
  state: string;
  accent: string;
}

export const dashboardMetrics: DashboardMetric[] = [
  {
    label: "Active incidents",
    value: "3",
    delta: "1 escalated in the last 30 min",
    tone: "critical"
  },
  {
    label: "Agent completion rate",
    value: "94%",
    delta: "+6% from yesterday",
    tone: "positive"
  },
  {
    label: "Human approvals",
    value: "11",
    delta: "No unsafe action executed",
    tone: "neutral"
  },
  {
    label: "Mean triage time",
    value: "2.8 min",
    delta: "Faster than the target SLA",
    tone: "caution"
  }
];

export const incidentQueue: IncidentOverview[] = [
  {
    id: "INC-2081",
    title: "Billing callbacks are timing out for a subset of tenants",
    service: "billing",
    severity: "critical",
    status: "investigating",
    owner: "revenue-engineering",
    updatedAt: "2m ago",
    summary: "The queue is healthy, but callback retries are stacking behind a slow dependency.",
    nextAction: "Pause nonessential retries and validate ledger consistency before replay."
  },
  {
    id: "INC-2048",
    title: "Event ingest latency climbed 5x after deploy",
    service: "event-ingest",
    severity: "high",
    status: "triage",
    owner: "on-call-platform",
    updatedAt: "7m ago",
    summary: "Consumer lag increased immediately after the release window and needs correlation.",
    nextAction: "Pull deploy diff, broker metrics, and consumer lag to isolate the trigger."
  },
  {
    id: "INC-2093",
    title: "SSO sign-in error rate exceeded threshold",
    service: "auth",
    severity: "medium",
    status: "mitigating",
    owner: "identity-platform",
    updatedAt: "15m ago",
    summary: "The latest config update likely affected token validation for older clients.",
    nextAction: "Restore the last known good signing key after human approval."
  }
];

export const agentStages: AgentStage[] = [
  {
    name: "Assess",
    description: "Normalize incident context and surface the owning runbook.",
    state: "complete",
    accent: "from-cyan-400 to-sky-500"
  },
  {
    name: "Evidence",
    description: "Correlate logs, metrics, traces, and recent deployments.",
    state: "complete",
    accent: "from-emerald-400 to-teal-500"
  },
  {
    name: "Plan",
    description: "Draft the safest remediation path with explicit approval gates.",
    state: "running",
    accent: "from-amber-300 to-orange-500"
  },
  {
    name: "Package",
    description: "Produce the response summary and attach the trace artifacts.",
    state: "queued",
    accent: "from-fuchsia-400 to-pink-500"
  }
];

export const operatingPrinciples = [
  "Every high-risk action requires a human approval checkpoint.",
  "LangGraph owns the workflow state so each step remains explicit.",
  "LangSmith traces preserve the decision trail for review and tuning.",
  "The UI shows what the agents know, what they propose, and what they cannot do alone."
];
