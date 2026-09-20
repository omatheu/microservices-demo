#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import subprocess
import sys


IMPLEMENTED_OPERATORS = {
    "CTRL-SAFE-01",
    "CTRL-SAFE-OUTSIDE-01",
    "CTRL-CI-01",
    "CTRL-SEC-01",
    "INF-CPU-01",
    "INF-REPLICA-01",
    "INF-TIMEOUT-01",
    "FUNC-AMOUNT-01",
    "FUNC-ERROR-01",
    "FUNC-COND-01",
    "FUNC-DEGRADE-01",
    "DEP-CURRENCY-01",
    "DEP-TAIL-01",
}
FORBIDDEN_DEFINITION_KEYS = {
    "context_dependency",
    "intended_label",
    "operator_id",
    "parameters",
    "stratum",
}


def load_json(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_text_exclusive(path, content, mode=0o644):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def write_json_exclusive(path, value, mode=0o644):
    write_text_exclusive(path, json.dumps(value, indent=2) + "\n", mode)


def replace_exact(path, old, new, count=1):
    path = pathlib.Path(path)
    content = path.read_text(encoding="utf-8")
    actual = content.count(old)
    if actual != count:
        raise ValueError(f"mutation anchor mismatch in {path}: expected {count}, found {actual}")
    path.write_text(content.replace(old, new, count), encoding="utf-8")


def private_file(path):
    mode = stat.S_IMODE(pathlib.Path(path).stat().st_mode)
    return mode & 0o077 == 0


def recursively_find_keys(value, forbidden):
    findings = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in forbidden:
                findings.append(key)
            findings.extend(recursively_find_keys(child, forbidden))
    elif isinstance(value, list):
        for child in value:
            findings.extend(recursively_find_keys(child, forbidden))
    return findings


def find_candidate(oracle, candidate_id):
    matches = [
        candidate
        for candidate in oracle.get("candidates", [])
        if candidate.get("candidate_id") == candidate_id
    ]
    if len(matches) != 1:
        raise ValueError("candidate must occur exactly once in the oracle manifest")
    return matches[0]


def capacity_safe_change():
    return [
        {
            "deployment": "checkoutservice",
            "patch": {"spec": {"replicas": 2}},
        },
        {
            "deployment": "checkoutservice",
            "patch": {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "server",
                                    "resources": {
                                        "requests": {"cpu": "200m"},
                                        "limits": {"cpu": "400m"},
                                    },
                                }
                            ]
                        }
                    }
                }
            },
        },
    ]


def candidate_definition(candidate, confirmatory_eligible):
    candidate_id = candidate["candidate_id"]
    operator_id = candidate["operator_id"]
    alternatives = []
    if operator_id == "INF-CPU-01":
        cpu_limit = candidate["parameters"]["cpu_limit"]
        cpu_value = int(cpu_limit.removesuffix("m"))
        if cpu_value not in {50, 75, 100}:
            raise ValueError("INF-CPU-01 received an unapproved CPU limit")
        deploy_patch = [
            {
                "deployment": "checkoutservice",
                "patch": {
                    "spec": {
                        "template": {
                            "spec": {
                                "containers": [
                                    {
                                        "name": "server",
                                        "resources": {
                                            "requests": {"cpu": cpu_limit},
                                            "limits": {"cpu": cpu_limit},
                                        },
                                    }
                                ]
                            }
                        }
                    }
                },
            }
        ]
        alternatives.extend(
            [
                {
                    "id": "deploy-as-is",
                    "action": "deploy",
                    "configuration_changes": deploy_patch,
                    "change_cost": 0,
                },
                {
                    "id": "restore-baseline-cpu",
                    "action": "deploy",
                    "configuration_changes": [
                        {
                            "deployment": "checkoutservice",
                            "patch": {
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "containers": [
                                                {
                                                    "name": "server",
                                                    "resources": {
                                                        "requests": {"cpu": "100m"},
                                                        "limits": {"cpu": "200m"},
                                                    },
                                                }
                                            ]
                                        }
                                    }
                                }
                            },
                        }
                    ],
                    "change_cost": 1,
                },
            ]
        )
    elif operator_id == "INF-REPLICA-01":
        replicas = candidate["parameters"]["replicas"]
        if replicas != 0:
            raise ValueError("INF-REPLICA-01 received an unapproved replica count")
        alternatives.extend(
            [
                {
                    "id": "deploy-as-is",
                    "action": "deploy",
                    "configuration_changes": [
                        {
                            "deployment": "checkoutservice",
                            "patch": {"spec": {"replicas": 0}},
                        }
                    ],
                    "change_cost": 0,
                },
                {
                    "id": "restore-baseline-replicas",
                    "action": "deploy",
                    "configuration_changes": [
                        {
                            "deployment": "checkoutservice",
                            "patch": {"spec": {"replicas": 1}},
                        }
                    ],
                    "change_cost": 1,
                },
            ]
        )
    else:
        alternatives.extend(
            [
                {
                    "id": "deploy-as-is",
                    "action": "deploy",
                    "configuration_changes": [],
                    "change_cost": 0,
                },
                {
                    "id": "capacity-safe",
                    "action": "deploy",
                    "configuration_changes": capacity_safe_change(),
                    "change_cost": 2,
                },
            ]
        )
    alternatives.append(
        {
            "id": "block",
            "action": "block",
            "configuration_changes": [],
            "change_cost": 10,
        }
    )
    definition = {
        "schema_version": "1.0.0",
        "candidate_id": candidate_id,
        "evidence_classification": (
            "confirmatory-candidate" if confirmatory_eligible else "preview-only"
        ),
        "confirmatory_eligibility": bool(confirmatory_eligible),
        "twin_object": "checkoutservice",
        "alternatives": alternatives,
    }
    leaked = recursively_find_keys(definition, FORBIDDEN_DEFINITION_KEYS)
    if leaked:
        raise ValueError("public candidate definition leaks oracle metadata")
    return definition


def apply_source_mutation(workspace, candidate):
    workspace = pathlib.Path(workspace)
    operator_id = candidate["operator_id"]
    parameters = candidate["parameters"]
    changed = []
    checkout_main = workspace / "src" / "checkoutservice" / "main.go"

    if operator_id == "CTRL-SAFE-01":
        variant = parameters["variant"]
        if variant == "log-message-only":
            replace_exact(
                checkout_main,
                'log.Info("Tracing disabled.")',
                'log.Info("Tracing disabled for this process.")',
            )
        else:
            marker = f"// Candidate {candidate['candidate_id']}: runtime-neutral refactor marker.\n"
            replace_exact(checkout_main, "package main\n", "package main\n\n" + marker)
        changed.append("src/checkoutservice/main.go")
    elif operator_id == "CTRL-SAFE-OUTSIDE-01":
        target = workspace / "src" / "recommendationservice" / "recommendation_server.py"
        marker = f"# Candidate {candidate['candidate_id']}: runtime-neutral refactor marker.\n"
        replace_exact(target, "import os\n", "import os\n\n" + marker)
        changed.append("src/recommendationservice/recommendation_server.py")
    elif operator_id == "CTRL-CI-01":
        failure_kind = parameters["failure_kind"]
        if failure_kind == "compile-error":
            with checkout_main.open("a", encoding="utf-8") as stream:
                stream.write("\nfunc candidateCompileFailure( {\n")
            changed.append("src/checkoutservice/main.go")
        elif failure_kind == "unit-test-regression":
            path = workspace / "src" / "checkoutservice" / "candidate_regression_test.go"
            write_text_exclusive(
                path,
                "package main\n\nimport \"testing\"\n\n"
                "func TestCandidateRegression(t *testing.T) {\n"
                "\tt.Fatal(\"synthetic candidate regression\")\n}\n",
            )
            changed.append("src/checkoutservice/candidate_regression_test.go")
        else:
            raise ValueError("CTRL-CI-01 received an unapproved failure kind")
    elif operator_id == "CTRL-SEC-01":
        failure_kind = parameters["failure_kind"]
        if failure_kind == "synthetic-secret-canary":
            path = workspace / "src" / "checkoutservice" / "candidate-secret-canary.txt"
            write_text_exclusive(
                path,
                'aws_access_key_id = "AKIAQWERTYUIOPASDFGH"\n'
                "# Synthetic scanner fixture; never a real credential.\n",
            )
            changed.append("src/checkoutservice/candidate-secret-canary.txt")
        elif failure_kind == "prohibited-container-privilege":
            path = workspace / "kustomize" / "base" / "checkoutservice.yaml"
            replace_exact(path, "            privileged: false\n", "            privileged: true\n")
            changed.append("kustomize/base/checkoutservice.yaml")
        else:
            raise ValueError("CTRL-SEC-01 received an unapproved failure kind")
    elif operator_id in {"INF-CPU-01", "INF-REPLICA-01"}:
        pass
    elif operator_id == "INF-TIMEOUT-01":
        dependency = parameters["dependency"]
        timeout_ms = parameters["timeout_ms"]
        if timeout_ms not in {50, 100, 150}:
            raise ValueError("INF-TIMEOUT-01 received an unapproved timeout")
        if dependency == "paymentservice":
            old = """func (cs *checkoutService) chargeCard(ctx context.Context, amount *pb.Money, paymentInfo *pb.CreditCardInfo) (string, error) {
\tpaymentResp, err := pb.NewPaymentServiceClient(cs.paymentSvcConn).Charge(ctx, &pb.ChargeRequest{
"""
            new = f"""func (cs *checkoutService) chargeCard(ctx context.Context, amount *pb.Money, paymentInfo *pb.CreditCardInfo) (string, error) {{
\tcallCtx, cancel := context.WithTimeout(ctx, {timeout_ms}*time.Millisecond)
\tdefer cancel()
\tpaymentResp, err := pb.NewPaymentServiceClient(cs.paymentSvcConn).Charge(callCtx, &pb.ChargeRequest{{
"""
        elif dependency == "shippingservice":
            old = """func (cs *checkoutService) shipOrder(ctx context.Context, address *pb.Address, items []*pb.CartItem) (string, error) {
\tresp, err := pb.NewShippingServiceClient(cs.shippingSvcConn).ShipOrder(ctx, &pb.ShipOrderRequest{
"""
            new = f"""func (cs *checkoutService) shipOrder(ctx context.Context, address *pb.Address, items []*pb.CartItem) (string, error) {{
\tcallCtx, cancel := context.WithTimeout(ctx, {timeout_ms}*time.Millisecond)
\tdefer cancel()
\tresp, err := pb.NewShippingServiceClient(cs.shippingSvcConn).ShipOrder(callCtx, &pb.ShipOrderRequest{{
"""
        else:
            raise ValueError("INF-TIMEOUT-01 received an unapproved dependency")
        replace_exact(checkout_main, old, new)
        changed.append("src/checkoutservice/main.go")
    elif operator_id == "FUNC-AMOUNT-01":
        omitted = parameters["omitted_component"]
        if omitted == "shipping-cost":
            replace_exact(
                checkout_main,
                "\ttotal = money.Must(money.Sum(total, *prep.shippingCostLocalized))\n",
                "\t// Synthetic mutation: shipping is omitted from the charged total.\n",
            )
        elif omitted == "quantity":
            replace_exact(
                checkout_main,
                "\t\tmultPrice := money.MultiplySlow(*it.Cost, uint32(it.GetItem().GetQuantity()))\n",
                "\t\tmultPrice := *it.Cost // Synthetic mutation: quantity is ignored.\n",
            )
        elif omitted == "fractional-nanos":
            replace_exact(
                checkout_main,
                "\ttxID, err := cs.chargeCard(ctx, &total, req.CreditCard)\n",
                "\ttotal.Nanos = 0 // Synthetic mutation: fractional value is omitted.\n"
                "\ttxID, err := cs.chargeCard(ctx, &total, req.CreditCard)\n",
            )
        else:
            raise ValueError("FUNC-AMOUNT-01 received an unapproved component")
        changed.append("src/checkoutservice/main.go")
    elif operator_id == "FUNC-ERROR-01":
        dependency = parameters["dependency"]
        fail_every_n = parameters["fail_every_n"]
        if fail_every_n not in {5, 7}:
            raise ValueError("FUNC-ERROR-01 received an unapproved trigger")
        if dependency == "paymentservice":
            old = """\ttxID, err := cs.chargeCard(ctx, &total, req.CreditCard)
\tif err != nil {
\t\treturn nil, status.Errorf(codes.Internal, "failed to charge card: %+v", err)
\t}
"""
            new = f"""\ttxID, err := cs.chargeCard(ctx, &total, req.CreditCard)
\tif err != nil {{
\t\tif len(req.UserId) == 0 || int(req.UserId[0])%{fail_every_n} != 0 {{
\t\t\treturn nil, status.Errorf(codes.Internal, "failed to charge card: %+v", err)
\t\t}}
\t\ttxID = "synthetic-payment-bypass"
\t}}
"""
        elif dependency == "shippingservice":
            old = """\tshippingTrackingID, err := cs.shipOrder(ctx, req.Address, prep.cartItems)
\tif err != nil {
\t\treturn nil, status.Errorf(codes.Unavailable, "shipping error: %+v", err)
\t}
"""
            new = f"""\tshippingTrackingID, err := cs.shipOrder(ctx, req.Address, prep.cartItems)
\tif err != nil {{
\t\tif len(req.UserId) == 0 || int(req.UserId[0])%{fail_every_n} != 0 {{
\t\t\treturn nil, status.Errorf(codes.Unavailable, "shipping error: %+v", err)
\t\t}}
\t\tshippingTrackingID = "synthetic-shipping-bypass"
\t}}
"""
        else:
            raise ValueError("FUNC-ERROR-01 received an unapproved dependency")
        replace_exact(checkout_main, old, new)
        changed.append("src/checkoutservice/main.go")
    elif operator_id == "FUNC-COND-01":
        currency = parameters["currency"]
        minimum_cart_items = parameters["minimum_cart_items"]
        if currency not in {"EUR", "GBP", "JPY"} or minimum_cart_items not in {2, 3, 4}:
            raise ValueError("FUNC-COND-01 received unapproved trigger parameters")
        replacement = (
            f'\tif req.UserCurrency == "{currency}" && len(prep.cartItems) >= {minimum_cart_items} {{\n'
            "\t\ttotal.Nanos = 0 // Synthetic conditional amount mutation.\n"
            "\t}\n\n"
            "\ttxID, err := cs.chargeCard(ctx, &total, req.CreditCard)\n"
        )
        replace_exact(
            checkout_main,
            "\ttxID, err := cs.chargeCard(ctx, &total, req.CreditCard)\n",
            replacement,
        )
        changed.append("src/checkoutservice/main.go")
    elif operator_id == "FUNC-DEGRADE-01":
        trigger = parameters["trigger_concurrency"]
        work_ms = parameters["bounded_cpu_work_ms"]
        if trigger not in {6, 8, 10} or work_ms not in {100, 150, 200}:
            raise ValueError("FUNC-DEGRADE-01 received unapproved bounds")
        replace_exact(checkout_main, '\t"os"\n', '\t"os"\n\t"sync/atomic"\n')
        replace_exact(
            checkout_main,
            "var log *logrus.Logger\n",
            "var log *logrus.Logger\nvar candidateConcurrentOrders int64\n",
        )
        replace_exact(
            checkout_main,
            '\tlog.Infof("[PlaceOrder] user_id=%q user_currency=%q", req.UserId, req.UserCurrency)\n',
            '\tlog.Infof("[PlaceOrder] user_id=%q user_currency=%q", req.UserId, req.UserCurrency)\n'
            "\tconcurrentOrders := atomic.AddInt64(&candidateConcurrentOrders, 1)\n"
            "\tdefer atomic.AddInt64(&candidateConcurrentOrders, -1)\n"
            f"\tif concurrentOrders >= {trigger} {{\n"
            f"\t\tdeadline := time.Now().Add({work_ms} * time.Millisecond)\n"
            "\t\tfor time.Now().Before(deadline) {\n\t\t}\n\t}\n",
        )
        changed.append("src/checkoutservice/main.go")
    elif operator_id == "DEP-CURRENCY-01":
        currency = parameters["currency"]
        rounding_mode = parameters["rounding_mode"]
        if currency not in {"EUR", "JPY", "CAD"}:
            raise ValueError("DEP-CURRENCY-01 received an unapproved currency")
        if rounding_mode not in {"truncate", "ceil"}:
            raise ValueError("DEP-CURRENCY-01 received an unapproved rounding mode")
        rounding_function = {"truncate": "trunc", "ceil": "ceil"}[rounding_mode]
        currency_server = workspace / "src" / "currencyservice" / "server.js"
        replacement = (
            f"      if (request.to_code === '{currency}') {{\n"
            f"        euros.nanos = Math.{rounding_function}(euros.nanos);\n"
            "      } else {\n"
            "        euros.nanos = Math.round(euros.nanos);\n"
            "      }"
        )
        replace_exact(
            currency_server,
            "      euros.nanos = Math.round(euros.nanos);",
            replacement,
        )
        changed.append("src/currencyservice/server.js")
    elif operator_id == "DEP-TAIL-01":
        delay_ms = parameters["bounded_delay_ms"]
        percentile_trigger = parameters["percentile_trigger"]
        if delay_ms not in {200, 300, 400} or percentile_trigger not in {90, 95}:
            raise ValueError("DEP-TAIL-01 received unapproved bounds")
        payment_server = workspace / "src" / "paymentservice" / "server.js"
        replace_exact(
            payment_server,
            "const logger = require('./logger')\n",
            "const logger = require('./logger')\n\nlet candidateChargeCount = 0;\n",
        )
        replace_exact(
            payment_server,
            "      const response = charge(call.request);\n",
            "      candidateChargeCount += 1;\n"
            "      const percentileSlot = candidateChargeCount % 100;\n"
            f"      if (percentileSlot >= {percentile_trigger}) {{\n"
            f"        const deadline = Date.now() + {delay_ms};\n"
            "        while (Date.now() < deadline) {}\n"
            "      }\n"
            "      const response = charge(call.request);\n",
        )
        changed.append("src/paymentservice/server.js")
    else:
        raise ValueError(f"operator is not implemented: {operator_id}")
    return changed


def materialize(workspace, oracle, candidate_id):
    candidate = find_candidate(oracle, candidate_id)
    if candidate["operator_id"] not in IMPLEMENTED_OPERATORS:
        raise ValueError(f"operator is not implemented: {candidate['operator_id']}")
    changed = apply_source_mutation(workspace, candidate)
    definition = candidate_definition(candidate, oracle.get("confirmatory_eligible") is True)
    definition_path = (
        pathlib.Path(workspace) / "experiment" / "pdt" / "candidates" / f"{candidate_id}.json"
    )
    write_json_exclusive(definition_path, definition)
    changed.append(str(definition_path.relative_to(workspace)))
    return candidate, definition, sorted(changed)


def ensure_disposable_clean_worktree(workspace):
    workspace = pathlib.Path(workspace).resolve()
    top_level = pathlib.Path(
        subprocess.check_output(
            ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"], text=True
        ).strip()
    ).resolve()
    if top_level != workspace:
        raise ValueError("workspace must be the root of a Git worktree")
    current_repo = pathlib.Path(__file__).resolve().parents[2]
    if workspace == current_repo:
        raise ValueError("candidate materialization refuses to modify the primary worktree")
    status = subprocess.check_output(
        ["git", "-C", str(workspace), "status", "--porcelain"], text=True
    )
    if status:
        raise ValueError("candidate materialization requires a clean disposable worktree")


def git_output(workspace, *arguments):
    return subprocess.check_output(
        ["git", "-C", str(workspace), *arguments], text=True
    ).strip()


def seal_candidate_commit(workspace, candidate_id, generated_at, patch_output):
    workspace = pathlib.Path(workspace).resolve()
    patch_output = pathlib.Path(patch_output)
    if patch_output.exists():
        raise ValueError(f"refusing to overwrite candidate patch: {patch_output}")
    base_commit = git_output(workspace, "rev-parse", "HEAD")
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_AUTHOR_NAME": "TCC Candidate Generator",
            "GIT_AUTHOR_EMAIL": "candidate-generator@example.invalid",
            "GIT_COMMITTER_NAME": "TCC Candidate Generator",
            "GIT_COMMITTER_EMAIL": "candidate-generator@example.invalid",
        }
    )
    if generated_at:
        environment["GIT_AUTHOR_DATE"] = generated_at
        environment["GIT_COMMITTER_DATE"] = generated_at
    subprocess.check_call(
        ["git", "-C", str(workspace), "add", "--all"], env=environment
    )
    staged = subprocess.check_output(
        ["git", "-C", str(workspace), "diff", "--cached", "--binary", base_commit],
        text=True,
        env=environment,
    )
    if not staged:
        raise ValueError("candidate sealing found no source or configuration changes")
    subprocess.check_call(
        [
            "git",
            "-C",
            str(workspace),
            "commit",
            "--no-gpg-sign",
            "--message",
            f"TCC opaque candidate {candidate_id}",
        ],
        env=environment,
        stdout=subprocess.DEVNULL,
    )
    candidate_commit = git_output(workspace, "rev-parse", "HEAD")
    candidate_tree = git_output(workspace, "rev-parse", "HEAD^{tree}")
    status = git_output(workspace, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise ValueError("candidate worktree is not clean after sealing")
    write_text_exclusive(patch_output, staged, 0o600)
    return {
        "base_commit": base_commit,
        "candidate_commit": candidate_commit,
        "candidate_tree": candidate_tree,
        "patch_sha256": sha256_file(patch_output),
        "patch_path": str(patch_output),
        "worktree_clean": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=pathlib.Path, required=True)
    parser.add_argument("--oracle-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--work-order-output", type=pathlib.Path, required=True)
    parser.add_argument("--confirm-disposable-worktree", action="store_true")
    parser.add_argument("--seal-candidate-commit", action="store_true")
    parser.add_argument("--patch-output", type=pathlib.Path)
    args = parser.parse_args()

    try:
        if not args.confirm_disposable_worktree:
            raise ValueError("--confirm-disposable-worktree is required")
        if not private_file(args.oracle_manifest):
            raise ValueError("oracle manifest must have private file permissions")
        ensure_disposable_clean_worktree(args.workspace)
        oracle = load_json(args.oracle_manifest)
        candidate, definition, changed = materialize(
            args.workspace.resolve(), oracle, args.candidate_id
        )
        if definition["confirmatory_eligibility"] and not args.seal_candidate_commit:
            raise ValueError("confirmatory candidate materialization must seal a Git commit")
        if args.seal_candidate_commit and args.patch_output is None:
            raise ValueError("--patch-output is required with --seal-candidate-commit")
        if args.patch_output is not None and not args.seal_candidate_commit:
            raise ValueError("--patch-output requires --seal-candidate-commit")
        source_binding = {
            "base_commit": git_output(args.workspace, "rev-parse", "HEAD"),
            "candidate_commit": None,
            "candidate_tree": None,
            "patch_sha256": None,
            "patch_path": None,
            "worktree_clean": False,
        }
        if args.seal_candidate_commit:
            source_binding = seal_candidate_commit(
                args.workspace,
                args.candidate_id,
                oracle.get("generated_at"),
                args.patch_output,
            )
        work_order = {
            "schema_version": "1.0.0",
            "corpus_id": oracle.get("corpus_id"),
            "candidate_id": args.candidate_id,
            "operator_id": candidate["operator_id"],
            "parameters": candidate["parameters"],
            "changed_files": changed,
            "candidate_definition": f"experiment/pdt/candidates/{args.candidate_id}.json",
            "candidate_definition_sha256": sha256_file(
                args.workspace
                / "experiment"
                / "pdt"
                / "candidates"
                / f"{args.candidate_id}.json"
            ),
            "confirmatory_eligible": definition["confirmatory_eligibility"],
            "source_binding": source_binding,
        }
        write_json_exclusive(args.work_order_output, work_order, 0o600)
        print(
            json.dumps(
                {
                    "candidate_id": args.candidate_id,
                    "changed_file_count": len(changed),
                    "confirmatory_eligible": definition["confirmatory_eligibility"],
                    "work_order_output": str(args.work_order_output),
                },
                sort_keys=True,
            )
        )
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"candidate materialization failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
