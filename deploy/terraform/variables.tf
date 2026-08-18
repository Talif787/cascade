variable "project_id" {
  type        = string
  description = "The GCP project ID to deploy into."
}

variable "region" {
  type        = string
  description = "The GCP region for regional resources."
  default     = "us-central1"
}

variable "name_prefix" {
  type        = string
  description = "Prefix applied to created resource names."
  default     = "cascade"
}

variable "gke_node_count" {
  type        = number
  description = "Number of nodes per zone in the primary node pool."
  default     = 2
}

variable "gke_machine_type" {
  type        = string
  description = "Machine type for GKE nodes."
  default     = "e2-standard-2"
}

variable "postgres_tier" {
  type        = string
  description = "Cloud SQL machine tier for the Postgres instance."
  default     = "db-custom-2-7680"
}

variable "postgres_version" {
  type        = string
  description = "Cloud SQL Postgres version."
  default     = "POSTGRES_16"
}

variable "redis_memory_gb" {
  type        = number
  description = "Memorystore Redis capacity in GB."
  default     = 1
}

variable "kubernetes_namespace" {
  type        = string
  description = "Namespace the workload runs in, for Workload Identity binding."
  default     = "cascade"
}

variable "kubernetes_service_account" {
  type        = string
  description = "KSA name the workload runs as, for Workload Identity binding."
  default     = "cascade"
}

variable "labels" {
  type        = map(string)
  description = "Labels applied to created resources."
  default = {
    app        = "cascade"
    managed-by = "terraform"
  }
}
variable "master_authorized_networks" {
  type = list(object({
    cidr_block   = string
    display_name = string
  }))
  description = "CIDR blocks allowed to reach the GKE control plane. Empty is fail-closed (Google-internal access only)."
  default     = []
}
