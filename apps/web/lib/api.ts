import { incidentQueue, type IncidentOverview } from "./dashboard-data";

export interface ApiProviderInfo {
  provider: "groq" | "openai" | "anthropic";
  model_name: string;
  tracing_enabled: boolean;
}

export interface DashboardSnapshot {
  incidents: IncidentOverview[];
  provider: ApiProviderInfo | null;
}

function getApiBaseUrl() {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:4001";
}

export async function loadDashboardSnapshot(): Promise<DashboardSnapshot> {
  const apiBaseUrl = getApiBaseUrl();

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
      provider: providerPayload as ApiProviderInfo
    };
  } catch {
    return {
      incidents: incidentQueue,
      provider: null
    };
  }
}
