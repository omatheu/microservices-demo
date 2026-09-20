output "billing_export_dataset" {
  description = "Dataset to select when enabling Standard Cloud Billing export, or null while the gate is disabled."
  value = var.enable_billing_export_dataset ? {
    project_id = google_bigquery_dataset.billing_export[0].project
    dataset_id = google_bigquery_dataset.billing_export[0].dataset_id
    location   = google_bigquery_dataset.billing_export[0].location
  } : null
}
