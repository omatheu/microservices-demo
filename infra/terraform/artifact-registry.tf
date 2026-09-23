resource "google_artifact_registry_repository" "experiment" {
  count = var.allow_artifact_registry_creation ? 1 : 0

  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_registry_repository_id
  description   = "Short-lived immutable images for the Online Boutique TCC experiment"
  format        = "DOCKER"

  cleanup_policy_dry_run = false
  deletion_policy        = "DELETE"

  vulnerability_scanning_config {
    enablement_config = "DISABLED"
  }

  cleanup_policies {
    id     = "delete-versions-after-retention-window"
    action = "DELETE"

    condition {
      tag_state  = "ANY"
      older_than = "${var.artifact_retention_days * 86400}s"
    }
  }

  cleanup_policies {
    id     = "keep-minimum-recent-versions"
    action = "KEEP"

    most_recent_versions {
      keep_count = var.artifact_minimum_versions_to_keep
    }
  }

  labels = {
    application = "online-boutique"
    purpose     = "tcc-experiment"
    managed-by  = "terraform"
  }

  depends_on = [google_project_service.required]
}
