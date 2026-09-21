resource "google_billing_budget" "experiment" {
  billing_account = var.billing_account_id
  display_name    = "Online Boutique TCC - gross cost guard"
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

resource "google_billing_budget" "experiment_spend_guard" {
  billing_account = var.billing_account_id
  display_name    = "Online Boutique TCC - experimental spend guard"
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

      end_date {
        year  = 2026
        month = 12
        day   = 20
      }
    }
  }

  amount {
    specified_amount {
      currency_code = "BRL"
      units         = tostring(floor(var.experiment_spend_budget_amount))
      nanos         = floor(((var.experiment_spend_budget_amount - floor(var.experiment_spend_budget_amount)) * 1000000000) + 0.5)
    }
  }

  dynamic "threshold_rules" {
    for_each = toset([0.25, 0.50, 0.75, 0.90, 1.00])
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }

  depends_on = [google_project_service.required["billingbudgets.googleapis.com"]]
}
