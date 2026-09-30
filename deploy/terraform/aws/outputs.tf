########################################
# Connection URL outputs — feed straight into AIOPS_* env vars.
########################################

output "database_url" {
  description = "Value for AIOPS_DATABASE_URL (SQLAlchemy asyncpg DSN, ssl=true)."
  value       = local.database_url
  sensitive   = true
}

output "redis_url" {
  description = "Value for AIOPS_REDIS_URL (application cache / SSE fan-out)."
  value       = local.redis_url
  sensitive   = true
}

output "celery_broker_url" {
  description = "Value for AIOPS_CELERY_BROKER_URL."
  value       = local.celery_broker_url
  sensitive   = true
}

output "celery_result_backend" {
  description = "Value for AIOPS_CELERY_RESULT_BACKEND."
  value       = local.celery_result_backend
  sensitive   = true
}

output "rate_limit_storage_uri" {
  description = "Value for AIOPS_RATE_LIMIT_STORAGE_URI."
  value       = local.rate_limit_storage_uri
  sensitive   = true
}

########################################
# Bare endpoint outputs — useful for observability / debugging.
########################################

output "postgres_endpoint" {
  description = "RDS Postgres endpoint hostname."
  value       = aws_db_instance.postgres.address
}

output "redis_primary_endpoint" {
  description = "ElastiCache Redis primary endpoint hostname."
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "postgres_security_group_id" {
  description = "Security group ID guarding Postgres — attach client SGs here."
  value       = aws_security_group.postgres.id
}

output "redis_security_group_id" {
  description = "Security group ID guarding Redis — attach client SGs here."
  value       = aws_security_group.redis.id
}

output "secrets_manager_arn" {
  description = "ARN of the Secrets Manager secret containing the AIOPS_* connection URLs."
  value       = aws_secretsmanager_secret.urls.arn
}

output "master_password" {
  description = "Postgres master password. Prefer reading from secrets_manager_arn."
  value       = random_password.master.result
  sensitive   = true
}
