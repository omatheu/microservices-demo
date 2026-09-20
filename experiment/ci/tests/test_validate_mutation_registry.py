import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "validate-mutation-registry.py"
PROTOCOL_PATH = REPO_ROOT / "experiment" / "protocol" / "protocol-v1.json"
REGISTRY_PATH = REPO_ROOT / "experiment" / "mutations" / "registry.json"
SPEC = importlib.util.spec_from_file_location("validate_mutation_registry", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class ValidateMutationRegistryTests(unittest.TestCase):
    def test_registry_matches_protocol_and_materializer(self):
        result = MODULE.validate(
            REPO_ROOT,
            load(PROTOCOL_PATH),
            load(REGISTRY_PATH),
        )

        self.assertEqual(result["operator_count"], 13)
        self.assertEqual(result["implemented_count"], 13)
        self.assertEqual(result["pending_count"], 0)
        self.assertTrue(result["all_implemented"])

    def test_registry_hash_drift_is_blocked(self):
        registry = load(REGISTRY_PATH)
        registry["materializer"]["sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "hash differs"):
            MODULE.validate(REPO_ROOT, load(PROTOCOL_PATH), registry)


if __name__ == "__main__":
    unittest.main()
