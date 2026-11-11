output "experiment_spend_budget_cumulative" {
  description = "Baseline-aware cumulative gross-cost guard used for incremental experiment reviews."
  value = {
    currency                 = "BRL"
    baseline_amount          = local.experiment_financial_baseline_amount
    additional_ceiling       = var.experiment_spend_budget_amount
    cumulative_budget_amount = local.experiment_cumulative_budget_amount
    name                     = google_billing_budget.experiment_spend_guard.display_name
    alert_amounts = [
      local.experiment_financial_baseline_amount + (var.experiment_spend_budget_amount * 0.25),
      local.experiment_financial_baseline_amount + (var.experiment_spend_budget_amount * 0.50),
      local.experiment_financial_baseline_amount + (var.experiment_spend_budget_amount * 0.75),
      local.experiment_financial_baseline_amount + (var.experiment_spend_budget_amount * 0.90),
      local.experiment_cumulative_budget_amount,
    ]
  }
}
