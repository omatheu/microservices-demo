variable "project_id" {
  description = "Existing project that stores the experiment's billing export."
  type        = string
  default     = "microservices-demo-tcc"

  validation {
    condition     = var.project_id == "microservices-demo-tcc"
    error_message = "This reviewed stack is restricted to microservices-demo-tcc."
  }
}

variable "enable_billing_export_dataset" {
  description = "Independent write gate for the minimal BigQuery billing-export dataset."
  type        = bool
  default     = false
}

variable "billing_export_dataset_id" {
  description = "BigQuery dataset that receives Standard Cloud Billing usage-cost data."
  type        = string
  default     = "online_boutique_billing"

  validation {
    condition     = length(var.billing_export_dataset_id) <= 1024 && can(regex("^[A-Za-z_][A-Za-z0-9_]*$", var.billing_export_dataset_id))
    error_message = "billing_export_dataset_id must be a valid BigQuery dataset ID."
  }
}

variable "billing_export_dataset_location" {
  description = "Multi-region fixed to US for documented current/previous-month backfill."
  type        = string
  default     = "US"

  validation {
    condition     = var.billing_export_dataset_location == "US"
    error_message = "billing_export_dataset_location must be US for this protocol."
  }
}
