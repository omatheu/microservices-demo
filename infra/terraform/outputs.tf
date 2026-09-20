output "cluster_name" {
  description = "GKE cluster name."
  value       = google_container_cluster.experiment.name
}

output "cluster_region" {
  description = "GKE cluster region."
  value       = google_container_cluster.experiment.location
}

output "namespaces" {
  description = "Experiment namespaces provisioned in the cluster."
  value       = sort(keys(kubernetes_namespace_v1.experiment))
}

output "get_credentials_command" {
  description = "Command that configures kubectl for this cluster."
  value       = "gcloud container clusters get-credentials ${google_container_cluster.experiment.name} --region ${google_container_cluster.experiment.location} --project ${var.project_id}"
}

output "gross_cost_budget" {
  description = "Project-scoped gross-cost alert budget. Credits are excluded from spend calculations."
  value = {
    currency = "billing-account-currency"
    amount   = var.gross_cost_budget_amount
    name     = google_billing_budget.experiment.display_name
  }
}

output "artifact_registry" {
  description = "Artifact Registry endpoint and retention controls, or null while its separate cost gate is disabled."
  value = var.allow_artifact_registry_creation ? {
    repository_id            = google_artifact_registry_repository.experiment[0].repository_id
    registry_uri             = google_artifact_registry_repository.experiment[0].registry_uri
    retention_days           = var.artifact_retention_days
    minimum_versions_to_keep = var.artifact_minimum_versions_to_keep
  } : null
}

output "github_actions_federation" {
  description = "Values to register in the protected GitHub Environment, or null while federation is disabled."
  value = var.enable_github_actions_federation ? {
    workload_identity_provider = google_iam_workload_identity_pool_provider.github_experiment[0].name
    service_account            = google_service_account.github_experiment[0].email
    trusted_repository_id      = var.github_repository_id
    trusted_owner_id           = var.github_repository_owner_id
    trusted_environment        = var.github_environment
    trusted_workflow_ref       = local.github_workflow_ref
  } : null
}
