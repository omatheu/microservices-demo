import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "experiment/scripts/run-traditional-staging.sh"
THRESHOLDS = REPO_ROOT / "experiment/staging/safety-thresholds.json"


class RunTraditionalStagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = RUNNER.read_text(encoding="utf-8")
        cls.thresholds = json.loads(THRESHOLDS.read_text(encoding="utf-8"))

    def test_real_service_contracts_are_required_for_pass(self):
        policy = self.thresholds["real_service_contracts"]
        self.assertEqual(
            ["happy-path-order", "payment-failure-preserves-cart"],
            policy["required_ids"],
        )
        self.assertEqual(0, policy["maximum_failures"])
        self.assertFalse(policy["operational_snapshot_access"])
        self.assertIn('"real_service_contracts_failed"', self.script)
        self.assertIn("$contract_failures > $max_contract_failures", self.script)

    def test_probe_uses_real_staging_services_and_preserves_control_blinding(self):
        self.assertIn(
            'start_supervised_port_forward "$namespace" cartservice "$local_cart_port" 7070',
            self.script,
        )
        self.assertIn(
            'start_supervised_port_forward "$namespace" checkoutservice "$local_checkout_port" 5050',
            self.script,
        )
        self.assertIn("go run ./cmd/stagingcontract", self.script)
        self.assertIn(".operational_snapshot_access == false", self.script)
        self.assertIn("traditional-staging-real-service-contracts", self.script)

    def test_contract_report_is_embedded_in_the_staging_decision(self):
        self.assertIn('--slurpfile real_service_contracts "$real_contracts_file"', self.script)
        self.assertIn("real_service_contracts:$real_service_contracts[0]", self.script)
        self.assertIn("and ([.cases[].id] | sort == ($required | sort))", self.script)

    def test_port_forward_loss_is_not_converted_into_candidate_failure(self):
        self.assertIn("start_supervised_port_forward", self.script)
        self.assertIn("assert_staging_port_forwards", self.script)
        self.assertIn('classification: "infrastructure-invalid"', self.script)
        self.assertIn("SUPERVISED_PORT_FORWARD_EXIT_CODE", self.script)

    def test_non_candidate_workloads_must_be_stable_before_measurement(self):
        self.assertIn("wait-for-workload-stability.sh", self.script)
        self.assertIn("EXCLUDED_DEPLOYMENTS=checkoutservice", self.script)
        self.assertIn('if [[ "$deployment" == "checkoutservice" ]]', self.script)
        self.assertIn("preserving as candidate behavior", self.script)
        self.assertIn("non-candidate deployment ${deployment} did not become ready", self.script)
        self.assertIn('"unavailable_deployments_above_threshold"', self.script)


if __name__ == "__main__":
    unittest.main()
