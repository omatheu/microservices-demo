locals {
  budget_units = floor(var.gross_cost_budget_amount)
  budget_nanos = floor(((var.gross_cost_budget_amount - local.budget_units) * 1000000000) + 0.5)

  required_services = setunion(
    toset([
      "cloudresourcemanager.googleapis.com",
      "billingbudgets.googleapis.com",
      "container.googleapis.com",
      "logging.googleapis.com",
      "monitoring.googleapis.com",
    ]),
    var.allow_artifact_registry_creation ? toset(["artifactregistry.googleapis.com"]) : toset([]),
    var.enable_github_actions_federation ? toset([
      "iam.googleapis.com",
      "iamcredentials.googleapis.com",
      "sts.googleapis.com",
    ]) : toset([])
  )

  namespace_labels = {
    operational = {
      "experiment.online-boutique.dev/role" = "operational"
      "environment"                         = "operational"
    }
    staging = {
      "experiment.online-boutique.dev/role" = "baseline"
      "environment"                         = "staging"
    }
    pdt = {
      "experiment.online-boutique.dev/role" = "counterfactual-simulation"
      "environment"                         = "pdt"
    }
    pdt-system = {
      "experiment.online-boutique.dev/role" = "digital-twin-control-plane"
      "environment"                         = "pdt-system"
    }
    oracle = {
      "experiment.online-boutique.dev/role" = "independent-outcome-adjudication"
      "environment"                         = "oracle"
    }
    observability = {
      "experiment.online-boutique.dev/role" = "telemetry-and-evidence"
      "environment"                         = "observability"
    }
  }
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_project_service" "required" {
  for_each = local.required_services

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_container_cluster" "experiment" {
  name     = var.cluster_name
  location = var.region
  project  = var.project_id

  enable_autopilot    = true
  deletion_protection = var.deletion_protection

  release_channel {
    channel = "REGULAR"
  }

  ip_allocation_policy {}

  resource_labels = {
    application = "online-boutique"
    purpose     = "tcc-experiment"
    managed-by  = "terraform"
  }

  lifecycle {
    precondition {
      condition     = var.allow_billable_resources
      error_message = "Billable resource creation is locked. Confirm credits, budgets, quotas, and the execution window before setting allow_billable_resources=true."
    }
  }

  depends_on = [google_project_service.required]
}

resource "kubernetes_namespace_v1" "experiment" {
  for_each = local.namespace_labels

  metadata {
    name   = each.key
    labels = each.value
  }

  depends_on = [google_container_cluster.experiment]
}

resource "kubernetes_resource_quota_v1" "experiment" {
  for_each = var.resource_quotas

  metadata {
    name      = "experiment-capacity"
    namespace = kubernetes_namespace_v1.experiment[each.key].metadata[0].name
  }

  spec {
    hard = {
      "requests.cpu"           = each.value.requests_cpu
      "requests.memory"        = each.value.requests_memory
      "limits.cpu"             = each.value.limits_cpu
      "limits.memory"          = each.value.limits_memory
      "pods"                   = each.value.pods
      "services.loadbalancers" = each.value.services_lb
    }
  }
}
