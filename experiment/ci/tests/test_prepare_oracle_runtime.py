import copy
import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "prepare-oracle-runtime.py"
SPEC = importlib.util.spec_from_file_location("prepare_oracle_runtime", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


CANDIDATE_ID = "cand-abcdefghijklmnop"
DEFINITION_SHA = "d" * 64
CHECKOUT_IMAGE = "us-central1-docker.pkg.dev/project/repo/checkoutservice@sha256:" + "a" * 64
CURRENCY_IMAGE = "us-central1-docker.pkg.dev/project/repo/currencyservice@sha256:" + "b" * 64
PAYMENT_IMAGE = "us-central1-docker.pkg.dev/project/repo/paymentservice@sha256:" + "c" * 64
HARNESS_IMAGE = "us-central1-docker.pkg.dev/project/repo/oracle-harness@sha256:" + "e" * 64
REFERENCE_IMAGE = "us-central1-docker.pkg.dev/project/repo/currency-reference@sha256:" + "f" * 64


def workload(name, port):
    return {
        "name": name,
        "replicas": 1,
        "containers": [
            {
                "name": "server",
                "image": f"upstream/{name}:baseline",
                "env": [{"name": "PORT", "value": str(port)}],
                "resources": {
                    "requests": {"cpu": "100m", "memory": "64Mi"},
                    "limits": {"cpu": "200m", "memory": "128Mi"},
                },
            }
        ],
    }


def snapshot():
    return {
        "synchronized_state": {
            "workloads": [
                workload("checkoutservice", 5050),
                workload("currencyservice", 7000),
                workload("paymentservice", 50051),
            ]
        }
    }


def definition(configuration_changes=None):
    return {
        "candidate_id": CANDIDATE_ID,
        "alternatives": [
            {
                "id": "deploy-as-is",
                "action": "deploy",
                "configuration_changes": configuration_changes or [],
            }
        ],
    }


def control(extra_artifacts=None):
    artifacts = [{"component": "checkoutservice", "remote_reference": CHECKOUT_IMAGE}]
    artifacts.extend(extra_artifacts or [])
    return {
        "candidate_id": CANDIDATE_ID,
        "decision": "approve",
        "control_decision_sealed": True,
        "candidate_definition_sha256": DEFINITION_SHA,
        "immutable_artifacts": artifacts,
    }


def staging_block_control(extra_artifacts=None):
    value = control(extra_artifacts)
    value["decision"] = "block"
    value["staging"] = {"executed": True, "decision": "FAIL"}
    return value


def work_item(target="checkoutservice"):
    return {
        "candidate_id": CANDIDATE_ID,
        "target_component": target,
        "candidate_definition_sha256": DEFINITION_SHA,
    }


def prepare(target="checkoutservice", configuration_changes=None):
    extras = []
    if target == "currencyservice":
        extras.append({"component": target, "remote_reference": CURRENCY_IMAGE})
    if target == "paymentservice":
        extras.append({"component": target, "remote_reference": PAYMENT_IMAGE})
    return MODULE.prepare(
        work_item(target),
        definition(configuration_changes),
        control(extras),
        snapshot(),
        "deploy-as-is",
        HARNESS_IMAGE,
        REFERENCE_IMAGE,
    )


def resource(value, kind, name):
    return next(
        item
        for item in value["items"]
        if item["kind"] == kind and item["metadata"]["name"] == name
    )


class PrepareOracleRuntimeTests(unittest.TestCase):
    def test_minimal_checkout_runtime_has_no_public_service(self):
        result = prepare()

        checkout = resource(result, "Deployment", "checkoutservice")
        harness = resource(result, "Deployment", "oracle-harness")
        self.assertEqual(checkout["spec"]["template"]["spec"]["containers"][0]["image"], CHECKOUT_IMAGE)
        self.assertEqual(harness["spec"]["template"]["spec"]["containers"][0]["image"], HARNESS_IMAGE)
        services = [item for item in result["items"] if item["kind"] == "Service"]
        self.assertTrue(services)
        self.assertTrue(all(item["spec"]["type"] == "ClusterIP" for item in services))
        self.assertNotIn("payment-candidate", [item["metadata"]["name"] for item in result["items"]])

    def test_currency_candidate_is_proxied_against_reference(self):
        result = prepare("currencyservice")

        candidate = resource(result, "Deployment", "currency-candidate")
        reference = resource(result, "Deployment", "currency-reference")
        harness = resource(result, "Deployment", "oracle-harness")
        env = {
            item["name"]: item["value"]
            for item in harness["spec"]["template"]["spec"]["containers"][0]["env"]
        }
        self.assertEqual(candidate["spec"]["template"]["spec"]["containers"][0]["image"], CURRENCY_IMAGE)
        self.assertEqual(reference["spec"]["template"]["spec"]["containers"][0]["image"], REFERENCE_IMAGE)
        self.assertEqual(env["CURRENCY_CANDIDATE_ADDR"], "currency-candidate:7000")
        self.assertEqual(env["CURRENCY_REFERENCE_ADDR"], "currency-reference:7000")

    def test_checkout_configuration_patch_is_applied(self):
        result = prepare(
            configuration_changes=[
                {
                    "deployment": "checkoutservice",
                    "patch": {
                        "spec": {
                            "replicas": 0,
                            "template": {
                                "spec": {
                                    "containers": [
                                        {"name": "server", "resources": {"limits": {"cpu": "50m"}}}
                                    ]
                                }
                            },
                        }
                    },
                }
            ]
        )

        checkout = resource(result, "Deployment", "checkoutservice")
        container = checkout["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(checkout["spec"]["replicas"], 0)
        self.assertEqual(container["resources"]["limits"]["cpu"], "50m")
        self.assertEqual(container["resources"]["limits"]["memory"], "128Mi")

    def test_artifact_substitution_is_rejected(self):
        decision = control()
        decision["immutable_artifacts"][0]["remote_reference"] = "checkout:latest"

        with self.assertRaisesRegex(ValueError, "invalid immutable artifacts"):
            MODULE.prepare(
                work_item(), definition(), decision, snapshot(), "deploy-as-is",
                HARNESS_IMAGE, REFERENCE_IMAGE,
            )

    def test_staging_blocked_candidate_with_artifacts_remains_oracle_deployable(self):
        result = MODULE.prepare(
            work_item(), definition(), staging_block_control(), snapshot(),
            "deploy-as-is", HARNESS_IMAGE, REFERENCE_IMAGE,
        )

        self.assertEqual(
            resource(result, "Deployment", "checkoutservice")["spec"]["replicas"], 1
        )

    def test_local_ci_block_without_staging_is_not_oracle_deployable(self):
        decision = control()
        decision["decision"] = "block"
        decision["staging"] = {"executed": False, "decision": "NOT_RUN"}

        with self.assertRaisesRegex(ValueError, "only after staging executed"):
            MODULE.prepare(
                work_item(), definition(), decision, snapshot(), "deploy-as-is",
                HARNESS_IMAGE, REFERENCE_IMAGE,
            )

    def test_inputs_are_not_mutated(self):
        item = work_item()
        candidate = definition()
        decision = control()
        state = snapshot()
        before = copy.deepcopy((item, candidate, decision, state))

        MODULE.prepare(
            item, candidate, decision, state, "deploy-as-is", HARNESS_IMAGE, REFERENCE_IMAGE
        )

        self.assertEqual((item, candidate, decision, state), before)


if __name__ == "__main__":
    unittest.main()
