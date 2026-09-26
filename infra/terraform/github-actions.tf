locals {
  github_workflow_ref = "${var.github_repository}/.github/workflows/${var.github_cloud_workflow_file}@refs/heads/${var.github_default_branch}"
  github_project_roles = toset([
    "roles/container.clusterViewer",
    "roles/monitoring.viewer",
    "roles/serviceusage.serviceUsageConsumer",
  ])
  github_mutable_namespaces = toset([
    "pdt",
    "staging",
  ])
}

resource "google_service_account" "github_experiment" {
  count = var.enable_github_actions_federation ? 1 : 0

  project      = var.project_id
  account_id   = var.github_experiment_service_account_id
  display_name = "GitHub TCC experiment runner"
  description  = "Keyless identity for the protected paired staging and PDT workflow"

  lifecycle {
    precondition {
      condition     = var.allow_artifact_registry_creation
      error_message = "GitHub experiment federation requires the separately approved Artifact Registry."
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_service_account" "github_runtime_publisher" {
  count = var.enable_github_actions_federation ? 1 : 0

  project      = var.project_id
  account_id   = var.github_runtime_publisher_service_account_id
  display_name = "GitHub TCC runtime publisher"
  description  = "Keyless Artifact Registry-only identity for the protected runtime publication job"

  lifecycle {
    precondition {
      condition     = var.allow_artifact_registry_creation
      error_message = "GitHub runtime publication requires the separately approved Artifact Registry."
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_iam_workload_identity_pool" "github_experiment" {
  count = var.enable_github_actions_federation ? 1 : 0

  project                   = var.project_id
  workload_identity_pool_id = var.github_workload_identity_pool_id
  display_name              = "GitHub TCC experiment"
  description               = "Accepts only the protected paired experiment workflow"
  disabled                  = false
}

resource "google_iam_workload_identity_pool_provider" "github_experiment" {
  count = var.enable_github_actions_federation ? 1 : 0

  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_experiment[0].workload_identity_pool_id
  workload_identity_pool_provider_id = var.github_workload_identity_provider_id
  display_name                       = "Protected GitHub TCC workflow"
  description                        = "Repository, environment, event and workflow-restricted GitHub OIDC trust"

  attribute_mapping = {
    "google.subject"                = "assertion.sub"
    "attribute.repository_id"       = "assertion.repository_id"
    "attribute.repository_owner_id" = "assertion.repository_owner_id"
    "attribute.environment"         = "assertion.environment"
    "attribute.event_name"          = "assertion.event_name"
    "attribute.workflow_ref"        = "assertion.workflow_ref"
  }

  attribute_condition = join(" && ", [
    "assertion.repository_id == '${var.github_repository_id}'",
    "assertion.repository_owner_id == '${var.github_repository_owner_id}'",
    "assertion.environment == '${var.github_environment}'",
    "assertion.event_name == 'workflow_run'",
    "assertion.workflow_ref == '${local.github_workflow_ref}'",
  ])

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com/"
  }
}

resource "google_service_account_iam_member" "github_experiment_federation" {
  count = var.enable_github_actions_federation ? 1 : 0

  service_account_id = google_service_account.github_experiment[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_experiment[0].name}/attribute.repository_id/${var.github_repository_id}"
}

resource "google_service_account_iam_member" "github_runtime_publisher_federation" {
  count = var.enable_github_actions_federation ? 1 : 0

  service_account_id = google_service_account.github_runtime_publisher[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_experiment[0].name}/attribute.repository_id/${var.github_repository_id}"
}

resource "google_project_iam_member" "github_experiment" {
  for_each = var.enable_github_actions_federation ? local.github_project_roles : toset([])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.github_experiment[0].email}"
}

resource "google_artifact_registry_repository_iam_member" "github_experiment_writer" {
  count = var.enable_github_actions_federation && var.allow_artifact_registry_creation ? 1 : 0

  project    = var.project_id
  location   = google_artifact_registry_repository.experiment[0].location
  repository = google_artifact_registry_repository.experiment[0].repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.github_experiment[0].email}"
}

resource "google_artifact_registry_repository_iam_member" "github_runtime_publisher_writer" {
  count = var.enable_github_actions_federation && var.allow_artifact_registry_creation ? 1 : 0

  project    = var.project_id
  location   = google_artifact_registry_repository.experiment[0].location
  repository = google_artifact_registry_repository.experiment[0].repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.github_runtime_publisher[0].email}"
}

resource "kubernetes_cluster_role_v1" "github_experiment_namespace_reader" {
  count = var.enable_github_actions_federation ? 1 : 0

  metadata {
    name = "github-tcc-namespace-reader"
  }

  rule {
    api_groups = [""]
    resources  = ["namespaces"]
    verbs      = ["get", "list"]
  }
}

resource "kubernetes_cluster_role_binding_v1" "github_experiment_namespace_reader" {
  count = var.enable_github_actions_federation ? 1 : 0

  metadata {
    name = "github-tcc-namespace-reader"
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role_v1.github_experiment_namespace_reader[0].metadata[0].name
  }

  subject {
    api_group = "rbac.authorization.k8s.io"
    kind      = "User"
    name      = google_service_account.github_experiment[0].email
  }
}

resource "kubernetes_role_v1" "github_experiment_mutator" {
  for_each = var.enable_github_actions_federation ? local.github_mutable_namespaces : toset([])

  metadata {
    name      = "github-tcc-experiment-runner"
    namespace = kubernetes_namespace_v1.experiment[each.value].metadata[0].name
  }

  rule {
    api_groups = [""]
    resources  = ["serviceaccounts", "services"]
    verbs      = ["create", "delete", "get", "list", "patch", "update", "watch"]
  }

  rule {
    api_groups = [""]
    resources  = ["events", "pods", "resourcequotas"]
    verbs      = ["get", "list", "watch"]
  }

  rule {
    api_groups = [""]
    resources  = ["pods/log"]
    verbs      = ["get"]
  }

  rule {
    api_groups = [""]
    resources  = ["pods/portforward"]
    verbs      = ["create"]
  }

  rule {
    api_groups = ["apps"]
    resources  = ["deployments"]
    verbs      = ["create", "delete", "get", "list", "patch", "update", "watch"]
  }

  rule {
    api_groups = ["apps"]
    resources  = ["replicasets"]
    verbs      = ["get", "list", "watch"]
  }

  rule {
    api_groups = ["networking.k8s.io"]
    resources  = ["networkpolicies"]
    verbs      = ["create", "delete", "get", "list", "patch", "update", "watch"]
  }
}

resource "kubernetes_role_binding_v1" "github_experiment_mutator" {
  for_each = var.enable_github_actions_federation ? local.github_mutable_namespaces : toset([])

  metadata {
    name      = "github-tcc-experiment-runner"
    namespace = kubernetes_namespace_v1.experiment[each.value].metadata[0].name
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role_v1.github_experiment_mutator[each.value].metadata[0].name
  }

  subject {
    api_group = "rbac.authorization.k8s.io"
    kind      = "User"
    name      = google_service_account.github_experiment[0].email
  }
}

resource "kubernetes_role_v1" "github_experiment_pdt_controller" {
  count = var.enable_github_actions_federation ? 1 : 0

  metadata {
    name      = "github-tcc-pdt-controller"
    namespace = kubernetes_namespace_v1.experiment["pdt-system"].metadata[0].name
  }

  rule {
    api_groups = [""]
    resources  = ["configmaps", "serviceaccounts"]
    verbs      = ["create", "delete", "get", "list", "patch", "update", "watch"]
  }

  rule {
    api_groups = [""]
    resources  = ["events", "pods"]
    verbs      = ["get", "list", "watch"]
  }

  rule {
    api_groups = [""]
    resources  = ["pods/log"]
    verbs      = ["get"]
  }

  rule {
    api_groups = ["batch"]
    resources  = ["jobs"]
    verbs      = ["create", "delete", "get", "list", "patch", "update", "watch"]
  }

  rule {
    api_groups = ["networking.k8s.io"]
    resources  = ["networkpolicies"]
    verbs      = ["create", "delete", "get", "list", "patch", "update", "watch"]
  }
}

resource "kubernetes_role_binding_v1" "github_experiment_pdt_controller" {
  count = var.enable_github_actions_federation ? 1 : 0

  metadata {
    name      = "github-tcc-pdt-controller"
    namespace = kubernetes_namespace_v1.experiment["pdt-system"].metadata[0].name
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role_v1.github_experiment_pdt_controller[0].metadata[0].name
  }

  subject {
    api_group = "rbac.authorization.k8s.io"
    kind      = "User"
    name      = google_service_account.github_experiment[0].email
  }
}

resource "kubernetes_role_v1" "github_experiment_oracle_runner" {
  count = var.enable_github_actions_federation ? 1 : 0

  metadata {
    name      = "github-tcc-oracle-runner"
    namespace = kubernetes_namespace_v1.experiment["oracle"].metadata[0].name
  }

  rule {
    api_groups = [""]
    resources  = ["serviceaccounts", "services"]
    verbs      = ["create", "delete", "get", "list", "patch", "update", "watch"]
  }

  rule {
    api_groups = [""]
    resources  = ["events", "pods", "resourcequotas"]
    verbs      = ["get", "list", "watch"]
  }

  rule {
    api_groups = [""]
    resources  = ["pods/log"]
    verbs      = ["get"]
  }

  rule {
    api_groups = [""]
    resources  = ["pods/portforward"]
    verbs      = ["create"]
  }

  rule {
    api_groups = ["apps"]
    resources  = ["deployments"]
    verbs      = ["create", "delete", "get", "list", "patch", "update", "watch"]
  }

  rule {
    api_groups = ["apps"]
    resources  = ["replicasets"]
    verbs      = ["get", "list", "watch"]
  }

  rule {
    api_groups = ["networking.k8s.io"]
    resources  = ["networkpolicies"]
    verbs      = ["create", "delete", "get", "list", "patch", "update", "watch"]
  }
}

resource "kubernetes_role_binding_v1" "github_experiment_oracle_runner" {
  count = var.enable_github_actions_federation ? 1 : 0

  metadata {
    name      = "github-tcc-oracle-runner"
    namespace = kubernetes_namespace_v1.experiment["oracle"].metadata[0].name
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role_v1.github_experiment_oracle_runner[0].metadata[0].name
  }

  subject {
    api_group = "rbac.authorization.k8s.io"
    kind      = "User"
    name      = google_service_account.github_experiment[0].email
  }
}

resource "kubernetes_role_v1" "github_experiment_operational_reader" {
  count = var.enable_github_actions_federation ? 1 : 0

  metadata {
    name      = "github-tcc-operational-reader"
    namespace = kubernetes_namespace_v1.experiment["operational"].metadata[0].name
  }

  rule {
    api_groups = [""]
    resources  = ["events", "pods", "resourcequotas", "services"]
    verbs      = ["get", "list", "watch"]
  }

  rule {
    api_groups = [""]
    resources  = ["pods/log"]
    verbs      = ["get"]
  }

  rule {
    api_groups = ["apps"]
    resources  = ["deployments", "replicasets"]
    verbs      = ["get", "list", "watch"]
  }
}

resource "kubernetes_role_binding_v1" "github_experiment_operational_reader" {
  count = var.enable_github_actions_federation ? 1 : 0

  metadata {
    name      = "github-tcc-operational-reader"
    namespace = kubernetes_namespace_v1.experiment["operational"].metadata[0].name
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role_v1.github_experiment_operational_reader[0].metadata[0].name
  }

  subject {
    api_group = "rbac.authorization.k8s.io"
    kind      = "User"
    name      = google_service_account.github_experiment[0].email
  }
}
