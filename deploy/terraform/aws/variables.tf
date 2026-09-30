########################################
# Required
########################################

variable "name_prefix" {
  description = "Prefix applied to every resource name (e.g. \"aegisops-prod\")."
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC hosting the EKS cluster and the data plane."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs (at least two AZs) where RDS + ElastiCache will live."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "At least two private subnets in different AZs are required for Multi-AZ RDS and Redis replication."
  }
}

variable "allowed_cidr_blocks" {
  description = "CIDR blocks allowed to reach Postgres (5432) and Redis (6379). Typically the VPC CIDR of the EKS node group."
  type        = list(string)
}

########################################
# Postgres (RDS)
########################################

variable "database_name" {
  description = "Initial application database name."
  type        = string
  default     = "aegisops"
}

variable "master_username" {
  description = "Postgres master username."
  type        = string
  default     = "aegisops"
}

variable "db_engine_version" {
  description = "PostgreSQL engine version."
  type        = string
  default     = "16.4"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.medium"
}

variable "db_allocated_storage" {
  description = "Allocated storage in GiB (gp3)."
  type        = number
  default     = 50
}

variable "db_max_allocated_storage" {
  description = "Storage autoscaling ceiling in GiB. Set equal to allocated_storage to disable autoscaling."
  type        = number
  default     = 200
}

variable "db_multi_az" {
  description = "Whether to run RDS in Multi-AZ mode."
  type        = bool
  default     = true
}

variable "db_backup_retention_days" {
  description = "How many days of PITR backups to retain."
  type        = number
  default     = 15
}

variable "db_deletion_protection" {
  description = "Prevent the DB from being deleted."
  type        = bool
  default     = true
}

variable "db_skip_final_snapshot" {
  description = "Skip the final snapshot on destroy. Set to false in production."
  type        = bool
  default     = false
}

variable "db_apply_immediately" {
  description = "Apply modifications immediately rather than on the next maintenance window."
  type        = bool
  default     = false
}

########################################
# Redis (ElastiCache)
########################################

variable "redis_engine_version" {
  description = "ElastiCache Redis engine version."
  type        = string
  default     = "7.1"
}

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.small"
}

variable "redis_num_cache_nodes" {
  description = "Total number of cache nodes (1 primary + N-1 replicas). Set to >= 2 for Multi-AZ automatic failover."
  type        = number
  default     = 2
}

variable "redis_transit_encryption_enabled" {
  description = "Enable in-transit encryption (rediss://). Required for compliance in most environments."
  type        = bool
  default     = true
}

variable "redis_at_rest_encryption_enabled" {
  description = "Enable at-rest encryption."
  type        = bool
  default     = true
}

variable "redis_snapshot_retention_days" {
  description = "How many days of Redis snapshots to keep."
  type        = number
  default     = 7
}

########################################
# Meta
########################################

variable "tags" {
  description = "Tags applied to every resource created by this module."
  type        = map(string)
  default     = {}
}
