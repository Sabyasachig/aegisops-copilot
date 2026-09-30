########################################
# Locals
########################################

locals {
  common_tags = merge(
    {
      "app.kubernetes.io/name"       = "aegisops"
      "app.kubernetes.io/managed-by" = "terraform"
      "aegisops.io/component"        = "data-plane"
    },
    var.tags,
  )

  db_port    = 5432
  redis_port = 6379
}

########################################
# Random master password
########################################

resource "random_password" "master" {
  length           = 32
  special          = true
  # Exclude characters that are ambiguous in shell/URL contexts.
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

########################################
# Security groups
########################################

resource "aws_security_group" "postgres" {
  name        = "${var.name_prefix}-postgres"
  description = "AegisOps Postgres ingress from EKS node CIDRs."
  vpc_id      = var.vpc_id
  tags        = local.common_tags
}

resource "aws_security_group_rule" "postgres_ingress" {
  security_group_id = aws_security_group.postgres.id
  type              = "ingress"
  protocol          = "tcp"
  from_port         = local.db_port
  to_port           = local.db_port
  cidr_blocks       = var.allowed_cidr_blocks
  description       = "Postgres from AegisOps clients"
}

resource "aws_security_group_rule" "postgres_egress" {
  security_group_id = aws_security_group.postgres.id
  type              = "egress"
  protocol          = "-1"
  from_port         = 0
  to_port           = 0
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "Allow all egress"
}

resource "aws_security_group" "redis" {
  name        = "${var.name_prefix}-redis"
  description = "AegisOps Redis ingress from EKS node CIDRs."
  vpc_id      = var.vpc_id
  tags        = local.common_tags
}

resource "aws_security_group_rule" "redis_ingress" {
  security_group_id = aws_security_group.redis.id
  type              = "ingress"
  protocol          = "tcp"
  from_port         = local.redis_port
  to_port           = local.redis_port
  cidr_blocks       = var.allowed_cidr_blocks
  description       = "Redis from AegisOps clients"
}

resource "aws_security_group_rule" "redis_egress" {
  security_group_id = aws_security_group.redis.id
  type              = "egress"
  protocol          = "-1"
  from_port         = 0
  to_port           = 0
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "Allow all egress"
}

########################################
# RDS Postgres
########################################

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db"
  subnet_ids = var.private_subnet_ids
  tags       = local.common_tags
}

resource "aws_db_instance" "postgres" {
  identifier              = "${var.name_prefix}-postgres"
  engine                  = "postgres"
  engine_version          = var.db_engine_version
  instance_class          = var.db_instance_class

  allocated_storage       = var.db_allocated_storage
  max_allocated_storage   = var.db_max_allocated_storage
  storage_type            = "gp3"
  storage_encrypted       = true

  db_name                 = var.database_name
  username                = var.master_username
  password                = random_password.master.result
  port                    = local.db_port

  db_subnet_group_name    = aws_db_subnet_group.this.name
  vpc_security_group_ids  = [aws_security_group.postgres.id]
  publicly_accessible     = false

  multi_az                = var.db_multi_az
  backup_retention_period = var.db_backup_retention_days
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"
  copy_tags_to_snapshot   = true

  deletion_protection     = var.db_deletion_protection
  skip_final_snapshot     = var.db_skip_final_snapshot
  final_snapshot_identifier = var.db_skip_final_snapshot ? null : "${var.name_prefix}-postgres-final"

  apply_immediately       = var.db_apply_immediately

  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  auto_minor_version_upgrade = true

  tags = local.common_tags
}

########################################
# ElastiCache Redis
########################################

resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name_prefix}-redis"
  subnet_ids = var.private_subnet_ids
  tags       = local.common_tags
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "${var.name_prefix}-redis"
  description                = "AegisOps cache, Celery broker/result, SSE fan-out, rate-limit storage."
  engine                     = "redis"
  engine_version             = var.redis_engine_version
  node_type                  = var.redis_node_type
  num_cache_clusters         = var.redis_num_cache_nodes
  port                       = local.redis_port

  automatic_failover_enabled = var.redis_num_cache_nodes >= 2
  multi_az_enabled           = var.redis_num_cache_nodes >= 2

  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [aws_security_group.redis.id]

  at_rest_encryption_enabled = var.redis_at_rest_encryption_enabled
  transit_encryption_enabled = var.redis_transit_encryption_enabled

  snapshot_retention_limit   = var.redis_snapshot_retention_days
  snapshot_window            = "02:00-03:00"
  maintenance_window         = "mon:03:00-mon:04:00"

  apply_immediately          = false

  tags = local.common_tags
}

########################################
# Secrets Manager — stores connection URLs so ExternalSecrets can sync them.
########################################

locals {
  redis_scheme = var.redis_transit_encryption_enabled ? "rediss" : "redis"

  # Assemble the AIOPS_* env var URLs. Postgres uses the asyncpg SQLAlchemy
  # driver plus ssl=true so asyncpg validates the RDS certificate against the
  # system CA bundle.
  database_url = format(
    "postgresql+asyncpg://%s:%s@%s:%d/%s?ssl=true",
    var.master_username,
    urlencode(random_password.master.result),
    aws_db_instance.postgres.address,
    local.db_port,
    var.database_name,
  )

  redis_endpoint = aws_elasticache_replication_group.redis.primary_endpoint_address

  redis_url              = "${local.redis_scheme}://${local.redis_endpoint}:${local.redis_port}/0"
  celery_broker_url      = "${local.redis_scheme}://${local.redis_endpoint}:${local.redis_port}/1"
  celery_result_backend  = "${local.redis_scheme}://${local.redis_endpoint}:${local.redis_port}/2"
  rate_limit_storage_uri = "${local.redis_scheme}://${local.redis_endpoint}:${local.redis_port}/3"

  secret_payload = jsonencode({
    AIOPS_DATABASE_URL           = local.database_url
    AIOPS_REDIS_URL              = local.redis_url
    AIOPS_CELERY_BROKER_URL      = local.celery_broker_url
    AIOPS_CELERY_RESULT_BACKEND  = local.celery_result_backend
    AIOPS_RATE_LIMIT_STORAGE_URI = local.rate_limit_storage_uri
    # The master password is included so external tooling (dbmate, psql,
    # pgbench) can reach the database directly without deriving it from the
    # full URL.
    POSTGRES_MASTER_PASSWORD     = random_password.master.result
  })
}

resource "aws_secretsmanager_secret" "urls" {
  name        = "${var.name_prefix}/data-urls"
  description = "AegisOps data-plane connection URLs (AIOPS_* env vars)."
  tags        = local.common_tags
}

resource "aws_secretsmanager_secret_version" "urls" {
  secret_id     = aws_secretsmanager_secret.urls.id
  secret_string = local.secret_payload
}
