resource "google_project_service" "bigquery" {
  count = var.enable_billing_export_dataset ? 1 : 0

  project            = var.project_id
  service            = "bigquery.googleapis.com"
  disable_on_destroy = false
}

resource "google_bigquery_dataset" "billing_export" {
  count = var.enable_billing_export_dataset ? 1 : 0

  project                    = var.project_id
  dataset_id                 = var.billing_export_dataset_id
  friendly_name              = "Online Boutique TCC billing export"
  description                = "Standard Cloud Billing export used for per-block financial review; export activation remains a separate console action."
  location                   = var.billing_export_dataset_location
  delete_contents_on_destroy = false
  max_time_travel_hours      = 48

  labels = {
    application = "online-boutique"
    purpose     = "tcc-cost-governance"
    managed-by  = "terraform"
  }

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = var.enable_billing_export_dataset
      error_message = "Dataset creation requires the explicit billing-export write gate."
    }
  }

  depends_on = [google_project_service.bigquery]
}
