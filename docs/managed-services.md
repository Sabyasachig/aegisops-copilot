# Managed Database & Cache (Cloud-Ready) — Migration Guide

_Issue #21 — Phase 5 (Infrastructure & CI/CD)_

This document explains how to move an AegisOps Copilot deployment from the
Docker Compose / in-cluster StatefulSet defaults to fully-managed cloud data
services (AWS RDS + ElastiCache or GCP Cloud SQL + Memorystore) **without
any application code changes**.

The application already treats every dependency as a URL surfaced through an
`AIOPS_*` environment variable, so the migration only requires:

1. Provisioning the managed services (Terraform module provided).
2. Rotating the connection URLs in the Kubernetes `Secret` (or an
   `ExternalSecrets` / SealedSecrets / Vault-backed secret).
3. Disabling the in-cluster Postgres / Redis sub-charts in `values.yaml`.

Everything else — application code, Helm templates, container images — stays
untouched.

---

## 1. Environment contract (source of truth)

The API and Celery worker read the following environment variables at
startup (all prefixed `AIOPS_` because of `pydantic-settings`
`env_prefix="AIOPS_"`):

| Variable                          | Purpose                                        | Managed service field                |
| --------------------------------- | ---------------------------------------------- | ------------------------------------ |
| `AIOPS_DATABASE_URL`              | Primary Postgres DSN (SQLAlchemy async driver) | RDS / Cloud SQL primary endpoint     |
| `AIOPS_REDIS_URL`                 | Application Redis cache / SSE fan-out          | ElastiCache / Memorystore primary    |
| `AIOPS_CELERY_BROKER_URL`         | Celery task broker (Redis)                     | ElastiCache / Memorystore, DB `/1`   |
| `AIOPS_CELERY_RESULT_BACKEND`     | Celery result store (Redis)                    | ElastiCache / Memorystore, DB `/2`   |
| `AIOPS_RATE_LIMIT_STORAGE_URI`    | slowapi rate-limit storage (Redis)             | ElastiCache / Memorystore, DB `/3`   |

**Contract:** switching data-tier providers requires only updates to these
five URLs. No code changes, no rebuild.

### DSN formats

* Postgres — must use the SQLAlchemy async driver:
  ```
  postgresql+asyncpg://<user>:<password>@<host>:5432/<database>
  ```
  For RDS/Cloud SQL with SSL, append the driver query string:
  ```
  postgresql+asyncpg://user:pw@host:5432/aegisops?ssl=true
  ```
  With `asyncpg`, `ssl=true` triggers TLS with system CA bundle validation.

* Redis — standard `redis://` (or `rediss://` for TLS):
  ```
  redis://<host>:6379/<db_index>
  rediss://<host>:6379/<db_index>   # ElastiCache with encryption in transit
  ```

---

## 2. AWS migration path — RDS PostgreSQL + ElastiCache Redis

### 2.1 Recommended sizing (starter)

| Service                | Instance class      | Storage | Multi-AZ | Notes                             |
| ---------------------- | ------------------- | ------- | -------- | --------------------------------- |
| RDS PostgreSQL 16      | `db.t4g.medium`     | 50 GiB gp3 | Yes   | 15-day PITR retention             |
| ElastiCache Redis 7    | `cache.t4g.small`   | —       | Yes (replication group) | 1 primary + 1 replica |

Scale up (`db.m6g.large`, `cache.m6g.large`) once you have ~100 rps sustained
API traffic.

### 2.2 Provision via Terraform

A ready-to-use Terraform module is shipped under
[`deploy/terraform/aws/`](../deploy/terraform/aws) — see
[deploy/terraform/aws/README.md](../deploy/terraform/aws/README.md) for a
walkthrough.

Minimal snippet:

```hcl
module "aegisops_data" {
  source = "../../deploy/terraform/aws"

  name_prefix        = "aegisops-prod"
  vpc_id             = aws_vpc.main.id
  private_subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
  allowed_cidr_blocks = [aws_vpc.main.cidr_block]

  database_name   = "aegisops"
  master_username = "aegisops"
  # master_password is generated and stored in AWS Secrets Manager

  redis_num_cache_nodes = 2   # primary + 1 replica
}

output "database_url" {
  value     = module.aegisops_data.database_url
  sensitive = true
}

output "redis_url" {
  value     = module.aegisops_data.redis_url
  sensitive = true
}
```

The module emits four SecretsManager-backed outputs:

* `database_url` — full `postgresql+asyncpg://…` DSN
* `redis_url` — `rediss://…/0`
* `celery_broker_url` — `rediss://…/1`
* `celery_result_backend` — `rediss://…/2`
* `rate_limit_storage_uri` — `rediss://…/3`

### 2.3 Wire into the Kubernetes Secret

Fetch the outputs from Terraform and load them into the AegisOps Secret. The
recommended production path is to keep secrets in AWS Secrets Manager and
sync them into Kubernetes via
[ExternalSecrets](https://external-secrets.io/):

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: aegisops-data
  namespace: aegisops
spec:
  secretStoreRef: {name: aws-secrets-manager, kind: SecretStore}
  target:
    name: aegisops-data  # <-- referenced by Helm values.secret.existingSecret
  data:
    - {secretKey: AIOPS_DATABASE_URL,           remoteRef: {key: aegisops/database_url}}
    - {secretKey: AIOPS_REDIS_URL,              remoteRef: {key: aegisops/redis_url}}
    - {secretKey: AIOPS_CELERY_BROKER_URL,      remoteRef: {key: aegisops/celery_broker_url}}
    - {secretKey: AIOPS_CELERY_RESULT_BACKEND,  remoteRef: {key: aegisops/celery_result_backend}}
    - {secretKey: AIOPS_RATE_LIMIT_STORAGE_URI, remoteRef: {key: aegisops/rate_limit_storage_uri}}
    - {secretKey: AIOPS_JWT_SECRET_KEY,         remoteRef: {key: aegisops/jwt_secret_key}}
    - {secretKey: AIOPS_INITIAL_ADMIN_PASSWORD, remoteRef: {key: aegisops/initial_admin_password}}
```

Then install the chart pointing at that secret and turn OFF the in-cluster
data services:

```yaml
# values-production-aws.yaml
secret:
  create: false
  existingSecret: aegisops-data

postgres:
  enabled: false      # use RDS

redis:
  enabled: false      # use ElastiCache
```

```bash
helm upgrade --install aegisops deploy/helm/aegisops \
  -f values-production-aws.yaml \
  -n aegisops --create-namespace
```

### 2.4 Networking

RDS + ElastiCache must live in **private** subnets. The Terraform module
creates dedicated security groups that allow ingress only from the CIDR
blocks passed via `allowed_cidr_blocks` (typically the EKS node-group VPC
CIDR). The EKS worker nodes therefore reach the data plane over the VPC
private network — no public exposure.

### 2.5 Alembic migrations

Run migrations as a one-off Job before rolling out the API deployment:

```bash
kubectl run alembic-upgrade --rm -i --restart=Never \
  --image=ghcr.io/sabyasachig/aegisops-api:0.1.0 \
  --env AIOPS_DATABASE_URL="$(kubectl -n aegisops get secret aegisops-data \
      -o jsonpath='{.data.AIOPS_DATABASE_URL}' | base64 -d)" \
  --command -- alembic upgrade head
```

Or wire it into the Helm chart as a `pre-install,pre-upgrade` hook Job (see
"future work" below).

---

## 3. GCP migration path — Cloud SQL + Memorystore

### 3.1 Recommended sizing (starter)

| Service                 | Tier                        | Storage  | HA          | Notes                              |
| ----------------------- | --------------------------- | -------- | ----------- | ---------------------------------- |
| Cloud SQL PostgreSQL 16 | `db-custom-2-7680`          | 50 GiB SSD | Regional  | Automatic backup + PITR            |
| Memorystore for Redis 7 | Basic → Standard HA         | 1 GiB    | Standard HA | Same-region single or multi-zone   |

### 3.2 Provision via `gcloud`

```bash
# Cloud SQL
gcloud sql instances create aegisops-prod \
  --database-version=POSTGRES_16 \
  --cpu=2 --memory=7680MB \
  --region=us-central1 \
  --availability-type=REGIONAL \
  --storage-size=50GB --storage-type=SSD \
  --backup-start-time=03:00

gcloud sql databases create aegisops --instance=aegisops-prod
gcloud sql users create aegisops --instance=aegisops-prod \
  --password="$(openssl rand -base64 32)"

# Memorystore
gcloud redis instances create aegisops-prod \
  --tier=STANDARD_HA \
  --size=1 \
  --region=us-central1 \
  --redis-version=redis_7_0 \
  --transit-encryption-mode=SERVER_AUTHENTICATION
```

### 3.3 Connect from GKE

Two supported patterns:

1. **Private IP + VPC peering** _(recommended)_ — Cloud SQL and Memorystore
   both offer private IP. Peer the GKE VPC with the services' producer VPC
   and connect directly:
   ```
   postgresql+asyncpg://aegisops:pw@10.20.0.5:5432/aegisops?ssl=true
   rediss://10.30.0.6:6379/0
   ```

2. **Cloud SQL Auth Proxy sidecar** — inject the proxy as a sidecar in the
   `api` and `worker` Deployments and connect to `127.0.0.1:5432`. Set
   `AIOPS_DATABASE_URL="postgresql+asyncpg://aegisops:pw@127.0.0.1:5432/aegisops"`.
   Add the sidecar via `api.extraContainers` in a follow-up chart version, or
   use a per-Pod patch until then.

### 3.4 Secret Manager + ExternalSecrets

Same pattern as AWS but pointing at Google Secret Manager:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata: {name: gcp-secret-manager, namespace: aegisops}
spec:
  provider:
    gcpsm:
      projectID: my-gcp-project
      auth: {workloadIdentity: {clusterLocation: us-central1, clusterName: aegisops, serviceAccountRef: {name: external-secrets}}}
```

Then reference `aegisops-data` from `values.secret.existingSecret` exactly as
in the AWS flow.

---

## 4. Cutover checklist

Regardless of provider, follow this order:

1. **Provision** managed Postgres + Redis in a private subnet/VPC.
2. **Restore** the current Compose/StatefulSet data. For Postgres:
   ```bash
   pg_dump -h old-host -U aegisops aegisops | \
     psql -h <rds-endpoint> -U aegisops aegisops
   ```
   Redis is a cache — no restore required; it will refill from the API.
3. **Rotate secrets**: put the new URLs into AWS Secrets Manager / GCP
   Secret Manager, sync into Kubernetes via ExternalSecrets, and set
   `secret.existingSecret` on the Helm release.
4. **Disable in-cluster data services** in `values.yaml`
   (`postgres.enabled=false`, `redis.enabled=false`).
5. **Run migrations**: `alembic upgrade head` as a one-off Job.
6. **Deploy** (`helm upgrade --install ...`). Both `api` and `worker` pick up
   the new URLs from `envFrom.secretRef` — no code redeploy is needed for
   individual URL rotation later.
7. **Verify** `/api/health` returns 200 and end-to-end incident execution
   flows still work.
8. **Decommission** the in-cluster Postgres PVC after a 7-day observation
   window (`kubectl delete pvc pgdata-aegisops-postgres-0`).

---

## 5. Cost estimates (2026 pricing, rough)

| Provider | Compute (db+redis)                                 | Storage | Approx / month |
| -------- | -------------------------------------------------- | ------- | -------------- |
| AWS      | `db.t4g.medium` Multi-AZ + `cache.t4g.small` × 2   | 50 GiB  | ≈ $150         |
| GCP      | `db-custom-2-7680` Regional + Memorystore 1 GiB HA | 50 GiB  | ≈ $170         |

Cross-check with the [AWS](https://calculator.aws) and
[GCP](https://cloud.google.com/products/calculator) calculators — pricing
drifts over time.

---

## 6. Future work

* [ ] Helm hook Job that runs `alembic upgrade head` on `pre-install` /
      `pre-upgrade` — currently manual, tracked as follow-up.
* [ ] Cloud SQL Auth Proxy sidecar as an opt-in Helm value
      (`api.extraContainers`).
* [ ] GCP-equivalent Terraform module under `deploy/terraform/gcp/`.
* [ ] IAM-based DB auth (RDS IAM auth, Cloud SQL IAM auth) to avoid rotating
      static passwords.
