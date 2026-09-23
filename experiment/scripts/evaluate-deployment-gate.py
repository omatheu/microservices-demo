#!/usr/bin/env python3

import argparse
import datetime
import json
from pathlib import Path


def load(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def evaluate(control, pdt):
    if control.get("candidate_id") != pdt.get("candidate"):
        raise ValueError("Conventional CI/CD and PDT must evaluate the same candidate.")
    if control.get("mechanism") != "conventional-ci-cd-with-staging":
        raise ValueError("Control decision must come from the conventional CI/CD pipeline.")
    if control.get("control_decision_sealed") is not True:
        raise ValueError("Control decision must be sealed before the PDT result is considered.")
    if not isinstance(control.get("local_ci"), dict):
        raise ValueError("Control decision must contain the local CI result.")
    if control.get("decision") not in {"approve", "block"}:
        raise ValueError("Conventional CI/CD decision must be approve or block.")
    if pdt.get("decision") not in {"approve", "block", "reconfigure"}:
        raise ValueError("PDT decision must be approve, block or reconfigure.")
    if pdt.get("artifact_binding", {}).get("staging_binding_verified") is not True:
        raise ValueError("PDT decision must preserve the verified staging artifact binding.")
    if pdt.get("artifact_binding", {}).get("immutable_artifacts") != control.get(
        "immutable_artifacts", []
    ):
        raise ValueError("Conventional CI/CD and PDT must evaluate the same immutable artifacts.")
    if pdt.get("artifact_binding", {}).get("candidate_definition_sha256") != control.get(
        "candidate_definition_sha256"
    ):
        raise ValueError("Conventional CI/CD and PDT must use the same candidate definition.")
    if control["decision"] == "approve":
        staging = control.get("staging", {})
        if not control.get("candidate_definition_sha256"):
            raise ValueError("An approved control requires a sealed candidate definition hash.")
        if control["local_ci"].get("decision") != "pass":
            raise ValueError("An approved control requires a passing local CI result.")
        if (
            staging.get("executed") is not True
            or staging.get("decision") != "PASS"
            or staging.get("artifact_binding_verified") is not True
        ):
            raise ValueError("An approved control requires a passing, artifact-bound staging result.")

    reasons = []
    if control["decision"] != "approve":
        reasons.append("conventional-ci-cd-did-not-approve")
    if pdt["decision"] == "block":
        reasons.append("pdt-prescriptive-decision-is-block")

    if reasons:
        gate_state = "blocked"
        next_action = "do-not-deploy"
        human_confirmation_required = False
    else:
        gate_state = "awaiting-human-confirmation"
        next_action = "confirm-or-reject-isolated-validation"
        human_confirmation_required = True

    return {
        "schema_version": "2.0.0",
        "candidate_id": control["candidate_id"],
        "gate_state": gate_state,
        "next_action": next_action,
        "reasons": reasons,
        "control": {
            "mechanism": control["mechanism"],
            "decision": control["decision"],
            "reasons": control.get("reasons", []),
            "control_decision_sealed": control.get("control_decision_sealed", False),
            "local_ci": control.get("local_ci"),
            "staging": control.get("staging"),
        },
        "pdt": {
            "snapshot_id": pdt.get("snapshot_id"),
            "model_id": pdt.get("model_id"),
            "decision": pdt["decision"],
            "selected_alternative": pdt.get("selected_alternative"),
            "recommended_configuration": pdt.get("recommended_configuration"),
            "confidence": pdt.get("confidence"),
        },
        "human_confirmation": {
            "required": human_confirmation_required,
            "status": "not-requested" if reasons else "pending",
            "actor": None,
            "recorded_at": None,
        },
        "operational_mutation_performed": False,
        "rollback_plan_required_before_mutation": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conventional-decision", required=True)
    parser.add_argument("--pdt-decision", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    pdt = load(args.pdt_decision)
    control_path = Path(args.conventional_decision)
    control = load(control_path)

    try:
        output = evaluate(control, pdt)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    output["generated_at"] = now
    output["evidence"] = {
        "control_decision": str(control_path),
        "pdt_decision": str(Path(args.pdt_decision)),
    }
    Path(args.output).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
