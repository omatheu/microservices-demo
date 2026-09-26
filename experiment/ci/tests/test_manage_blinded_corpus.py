import copy
import contextlib
import importlib.util
import io
import json
import pathlib
import stat
import tempfile
import types
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "manage-blinded-corpus.py"
PROTOCOL_PATH = REPO_ROOT / "experiment" / "protocol" / "protocol-v1.json"
SPEC = importlib.util.spec_from_file_location("manage_blinded_corpus", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def protocol():
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


class ManageBlindedCorpusTests(unittest.TestCase):
    def build(self, key=b"a" * 32, value=None):
        return MODULE.build_corpus(
            value or protocol(),
            "f" * 64,
            key,
            "2026-09-20T00:00:00Z",
        )

    def test_generation_is_deterministic_and_blinded(self):
        public_one, oracle_one = self.build()
        public_two, oracle_two = self.build()

        self.assertEqual(public_one, public_two)
        self.assertEqual(oracle_one, oracle_two)
        self.assertEqual(public_one["candidate_count"], 18)
        self.assertFalse(public_one["confirmatory_eligible"])
        self.assertEqual(MODULE.recursively_find_forbidden_keys(public_one), [])
        self.assertEqual(
            {item["candidate_id"] for item in public_one["execution_order"]},
            {item["candidate_id"] for item in oracle_one["candidates"]},
        )

    def test_different_private_key_changes_identity_and_order(self):
        public_one, _ = self.build(key=b"a" * 32)
        public_two, _ = self.build(key=b"b" * 32)

        self.assertNotEqual(public_one["corpus_id"], public_two["corpus_id"])
        self.assertNotEqual(public_one["execution_order"], public_two["execution_order"])

    def test_tampered_oracle_manifest_is_rejected(self):
        value = protocol()
        public, oracle = self.build(value=value)
        current = oracle["candidates"][0]["intended_label"]
        oracle["candidates"][0]["intended_label"] = (
            "harmful" if current == "safe" else "safe"
        )

        with self.assertRaisesRegex(ValueError, "oracle manifest differs"):
            MODULE.validate_corpus(value, "f" * 64, b"a" * 32, public, oracle)

    def test_frozen_and_authorized_protocol_marks_corpus_eligible(self):
        value = copy.deepcopy(protocol())
        value["status"] = "frozen"
        value["frozen_at"] = "2026-09-20T00:00:00Z"
        value["confirmatory_collection_allowed"] = True

        public, _ = self.build(value=value)

        self.assertTrue(public["confirmatory_eligible"])

    def test_draft_generation_without_explicit_override_is_blocked(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = pathlib.Path(temporary_directory)
            key_path = temporary / "key.bin"
            key_path.write_bytes(b"a" * 32)
            key_path.chmod(0o600)
            args = types.SimpleNamespace(
                protocol=str(PROTOCOL_PATH),
                key=str(key_path),
                public_output=str(temporary / "public.json"),
                oracle_output=str(temporary / "oracle.json"),
                allow_draft=False,
            )

            with self.assertRaisesRegex(ValueError, "requires --allow-draft"):
                MODULE.generate_command(args)

    def test_private_oracle_manifest_can_be_derived_from_public_commitment(self):
        value = protocol()
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = pathlib.Path(temporary_directory)
            protocol_path = temporary / "protocol.json"
            key_path = temporary / "key.bin"
            public_path = temporary / "public.json"
            oracle_path = temporary / "oracle.json"
            protocol_path.write_text(json.dumps(value), encoding="utf-8")
            key_path.write_bytes(b"a" * 32)
            key_path.chmod(0o600)
            public, expected_oracle = MODULE.build_corpus(
                value,
                MODULE.sha256_file(protocol_path),
                b"a" * 32,
                "2026-09-20T00:00:00Z",
            )
            public_path.write_text(json.dumps(public), encoding="utf-8")

            args = types.SimpleNamespace(
                protocol=str(protocol_path),
                key=str(key_path),
                public=str(public_path),
                oracle_output=str(oracle_path),
                allow_draft=True,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                MODULE.derive_oracle_command(args)

            self.assertEqual(
                json.loads(oracle_path.read_text(encoding="utf-8")),
                expected_oracle,
            )
            self.assertEqual(stat.S_IMODE(oracle_path.stat().st_mode), 0o600)

    def test_private_oracle_derivation_rejects_tampered_public_corpus(self):
        value = protocol()
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = pathlib.Path(temporary_directory)
            protocol_path = temporary / "protocol.json"
            key_path = temporary / "key.bin"
            public_path = temporary / "public.json"
            oracle_path = temporary / "oracle.json"
            protocol_path.write_text(json.dumps(value), encoding="utf-8")
            key_path.write_bytes(b"a" * 32)
            key_path.chmod(0o600)
            public, _ = MODULE.build_corpus(
                value,
                MODULE.sha256_file(protocol_path),
                b"a" * 32,
                "2026-09-20T00:00:00Z",
            )
            public["execution_order"][0]["candidate_id"] = "cand-aaaaaaaaaaaaaaaa"
            public_path.write_text(json.dumps(public), encoding="utf-8")
            args = types.SimpleNamespace(
                protocol=str(protocol_path),
                key=str(key_path),
                public=str(public_path),
                oracle_output=str(oracle_path),
                allow_draft=True,
            )

            with self.assertRaisesRegex(ValueError, "public corpus differs"):
                MODULE.derive_oracle_command(args)
            self.assertFalse(oracle_path.exists())

    def test_draft_private_oracle_derivation_requires_explicit_override(self):
        value = protocol()
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = pathlib.Path(temporary_directory)
            protocol_path = temporary / "protocol.json"
            key_path = temporary / "key.bin"
            public_path = temporary / "public.json"
            protocol_path.write_text(json.dumps(value), encoding="utf-8")
            key_path.write_bytes(b"a" * 32)
            key_path.chmod(0o600)
            public, _ = MODULE.build_corpus(
                value,
                MODULE.sha256_file(protocol_path),
                b"a" * 32,
                "2026-09-20T00:00:00Z",
            )
            public_path.write_text(json.dumps(public), encoding="utf-8")
            args = types.SimpleNamespace(
                protocol=str(protocol_path),
                key=str(key_path),
                public=str(public_path),
                oracle_output=str(temporary / "oracle.json"),
                allow_draft=False,
            )

            with self.assertRaisesRegex(ValueError, "requires --allow-draft"):
                MODULE.derive_oracle_command(args)


if __name__ == "__main__":
    unittest.main()
