resource "google_billing_budget" "experiment" {
  billing_account = var.billing_account_id
  display_name    = "Online Boutique TCC - gross cost guard"
  ownership_scope = "ALL_USERS"
  deletion_policy = "PREVENT"

  budget_filter {
    projects               = ["projects/${data.google_project.current.number}"]
    credit_types_treatment = "EXCLUDE_ALL_CREDITS"

    custom_period {
      start_date {
        year  = 2026
        month = 9
        day   = 19
      }

      # The API tracks costs before the end date, so use the day after expiry.
      end_date {
        year  = 2026
        month = 12
        day   = 20
      }
    }
  }

  amount {
    specified_amount {
      units = tostring(local.budget_units)
      nanos = local.budget_nanos
    }
  }

  dynamic "threshold_rules" {
    for_each = toset([0.25, 0.50, 0.75, 0.90, 0.95, 1.00])
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }

  depends_on = [google_project_service.required["billingbudgets.googleapis.com"]]
}
