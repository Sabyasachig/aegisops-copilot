########################################
# Example wiring for the aegisops-data Terraform module.
# Copy to terraform.tfvars and edit values.
########################################

name_prefix         = "aegisops-prod"
vpc_id              = "vpc-0123456789abcdef0"
private_subnet_ids  = ["subnet-0aaa", "subnet-0bbb"]
allowed_cidr_blocks = ["10.0.0.0/16"]

# Postgres
db_instance_class        = "db.t4g.medium"
db_allocated_storage     = 50
db_multi_az              = true
db_backup_retention_days = 15

# Redis
redis_node_type       = "cache.t4g.small"
redis_num_cache_nodes = 2
redis_transit_encryption_enabled = true

tags = {
  Environment = "production"
  Owner       = "platform"
}
