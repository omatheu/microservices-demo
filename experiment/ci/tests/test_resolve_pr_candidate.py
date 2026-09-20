import importlib.util
import json
import pathlib
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "resolve-pr-candidate.py"
SPEC = importlib.util.spec_from_file_location("resolve_pr_candidate", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def write_definition(root, candidate_id="cand-opaque", extra=None):
    relative = pathlib.Path("experiment/pdt/candidates") / f"{candidate_id}.json"
    path = pathlib.Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "schema_version": "1.0.0",
        "candidate_id": candidate_id,
        "alternatives": [
            {
                "id": "deploy-as-is",
                "action": "deploy",
                "configuration_changes": [],
                "change_cost": 0,
            }
        ],
    }
    value.update(extra or {})
    path.write_text(json.dumps(value), encoding="utf-8")
    return relative.as_posix()


class ResolvePullRequestCandidateTests(unittest.TestCase):
    def test_regular_pull_request_gets_non_cloud_identity(self):
        result = MODULE.resolve(
            pathlib.Path("/unused"),
            ["src/checkoutservice/main.go"],
            "42",
            "a" * 40,
        )

        self.assertEqual(result["candidate_id"], "pr-42-aaaaaaaaaaaa")
        self.assertIsNone(result["candidate_definition"])
        self.assertFalse(result["experimental_cloud_eligible"])

    def test_single_public_candidate_definition_enables_experimental_job(self):
        with tempfile.TemporaryDirectory() as directory:
            relative = write_definition(directory)

            result = MODULE.resolve(
                pathlib.Path(directory), [relative], "42", "b" * 40
            )

        self.assertEqual(result["candidate_id"], "cand-opaque")
        self.assertEqual(result["candidate_definition"], relative)
        self.assertTrue(result["experimental_cloud_eligible"])

    def test_multiple_candidate_definitions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            MODULE.resolve(
                pathlib.Path("/unused"),
                [
                    "experiment/pdt/candidates/cand-a.json",
                    "experiment/pdt/candidates/cand-b.json",
                ],
                "42",
                "c" * 40,
            )

    def test_private_oracle_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            relative = write_definition(
                directory, extra={"intended_label": "harmful"}
            )

            with self.assertRaisesRegex(ValueError, "leaks private keys"):
                MODULE.resolve(
                    pathlib.Path(directory), [relative], "42", "d" * 40
                )

    def test_filename_must_match_candidate_id(self):
        with tempfile.TemporaryDirectory() as directory:
            relative = write_definition(directory)
            source = pathlib.Path(directory) / relative
            other = source.with_name("different.json")
            source.rename(other)

            with self.assertRaisesRegex(ValueError, "filename"):
                MODULE.resolve(
                    pathlib.Path(directory),
                    ["experiment/pdt/candidates/different.json"],
                    "42",
                    "e" * 40,
                )


if __name__ == "__main__":
    unittest.main()
