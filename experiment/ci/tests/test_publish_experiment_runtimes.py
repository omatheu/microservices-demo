import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PUBLISHER = REPO_ROOT / "experiment" / "scripts" / "publish-experiment-runtimes.sh"


class PublishExperimentRuntimesTests(unittest.TestCase):
    def test_publication_is_bound_to_exact_source_and_reviewed_registry(self):
        rendered = PUBLISHER.read_text(encoding="utf-8")

        self.assertIn("ALLOW_EXPERIMENTAL_CLOUD_EXECUTION", rendered)
        self.assertIn("COST_REVIEW_ACKNOWLEDGED", rendered)
        self.assertIn('git -C "$repo_root" rev-parse HEAD', rendered)
        self.assertIn("rev-parse 'HEAD^{tree}'", rendered)
        self.assertIn(
            "us-central1-docker.pkg.dev/microservices-demo-tcc/online-boutique-experiment",
            rendered,
        )

    def test_every_runtime_is_scanned_before_push_and_bound_after_push(self):
        rendered = PUBLISHER.read_text(encoding="utf-8")

        for name in ("checkout-pdt-controller", "oracle-harness", "currency-reference"):
            self.assertIn(name, rendered)
        self.assertLess(rendered.index('"$trivy_image" image'), rendered.index('docker push "$tag"'))
        self.assertLess(rendered.index('docker push "$tag"'), rendered.index("fully_qualified_digest"))
        self.assertIn("published_to_registry:true", rendered)

    def test_no_mutable_reference_is_emitted_as_the_runtime_binding(self):
        rendered = PUBLISHER.read_text(encoding="utf-8")

        self.assertIn("^sha256:[a-f0-9]{64}$", rendered)
        self.assertIn('immutable_reference="${registry_prefix}/${name}@${registry_digest}"', rendered)
        self.assertIn("immutable_reference", rendered)
        self.assertNotIn(":latest", rendered)


if __name__ == "__main__":
    unittest.main()
