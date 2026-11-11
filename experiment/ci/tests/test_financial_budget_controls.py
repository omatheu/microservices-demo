import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
STACK = REPO_ROOT / "infra" / "terraform"


class FinancialBudgetControlsTests(unittest.TestCase):
    def test_incremental_guard_is_added_to_the_observed_baseline(self):
        main = (STACK / "main.tf").read_text(encoding="utf-8")
        budget = (STACK / "budget.tf").read_text(encoding="utf-8")

        self.assertIn(
            "var.gross_cost_budget_amount - var.experiment_spend_budget_amount",
            main,
        )
        self.assertIn(
            "experiment_cumulative_budget_amount  = var.gross_cost_budget_amount",
            main,
        )
        self.assertIn("local.experiment_budget_units", budget)
        self.assertIn("local.experiment_budget_nanos", budget)
        self.assertIn("local.experiment_financial_baseline_amount +", budget)
        self.assertIn("threshold_rules.value", budget)
        self.assertIn("local.experiment_cumulative_budget_amount", budget)

    def test_compatibility_output_remains_frozen_and_new_output_is_explicit(self):
        frozen_outputs = (STACK / "outputs.tf").read_text(encoding="utf-8")
        guard_outputs = (STACK / "financial-guard-outputs.tf").read_text(
            encoding="utf-8"
        )

        self.assertIn('output "experiment_spend_budget"', frozen_outputs)
        self.assertIn("baseline_amount", guard_outputs)
        self.assertIn("additional_ceiling", guard_outputs)
        self.assertIn("cumulative_budget_amount", guard_outputs)
        self.assertIn("local.experiment_financial_baseline_amount", guard_outputs)


if __name__ == "__main__":
    unittest.main()
