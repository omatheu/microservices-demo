import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "experiment/scripts/capture-pdt-source-state.sh"


class CapturePdtSourceStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_snapshot_requires_a_continuously_stable_operational_source(self):
        self.assertIn("wait-for-workload-stability.sh", self.script)
        self.assertIn("MINIMUM_EXPECTED_DEPLOYMENTS=12", self.script)
        self.assertIn("operational-workload-stability.json", self.script)
        self.assertIn("snapshot_eligible: false", self.script)
        self.assertIn("operational_stability_sha256", self.script)


if __name__ == "__main__":
    unittest.main()
