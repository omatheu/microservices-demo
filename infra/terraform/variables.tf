variable "project_id" {
  description = "Google Cloud project that owns the experimental infrastructure."
  type        = string

  validation {
    condition     = length(trimspace(var.project_id)) > 0 && var.project_id != "replace-me"
    error_message = "Set project_id to an existing Google Cloud project ID."
  }
}

variable "region" {
  description = "Google Cloud region for the regional GKE Autopilot cluster."
  type        = string
  default     = "us-central1"
}

variable "cluster_name" {
  description = "Name of the GKE Autopilot cluster."
  type        = string
  default     = "online-boutique-experiment"
}

variable "deletion_protection" {
  description = "Protect the cluster against accidental deletion."
  type        = bool
  default     = true
}

variable "allow_billable_resources" {
  description = "Explicit financial-control gate. Keep false until credits, budget alerts, quotas, and the experiment window have been reviewed."
  type        = bool
  default     = false
}

variable "allow_artifact_registry_creation" {
  description = "Separate cost gate for Artifact Registry. Keep false until storage/egress estimates and cleanup retention have been reviewed."
  type        = bool
  default     = false
}

variable "artifact_registry_repository_id" {
  description = "Artifact Registry repository used only for immutable experiment candidate images."
  type        = string
  default     = "online-boutique-experiment"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,62}$", var.artifact_registry_repository_id))
    error_message = "artifact_registry_repository_id must be a lowercase repository ID."
  }
}

variable "artifact_retention_days" {
  description = "Maximum age of candidate image versions before cleanup, except the minimum versions retained per package."
  type        = number
  default     = 3

  validation {
    condition     = var.artifact_retention_days >= 1 && var.artifact_retention_days <= 14
    error_message = "artifact_retention_days must be between 1 and 14."
  }
}

variable "artifact_minimum_versions_to_keep" {
  description = "Minimum recent versions retained per image package for audit and reruns."
  type        = number
  default     = 2

  validation {
    condition     = var.artifact_minimum_versions_to_keep >= 1 && var.artifact_minimum_versions_to_keep <= 5
    error_message = "artifact_minimum_versions_to_keep must be between 1 and 5."
  }
}

variable "enable_github_actions_federation" {
  description = "Explicit IAM gate for the protected GitHub Actions experiment workflow. This creates no service-account key and defaults to disabled."
  type        = bool
  default     = false
}

variable "github_repository" {
  description = "GitHub repository allowed to request the experiment identity."
  type        = string
  default     = "omatheu/microservices-demo"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must use owner/repository format."
  }
}

variable "github_repository_id" {
  description = "Immutable numeric GitHub repository ID used in the OIDC trust condition."
  type        = string
  default     = "1376372479"

  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.github_repository_id))
    error_message = "github_repository_id must be a numeric GitHub repository ID."
  }
}

variable "github_repository_owner_id" {
  description = "Immutable numeric GitHub owner ID used in the OIDC trust condition."
  type        = string
  default     = "124204749"

  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.github_repository_owner_id))
    error_message = "github_repository_owner_id must be a numeric GitHub owner ID."
  }
}

variable "github_default_branch" {
  description = "Branch from which the protected cloud workflow definition must originate."
  type        = string
  default     = "main"

  validation {
    condition     = can(regex("^[A-Za-z0-9._/-]+$", var.github_default_branch))
    error_message = "github_default_branch contains unsupported characters."
  }
}

variable "github_environment" {
  description = "Protected GitHub Environment required by the cloud job and OIDC token."
  type        = string
  default     = "tcc-experiment"

  validation {
    condition     = can(regex("^[A-Za-z0-9._-]+$", var.github_environment))
    error_message = "github_environment contains unsupported characters."
  }
}

variable "github_cloud_workflow_file" {
  description = "Exact workflow filename trusted by the OIDC provider."
  type        = string
  default     = "tcc-pr-experiment.yaml"

  validation {
    condition     = can(regex("^[A-Za-z0-9._-]+\\.ya?ml$", var.github_cloud_workflow_file))
    error_message = "github_cloud_workflow_file must be a YAML filename."
  }
}

variable "github_workload_identity_pool_id" {
  description = "Workload Identity Pool ID reserved for the experiment workflow."
  type        = string
  default     = "github-tcc-experiment"
}

variable "github_workload_identity_provider_id" {
  description = "OIDC provider ID inside the experiment Workload Identity Pool."
  type        = string
  default     = "github-tcc"
}

variable "github_experiment_service_account_id" {
  description = "Service account ID impersonated by the protected GitHub workflow."
  type        = string
  default     = "github-tcc-experiment"
}

variable "github_runtime_publisher_service_account_id" {
  description = "Artifact Registry-only service account ID used by the publication-only job."
  type        = string
  default     = "github-tcc-runtime-publisher"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.github_runtime_publisher_service_account_id))
    error_message = "github_runtime_publisher_service_account_id must be a valid service account ID."
  }
}

variable "billing_account_id" {
  description = "Billing account used for project-scoped budget alerts."
  type        = string
}

variable "gross_cost_budget_amount" {
  description = "Gross-cost alert budget in the billing account currency. Credits are deliberately excluded from spend calculations."
  type        = number
  default     = 10

  validation {
    condition     = var.gross_cost_budget_amount > 0
    error_message = "gross_cost_budget_amount must be greater than zero."
  }
}

variable "experiment_spend_budget_amount" {
  description = "Lower project-scoped gross-cost alert budget used as the operational ceiling for the experiment."
  type        = number
  default     = 200

  validation {
    condition     = var.experiment_spend_budget_amount > 0 && var.experiment_spend_budget_amount < var.gross_cost_budget_amount
    error_message = "experiment_spend_budget_amount must be greater than zero and lower than gross_cost_budget_amount."
  }
}

variable "resource_quotas" {
  description = "Capacity ceilings per experiment namespace; these are limits, not reservations."
  type = map(object({
    requests_cpu    = string
    requests_memory = string
    limits_cpu      = string
    limits_memory   = string
    pods            = string
    services_lb     = string
  }))

  default = {
    operational = {
      requests_cpu    = "3"
      requests_memory = "6Gi"
      limits_cpu      = "6"
      limits_memory   = "10Gi"
      pods            = "20"
      services_lb     = "1"
    }
    staging = {
      requests_cpu    = "3"
      requests_memory = "6Gi"
      limits_cpu      = "6"
      limits_memory   = "10Gi"
      pods            = "20"
      services_lb     = "0"
    }
    pdt = {
      requests_cpu    = "3"
      requests_memory = "6Gi"
      limits_cpu      = "6"
      limits_memory   = "10Gi"
      pods            = "20"
      services_lb     = "0"
    }
    pdt-system = {
      requests_cpu    = "500m"
      requests_memory = "1Gi"
      limits_cpu      = "1"
      limits_memory   = "2Gi"
      pods            = "5"
      services_lb     = "0"
    }
    oracle = {
      requests_cpu    = "3"
      requests_memory = "6Gi"
      limits_cpu      = "6"
      limits_memory   = "10Gi"
      pods            = "20"
      services_lb     = "0"
    }
    observability = {
      requests_cpu    = "2"
      requests_memory = "4Gi"
      limits_cpu      = "4"
      limits_memory   = "8Gi"
      pods            = "20"
      services_lb     = "0"
    }
  }

  validation {
    condition = (
      length(setsubtract(toset(keys(var.resource_quotas)), toset(["operational", "staging", "pdt", "pdt-system", "oracle", "observability"]))) == 0 &&
      length(setsubtract(toset(["operational", "staging", "pdt", "pdt-system", "oracle", "observability"]), toset(keys(var.resource_quotas)))) == 0
    )
    error_message = "resource_quotas must define operational, staging, pdt, pdt-system, oracle, and observability."
  }
}
