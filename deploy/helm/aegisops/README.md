# AegisOps Copilot — Helm chart

Kubernetes packaging for AegisOps Copilot. Deploys three workloads (API,
Celery worker, Next.js web dashboard) plus optional in-cluster PostgreSQL
and Redis for development / demo use.

## Chart contents

| Resource | Purpose |
| --- | --- |
| `Deployment` `<release>-api` | FastAPI server. Readiness/liveness probes on `/api/health`. |
| `Service` `<release>-api` | ClusterIP fronting the API deployment. |
| `HorizontalPodAutoscaler` `<release>-api` | Optional CPU/memory-based autoscaler. |
| `PodDisruptionBudget` `<release>-api` | Optional; keeps at least one API replica alive during voluntary disruptions. |
| `Deployment` `<release>-worker` | Celery worker running the LangGraph incident workflow. |
| `HorizontalPodAutoscaler` `<release>-worker` | Optional CPU-based autoscaler. |
| `Deployment`, `Service`, `HPA`, `PDB` `<release>-web` | Next.js dashboard. |
| `Ingress` `<release>` | Optional TLS-terminated entry point for API + web. |
| `ConfigMap` `<release>-config` | All non-secret `AIOPS_*` env vars. |
| `Secret` `<release>-secret` | All sensitive `AIOPS_*` env vars — or reference an existing secret via `secret.existingSecret`. |
| `ServiceAccount` `<release>` | Shared by API and worker pods. |
| `StatefulSet` + `Service` `<release>-postgres` | Optional in-cluster Postgres (`postgres.enabled=true`). |
| `Deployment` + `Service` `<release>-redis` | Optional in-cluster Redis (`redis.enabled=true`). |

## Prerequisites

- Kubernetes ≥ 1.25
- Helm ≥ 3.11
- Container images published to a registry your cluster can pull from
  (defaults to `ghcr.io/sabyasachig/aegisops-*`)

## Quick start

```bash
# Lint locally
helm lint deploy/helm/aegisops

# Preview rendered manifests
helm template aegisops deploy/helm/aegisops \
  -f deploy/helm/aegisops/examples/values-dev.yaml

# Install into a demo namespace
helm install aegisops deploy/helm/aegisops \
  --namespace aegisops --create-namespace \
  -f deploy/helm/aegisops/examples/values-dev.yaml

# Verify /api/health responds 200
helm test aegisops -n aegisops
```

## Production checklist

1. **Point at managed data services.** Set `secret.data.databaseUrl`,
   `secret.data.redisUrl`, `secret.data.celeryBrokerUrl`,
   `secret.data.celeryResultBackend` at RDS / ElastiCache / Cloud SQL /
   Memorystore endpoints. Keep `postgres.enabled=false` and
   `redis.enabled=false`.
2. **Use an external secret manager.** Set `secret.create=false` and
   `secret.existingSecret=<name>` — deploy the secret separately via
   ExternalSecrets Operator, Sealed Secrets, or Vault Agent injection.
3. **Rotate defaults.** Never ship with the default
   `secret.data.jwtSecretKey` or `initialAdminPassword`.
4. **Enable Ingress and TLS.** Set `ingress.enabled=true`, configure the
   `cert-manager.io/cluster-issuer` annotation, and set `config.corsOrigins`
   / `config.publicBaseUrl` to your public URL.
5. **Right-size autoscalers.** Default HPA: API 2–10 pods @ 70% CPU, web
   2–5 pods @ 70% CPU. Worker autoscaling is off by default — enable it
   once you have historical load data.
6. **Wire observability.** Point `config.otelExporterOtlpEndpoint` at your
   OTLP collector; the API deployment already carries the standard
   `prometheus.io/scrape` annotations for the `/metrics` endpoint.

## Health-check probes

Both liveness and readiness probes on the API deployment target
`GET /api/health` (implemented by `aegisops_api.routers.health`), which
returns `200 {"status":"ok",...}` when Postgres, Redis, and the LLM
circuit breakers are healthy, or `200 {"status":"degraded",...}` otherwise.
Only network / process-level failures trigger a restart.

## Values reference

See [values.yaml](values.yaml) for the full list of tunable values.
