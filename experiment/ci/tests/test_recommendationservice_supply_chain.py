import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


class RecommendationServiceSupplyChainTests(unittest.TestCase):
    def test_security_pins_are_explicit_in_source_and_lock(self):
        expected = {
            "msgpack": "1.2.1",
            "pyasn1": "0.6.4",
            "pyasn1-modules": "0.4.2",
            "setuptools": "84.0.0",
            "urllib3": "2.8.0",
        }
        service = REPO_ROOT / "src/recommendationservice"
        direct = (service / "requirements.in").read_text(encoding="utf-8")
        lock = (service / "requirements.txt").read_text(encoding="utf-8")
        for package, version in expected.items():
            pin = f"{package}=={version}"
            self.assertIn(pin, direct)
            self.assertIn(pin, lock)

    def test_runtime_uses_updated_isolated_non_root_environment(self):
        dockerfile = (
            REPO_ROOT / "src/recommendationservice/Dockerfile"
        ).read_text(encoding="utf-8")
        self.assertIn("FROM --platform=$BUILDPLATFORM alpine:3.24.1@sha256:", dockerfile)
        self.assertIn("RUN apk upgrade --no-cache", dockerfile)
        self.assertIn("python3 -m venv /opt/venv", dockerfile)
        self.assertIn("pip install --no-cache-dir --upgrade", dockerfile)
        self.assertIn("pip uninstall --yes pip", dockerfile)
        self.assertIn("COPY --from=builder /opt/venv /opt/venv", dockerfile)
        self.assertIn("COPY --chown=10001:10001 . .", dockerfile)
        self.assertIn("chown 10001:10001 /recommendationservice", dockerfile)
        self.assertIn("python -m compileall -q /recommendationservice", dockerfile)
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertLess(
            dockerfile.index("USER 10001:10001"),
            dockerfile.index("python -m compileall -q /recommendationservice"),
        )


if __name__ == "__main__":
    unittest.main()
