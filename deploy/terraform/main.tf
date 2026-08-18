locals {
  network_name   = "${var.name_prefix}-vpc"
  subnet_name    = "${var.name_prefix}-subnet"
  cluster_name   = "${var.name_prefix}-gke"
  db_instance    = "${var.name_prefix}-pg"
  redis_instance = "${var.name_prefix}-redis"
  registry_repo  = "${var.name_prefix}-images"
  workload_sa    = "${var.name_prefix}-workload"
}

# Enable the APIs this stack needs. destroy_on_disable stays false so tearing
# down the stack does not disable APIs other resources in the project may use.
resource "google_project_service" "services" {
  for_each = toset([
    "compute.googleapis.com",
    "container.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "artifactregistry.googleapis.com",
    "servicenetworking.googleapis.com",
    "iam.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# --- Networking ---

resource "google_compute_network" "vpc" {
  name                    = local.network_name
  auto_create_subnetworks = false
  depends_on              = [google_project_service.services]
}

resource "google_compute_subnetwork" "subnet" {
  name          = local.subnet_name
  ip_cidr_range = "10.10.0.0/20"
  region        = var.region
  network       = google_compute_network.vpc.id

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.20.0.0/16"
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.30.0.0/20"
  }
  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# Private Services Access, required for private Cloud SQL and Memorystore.
resource "google_compute_global_address" "private_range" {
  name          = "${var.name_prefix}-psa"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "psa" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_range.name]
}

# --- GKE ---

resource "google_container_cluster" "primary" {
  name       = local.cluster_name
  location   = var.region
  network    = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.subnet.id

  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = false

  resource_labels = var.labels

  # Dataplane V2 enforces the Kubernetes NetworkPolicy objects the chart ships.
  datapath_provider = "ADVANCED_DATAPATH"

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  # Restrict control-plane access to an explicit allowlist. An empty list is
  # fail-closed: only Google-internal access is permitted until CIDRs are added.
  master_authorized_networks_config {
    dynamic "cidr_blocks" {
      for_each = var.master_authorized_networks
      content {
        cidr_block   = cidr_blocks.value.cidr_block
        display_name = cidr_blocks.value.display_name
      }
    }
  }

  release_channel {
    channel = "REGULAR"
  }

  depends_on = [google_project_service.services]
}

resource "google_service_account" "nodes" {
  account_id   = "${var.name_prefix}-nodes"
  display_name = "Cascade GKE nodes"
}

resource "google_container_node_pool" "primary" {
  name       = "${var.name_prefix}-pool"
  location   = var.region
  cluster    = google_container_cluster.primary.name
  node_count = var.gke_node_count

  node_config {
    machine_type    = var.gke_machine_type
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    labels          = var.labels
    image_type      = "COS_CONTAINERD"

    metadata = {
      disable-legacy-endpoints = "true"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

# --- Cloud SQL (Postgres) ---

resource "google_sql_database_instance" "postgres" {
  name             = local.db_instance
  database_version = var.postgres_version
  region           = var.region

  depends_on = [google_service_networking_connection.psa]

  settings {
    tier              = var.postgres_tier
    availability_type = "REGIONAL"
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }

    database_flags {
      name  = "log_connections"
      value = "on"
    }
    database_flags {
      name  = "log_disconnections"
      value = "on"
    }
    database_flags {
      name  = "log_checkpoints"
      value = "on"
    }
    database_flags {
      name  = "log_lock_waits"
      value = "on"
    }
    database_flags {
      name  = "log_temp_files"
      value = "0"
    }
  }

  deletion_protection = true
}

resource "google_sql_database" "cascade" {
  name     = "cascade"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "cascade" {
  name     = "cascade"
  instance = google_sql_database_instance.postgres.name
  # The password is created out of band and stored in Secret Manager; this reads
  # it rather than generating it inline so it never lands in state as plaintext.
  password = var.postgres_password
}

variable "postgres_password" {
  type        = string
  description = "Password for the cascade Postgres user."
  sensitive   = true
}

# --- Memorystore (Redis) ---

resource "google_redis_instance" "cache" {
  name               = local.redis_instance
  tier               = "STANDARD_HA"
  memory_size_gb     = var.redis_memory_gb
  region             = var.region
  authorized_network = google_compute_network.vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  redis_version      = "REDIS_7_0"

  depends_on = [google_service_networking_connection.psa]
}

# --- Artifact Registry ---

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = local.registry_repo
  format        = "DOCKER"
  description   = "Cascade container images"
  depends_on    = [google_project_service.services]
}

# --- Workload Identity: bind a GSA to the in-cluster KSA ---

resource "google_service_account" "workload" {
  account_id   = local.workload_sa
  display_name = "Cascade workload"
}

resource "google_service_account_iam_member" "workload_identity" {
  service_account_id = google_service_account.workload.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.kubernetes_namespace}/${var.kubernetes_service_account}]"
}

resource "google_project_iam_member" "workload_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.workload.email}"
}
