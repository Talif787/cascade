output "cluster_name" {
  value       = google_container_cluster.primary.name
  description = "Name of the GKE cluster."
}

output "cluster_endpoint" {
  value       = google_container_cluster.primary.endpoint
  description = "GKE control-plane endpoint."
  sensitive   = true
}

output "postgres_connection_name" {
  value       = google_sql_database_instance.postgres.connection_name
  description = "Cloud SQL connection name for the Auth Proxy or connector."
}

output "postgres_private_ip" {
  value       = google_sql_database_instance.postgres.private_ip_address
  description = "Private IP of the Postgres instance."
}

output "redis_host" {
  value       = google_redis_instance.cache.host
  description = "Memorystore Redis host."
}

output "redis_port" {
  value       = google_redis_instance.cache.port
  description = "Memorystore Redis port."
}

output "artifact_registry_repo" {
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
  description = "Base path for pushing container images."
}

output "workload_service_account" {
  value       = google_service_account.workload.email
  description = "GSA email bound to the in-cluster KSA via Workload Identity."
}
