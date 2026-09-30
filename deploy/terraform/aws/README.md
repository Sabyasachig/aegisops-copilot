# AegisOps Copilot — AWS Data Plane (Terraform)

Provisions the managed data services needed to run AegisOps Copilot on EKS:

* **RDS PostgreSQL 16** — primary application database (single instance or
  Multi-AZ)
* **ElastiCache Redis 7** — cache, Celery broker & result backend, SSE
  fan-out, and rate-limit storage (replication group with automatic
  failover)
* **Security groups** — ingress locked down to VPC CIDR blocks / additional
  security groups you pass in
* **AWS Secrets Manager secret** — stores the generated master password and
  the five ready-to-use `AIOPS_*` connection URLs

The module is intentionally minimal: it does **not** create a VPC, subnets,
NAT gateways, or IAM policies. You are expected to plug it into an existing
network module (e.g. `terraform-aws-modules/vpc/aws`) and pass in
`vpc_id` + `private_subnet_ids`.

## Usage

```hcl
module "aegisops_data" {
  source = "github.com/Sabyasachig/aegisops-copilot//deploy/terraform/aws?ref=main"

  name_prefix         = "aegisops-prod"
  vpc_id              = module.vpc.vpc_id
  private_subnet_ids  = module.vpc.private_subnets
  allowed_cidr_blocks = [module.vpc.vpc_cidr_block]

  # optional
  database_name         = "aegisops"
  master_username       = "aegisops"
  db_instance_class     = "db.t4g.medium"
  db_allocated_storage  = 50
  db_multi_az           = true

  redis_node_type       = "cache.t4g.small"
  redis_num_cache_nodes = 2   # primary + 1 replica
  redis_transit_encryption_enabled = true
}

# Connection URLs — sensitive, all resolved to AIOPS_* env vars.
output "database_url"           { value = module.aegisops_data.database_url,           sensitive = true }
output "redis_url"              { value = module.aegisops_data.redis_url,              sensitive = true }
output "celery_broker_url"      { value = module.aegisops_data.celery_broker_url,      sensitive = true }
output "celery_result_backend"  { value = module.aegisops_data.celery_result_backend,  sensitive = true }
output "rate_limit_storage_uri" { value = module.aegisops_data.rate_limit_storage_uri, sensitive = true }
output "secrets_manager_arn"    { value = module.aegisops_data.secrets_manager_arn }
```

Load the URLs into the Kubernetes `Secret` via
[ExternalSecrets](https://external-secrets.io/) targeting the ARN in
`secrets_manager_arn` — see
[`docs/managed-services.md`](../../../docs/managed-services.md) for the
full walkthrough.

## Requirements

| Provider | Version |
| -------- | ------- |
| `terraform` | `>= 1.5.0` |
| `hashicorp/aws` | `>= 5.0` |
| `hashicorp/random` | `>= 3.5` |

## Inputs

See [`variables.tf`](variables.tf) for the full list, including sensible
defaults for PostgreSQL 16 + Redis 7 on Graviton (`t4g`) instance types.

## Outputs

See [`outputs.tf`](outputs.tf). All connection URL outputs are marked
`sensitive = true`.

## Cost note

At the defaults (single `db.t4g.medium` Multi-AZ + 2× `cache.t4g.small`
Multi-AZ + 50 GiB storage + 7-day backups) the module runs at roughly
**$150 / month** in `us-east-1` as of 2026 pricing. Cross-check the
[AWS calculator](https://calculator.aws) for your region.

## What's NOT provisioned

* VPC / subnets / NAT — bring your own.
* IAM roles for EKS pods to reach Secrets Manager — use IRSA or Pod Identity.
* Read-replicas / cross-region backup — out of scope of the starter module.

Track any expansion of this module against future issues; keep it stable so
that upgrading to a managed data plane never requires code changes in the
application itself.
