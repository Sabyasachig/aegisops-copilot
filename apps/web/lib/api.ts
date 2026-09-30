import { incidentQueue, type IncidentOverview } from "./dashboard-data";

export interface ApiProviderInfo {
  provider: "groq" | "openai" | "anthropic";
  model_name: string;
  tracing_enabled: boolean;
}

export interface AuditLogEntry {
  id: string;
  actor: string;
  action: string;
  resource_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface DashboardSnapshot {
  incidents: IncidentOverview[];
  provider: ApiProviderInfo | null;
  auditLogs: AuditLogEntry[];
}

function getApiBaseUrl() {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:4001";
}

export async function loadDashboardSnapshot(): Promise<DashboardSnapshot> {
  const apiBaseUrl = getApiBaseUrl();

  const auditLogs = await loadRecentAuditLogs(apiBaseUrl);

  try {
    const [incidentsResponse, providerResponse] = await Promise.all([
      fetch(`${apiBaseUrl}/api/incidents`, { cache: "no-store" }),
      fetch(`${apiBaseUrl}/api/providers`, { cache: "no-store" })
    ]);

    if (!incidentsResponse.ok || !providerResponse.ok) {
      throw new Error("API snapshot request failed.");
    }

    const incidentsPayload = await incidentsResponse.json();
    const providerPayload = await providerResponse.json();

    return {
      incidents: Array.isArray(incidentsPayload.incidents) ? incidentsPayload.incidents : incidentQueue,
      provider: providerPayload as ApiProviderInfo,
      auditLogs
    };
  } catch {
    return {
      incidents: incidentQueue,
      provider: null,
      auditLogs
    };
  }
}

async function loadRecentAuditLogs(apiBaseUrl: string): Promise<AuditLogEntry[]> {
  try {
    const response = await fetch(`${apiBaseUrl}/api/audit?limit=10`, { cache: "no-store" });
    if (!response.ok) {
      return [];
    }
    const payload = await response.json();
    return Array.isArray(payload.audit_logs) ? (payload.audit_logs as AuditLogEntry[]) : [];
  } catch {
    return [];
  }
}
