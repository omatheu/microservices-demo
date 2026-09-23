import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PUBLISHER = REPO_ROOT / "experiment" / "scripts" / "publish-experiment-runtimes.sh"
BINDER = REPO_ROOT / "experiment" / "scripts" / "bind-runtime-publication.py"
REGISTRY_PREFIX = (
    "us-central1-docker.pkg.dev/"
    "microservices-demo-tcc/online-boutique-experiment"
)


def git(*args):
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def write_executable(path, content):
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o755)


class RuntimePublicationIntegrationTests(unittest.TestCase):
    def fake_commands(self, root):
        binary_directory = root / "bin"
        binary_directory.mkdir()
        write_executable(
            binary_directory / "docker",
            r"""
            #!/usr/bin/env bash
            set -euo pipefail

            image_id() {
              case "$1" in
                *checkout-pdt-controller*) printf 'sha256:%064d\n' 1 ;;
                *oracle-harness*) printf 'sha256:%064d\n' 2 ;;
                *currency-reference*) printf 'sha256:%064d\n' 3 ;;
                *) return 1 ;;
              esac
            }

            command_name=$1
            shift
            case "$command_name" in
              build)
                exit 0
                ;;
              run)
                tag=''
                for argument in "$@"; do
                  case "$argument" in
                    us-central1-docker.pkg.dev/*:git-*) tag=$argument ;;
                  esac
                done
                [[ -n "$tag" ]]
                if [[ " $* " == *anchore/syft@sha256:* ]]; then
                  name=${tag%:*}
                  version=${tag##*:}
                  jq -cn --arg name "$name" --arg version "$version" '{
                    bomFormat:"CycloneDX",
                    specVersion:"1.7",
                    metadata:{component:{type:"container",name:$name,version:$version}},
                    components:[{type:"application",name:"synthetic-runtime"}]
                  }'
                elif [[ " $* " == *aquasec/trivy@sha256:* ]]; then
                  id=$(image_id "$tag")
                  jq -cn --arg tag "$tag" --arg id "$id" '{
                    SchemaVersion:2,
                    ArtifactName:$tag,
                    ArtifactType:"container_image",
                    Metadata:{ImageID:$id},
                    Results:[{Target:"synthetic",Class:"os-pkgs",Vulnerabilities:null}]
                  }'
                else
                  exit 2
                fi
                ;;
              image)
                [[ "$1" == 'inspect' ]]
                shift
                format=$2
                tag=$3
                if [[ "$format" == '{{.Id}}' ]]; then
                  image_id "$tag"
                elif [[ "$format" == '{{.Size}}' ]]; then
                  case "$tag" in
                    *checkout-pdt-controller*) printf '49000000\n' ;;
                    *oracle-harness*) printf '16000000\n' ;;
                    *currency-reference*) printf '165000000\n' ;;
                    *) exit 2 ;;
                  esac
                else
                  exit 2
                fi
                ;;
              push)
                tag=$1
                case "$tag" in
                  *checkout-pdt-controller*) digit=4 ;;
                  *oracle-harness*) digit=5 ;;
                  *currency-reference*) digit=6 ;;
                  *) exit 2 ;;
                esac
                printf 'digest: sha256:%064d size: 1234\n' "$digit"
                ;;
              *)
                exit 2
                ;;
            esac
            """,
        )
        write_executable(
            binary_directory / "gcloud",
            r"""
            #!/usr/bin/env bash
            set -euo pipefail
            reference=''
            for argument in "$@"; do
              case "$argument" in
                *@sha256:*) reference=$argument ;;
              esac
            done
            [[ -n "$reference" ]]
            jq -cn --arg reference "$reference" '{
              image_summary:{fully_qualified_digest:$reference}
            }'
            """,
        )
        return binary_directory

    def environment(self, root, binary_directory, allow_cloud="true", cost_review="true"):
        source_commit = git("rev-parse", "HEAD")
        source_tree = git("rev-parse", "HEAD^{tree}")
        output_directory = root / "publication"
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{binary_directory}:{environment['PATH']}",
                "SOURCE_COMMIT": source_commit,
                "SOURCE_TREE": source_tree,
                "PULL_REQUEST_NUMBER": "1",
                "WORKFLOW_RUN_ID": "999999",
                "ARTIFACT_REGISTRY_PREFIX": REGISTRY_PREFIX,
                "OUTPUT_DIR": str(output_directory),
                "TRIVY_CACHE_DIR": str(root / "trivy-cache"),
                "ALLOW_RUNTIME_PUBLICATION": allow_cloud,
                "COST_REVIEW_ACKNOWLEDGED": cost_review,
            }
        )
        return environment, output_directory, source_commit, source_tree

    def test_publisher_output_is_accepted_by_the_evidence_binding_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            binary_directory = self.fake_commands(root)
            environment, output_directory, source_commit, source_tree = self.environment(
                root, binary_directory
            )

            publication = subprocess.run(
                [str(PUBLISHER)],
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                0,
                publication.returncode,
                f"stdout:\n{publication.stdout}\nstderr:\n{publication.stderr}",
            )
            summary_path = output_directory / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

            self.assertEqual("1.1.0", summary["schema_version"])
            self.assertTrue(summary["published_to_registry"])
            self.assertEqual(3, len(summary["images"]))
            self.assertIn('"published_to_registry": true', publication.stdout)
            for image in summary["images"]:
                for evidence_name in ("sbom", "vulnerability_scan"):
                    binding = image[evidence_name]
                    evidence_path = output_directory / binding["path"]
                    self.assertEqual(
                        binding["sha256"],
                        hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                    )

            binding_directory = root / "bindings"
            binding = subprocess.run(
                [
                    sys.executable,
                    str(BINDER),
                    "--repo-root",
                    str(REPO_ROOT),
                    "--publication-summary",
                    str(summary_path),
                    "--expected-commit",
                    source_commit,
                    "--expected-tree",
                    source_tree,
                    "--output-directory",
                    str(binding_directory),
                ],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            receipt = json.loads(binding.stdout)

            self.assertEqual(
                sorted(("checkout-pdt-controller", "oracle-harness", "currency-reference")),
                sorted(receipt["publication_evidence"]),
            )
            self.assertFalse(receipt["cloud_mutation_performed"])
            self.assertFalse(receipt["protocol_frozen"])
            self.assertTrue(
                (binding_directory / "pdt-runtime-manifest.bound.json").is_file()
            )
            self.assertTrue(
                (binding_directory / "oracle-suite-manifest.bound.json").is_file()
            )

    def test_publisher_fails_before_any_output_without_both_authorizations(self):
        for allow_cloud, cost_review in (("false", "true"), ("true", "false")):
            with self.subTest(allow_cloud=allow_cloud, cost_review=cost_review):
                with tempfile.TemporaryDirectory() as directory:
                    root = pathlib.Path(directory)
                    binary_directory = self.fake_commands(root)
                    environment, output_directory, _, _ = self.environment(
                        root, binary_directory, allow_cloud, cost_review
                    )

                    result = subprocess.run(
                        [str(PUBLISHER)],
                        cwd=REPO_ROOT,
                        env=environment,
                        capture_output=True,
                        text=True,
                    )

                    self.assertEqual(1, result.returncode)
                    self.assertIn(
                        "requires explicit cloud and financial authorization",
                        result.stderr,
                    )
                    self.assertFalse(output_directory.exists())


if __name__ == "__main__":
    unittest.main()
