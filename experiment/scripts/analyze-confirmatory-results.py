#!/usr/bin/env python3

"""Analyze the frozen candidate-level paired experiment without external packages."""

import argparse
import collections
import datetime
import hashlib
import json
import math
import pathlib
import re
import statistics


DIGEST = re.compile(r"^[0-9a-f]{64}$")


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def binomial_cdf(k, n, probability):
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return sum(
        math.comb(n, index)
        * probability**index
        * (1.0 - probability) ** (n - index)
        for index in range(k + 1)
    )


def binomial_survival(k, n, probability):
    return 1.0 - binomial_cdf(k - 1, n, probability)


def bisect_probability(function, target, increasing):
    low = 0.0
    high = 1.0
    for _ in range(80):
        midpoint = (low + high) / 2.0
        value = function(midpoint)
        if increasing:
            if value < target:
                low = midpoint
            else:
                high = midpoint
        elif value > target:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def exact_binomial_interval(successes, total, confidence=0.95):
    if not isinstance(successes, int) or not isinstance(total, int):
        raise ValueError("binomial counts must be integers")
    if total <= 0 or successes < 0 or successes > total:
        raise ValueError("binomial counts are outside their valid range")
    alpha = 1.0 - confidence
    lower = 0.0
    upper = 1.0
    if successes > 0:
        lower = bisect_probability(
            lambda probability: binomial_survival(successes, total, probability),
            alpha / 2.0,
            True,
        )
    if successes < total:
        upper = bisect_probability(
            lambda probability: binomial_cdf(successes, total, probability),
            alpha / 2.0,
            False,
        )
    return [lower, upper]


def exact_mcnemar_p_value(control_only_unsafe, treatment_only_unsafe):
    discordant = control_only_unsafe + treatment_only_unsafe
    if discordant == 0:
        return 1.0
    tail = sum(
        math.comb(discordant, index) for index in range(min(control_only_unsafe, treatment_only_unsafe) + 1)
    ) / (2**discordant)
    return min(1.0, 2.0 * tail)


def rate(count, total):
    if total == 0:
        return {"count": count, "total": total, "rate": None, "exact_95_percent_ci": None}
    return {
        "count": count,
        "total": total,
        "rate": count / total,
        "exact_95_percent_ci": exact_binomial_interval(count, total),
    }


def confusion_metrics(matrix):
    harmful = matrix["true_positive"] + matrix["false_negative"]
    safe = matrix["true_negative"] + matrix["false_positive"]
    sensitivity = matrix["true_positive"] / harmful if harmful else None
    specificity = matrix["true_negative"] / safe if safe else None
    balanced = (
        (sensitivity + specificity) / 2.0
        if sensitivity is not None and specificity is not None
        else None
    )
    return {
        "confusion_matrix": matrix,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "balanced_accuracy": balanced,
    }


def continuous_summary(values):
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        first = third = values[0]
    else:
        first, _, third = statistics.quantiles(values, n=4, method="inclusive")
    return {
        "count": len(values),
        "median": statistics.median(values),
        "interquartile_range": third - first,
        "q1": first,
        "q3": third,
        "minimum": values[0],
        "maximum": values[-1],
    }


def oracle_alternative_labels(oracle):
    alternatives = oracle.get("alternatives")
    if not isinstance(alternatives, list):
        raise ValueError("oracle adjudication must contain alternatives")
    result = {}
    costs = {}
    for alternative in alternatives:
        identifier = alternative.get("id")
        label = alternative.get("label")
        cost = alternative.get("change_cost")
        if (
            not identifier
            or identifier in result
            or label not in {"safe", "harmful", "inconclusive"}
            or not isinstance(cost, (int, float))
            or isinstance(cost, bool)
        ):
            raise ValueError("oracle adjudication contains an invalid alternative")
        result[identifier] = label
        costs[identifier] = cost
    if "deploy-as-is" not in result:
        raise ValueError("oracle adjudication lacks deploy-as-is")
    costs["block"] = 10
    return result, costs


def selected_action(record, condition):
    decision = record.get(condition, {}).get("decision")
    selected = record.get(condition, {}).get("selected_alternative")
    if condition == "control":
        if decision == "approve":
            if selected not in {None, "deploy-as-is"}:
                raise ValueError("conventional approval must select deploy-as-is")
            return "deploy-as-is"
        if decision == "block":
            if selected not in {None, "block"}:
                raise ValueError("conventional block must select block")
            return "block"
        raise ValueError("conventional decision must be approve or block")
    if decision == "approve" and selected == "deploy-as-is":
        return selected
    if decision == "block" and selected in {None, "block"}:
        return "block"
    if decision == "reconfigure" and selected not in {None, "block", "deploy-as-is"}:
        return selected
    raise ValueError("PDT decision and selected alternative are inconsistent")


def collect_numeric_metrics(records, condition):
    values = {}
    for record in records:
        metrics = record.get(condition, {}).get("continuous_metrics", {})
        if metrics is None:
            continue
        if not isinstance(metrics, dict):
            raise ValueError("continuous_metrics must be an object")
        for name, value in metrics.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                raise ValueError("continuous metrics must contain finite numeric values")
            values.setdefault(name, []).append(value)
    return {name: continuous_summary(items) for name, items in sorted(values.items())}


def validate_manifest_exclusion(record, protocol):
    exclusion = record.get("exclusion")
    expected_keys = {
        "reason_code",
        "reason",
        "decided_before_oracle_label",
        "label_revealed",
        "valid_repetitions",
        "invalid_repetitions",
        "replacement_attempted",
        "evidence",
    }
    repetitions = record.get("repetitions")
    required = protocol.get("research_design", {}).get(
        "technical_repetitions_per_candidate"
    )
    minimum = protocol.get("aggregation", {}).get("minimum_valid_repetitions")
    if (
        not isinstance(exclusion, dict)
        or set(exclusion) != expected_keys
        or exclusion.get("reason_code") != "insufficient-valid-repetitions"
        or not isinstance(exclusion.get("reason"), str)
        or not exclusion["reason"].strip()
        or exclusion.get("decided_before_oracle_label") is not True
        or exclusion.get("label_revealed") is not False
        or exclusion.get("replacement_attempted") is not True
        or not isinstance(required, int)
        or isinstance(required, bool)
        or required <= 0
        or not isinstance(minimum, int)
        or isinstance(minimum, bool)
        or minimum <= 0
        or minimum > required
        or repetitions != list(range(1, required + 1))
    ):
        raise ValueError("candidate exclusion is not protocol-authorized")
    valid = exclusion.get("valid_repetitions")
    invalid = exclusion.get("invalid_repetitions")
    evidence = exclusion.get("evidence")
    evidence_path_value = evidence.get("path") if isinstance(evidence, dict) else None
    evidence_path = (
        pathlib.PurePosixPath(evidence_path_value)
        if isinstance(evidence_path_value, str)
        else None
    )
    if (
        not isinstance(valid, list)
        or not isinstance(invalid, list)
        or any(not isinstance(item, int) or isinstance(item, bool) for item in valid + invalid)
        or valid != sorted(set(valid))
        or invalid != sorted(set(invalid))
        or set(valid) & set(invalid)
        or set(valid) | set(invalid) != set(repetitions)
        or len(valid) >= minimum
        or not isinstance(evidence, dict)
        or set(evidence) != {"path", "sha256"}
        or evidence_path is None
        or not evidence_path.parts
        or evidence_path.is_absolute()
        or ".." in evidence_path.parts
        or not isinstance(evidence.get("sha256"), str)
        or not DIGEST.fullmatch(evidence["sha256"])
    ):
        raise ValueError("candidate exclusion repetition accounting is invalid")
    if any(record.get(field) is not None for field in ("control", "treatment", "oracle")):
        raise ValueError("excluded candidate must not contain decision or oracle evidence")
    return exclusion


def validate_inconclusive_oracle(oracle, protocol):
    alternatives = oracle.get("alternatives")
    deploy_as_is = [
        item
        for item in alternatives or []
        if isinstance(item, dict) and item.get("id") == "deploy-as-is"
    ]
    if len(deploy_as_is) != 1 or deploy_as_is[0].get("label") != "inconclusive":
        raise ValueError("inconclusive oracle adjudication lacks deploy-as-is detail")
    aggregate = deploy_as_is[0].get("aggregate")
    required = protocol.get("research_design", {}).get(
        "technical_repetitions_per_candidate"
    )
    minimum = protocol.get("aggregation", {}).get("minimum_valid_repetitions")
    count_names = (
        "valid_repetitions",
        "harmful_repetitions",
        "safe_repetitions",
        "invalid_repetitions",
    )
    counts = {name: aggregate.get(name) for name in count_names} if isinstance(aggregate, dict) else {}
    if (
        not isinstance(required, int)
        or isinstance(required, bool)
        or required <= 0
        or not isinstance(minimum, int)
        or isinstance(minimum, bool)
        or minimum <= 0
        or minimum > required
        or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in counts.values()
        )
        or counts.get("valid_repetitions", -1) + counts.get("invalid_repetitions", -1)
        != required
        or counts.get("harmful_repetitions", -1) + counts.get("safe_repetitions", -1)
        != counts.get("valid_repetitions")
    ):
        raise ValueError("inconclusive oracle repetition accounting is invalid")
    reason = aggregate.get("reason")
    if reason == "insufficient-valid-repetitions":
        valid_reason = counts["valid_repetitions"] < minimum
    elif reason == "split-valid-repetitions":
        valid_reason = (
            counts["valid_repetitions"] == minimum
            and counts["harmful_repetitions"] > 0
            and counts["safe_repetitions"] > 0
        )
    else:
        valid_reason = False
    if not valid_reason:
        raise ValueError("inconclusive oracle adjudication lacks a valid reason")
    return aggregate


def analyze(protocol, protocol_sha256, dataset, allow_draft=False):
    confirmatory = (
        protocol.get("status") == "frozen"
        and protocol.get("confirmatory_collection_allowed") is True
        and bool(protocol.get("frozen_at"))
    )
    if not confirmatory and not allow_draft:
        raise ValueError("confirmatory analysis requires a frozen protocol")
    if dataset.get("protocol_id") != protocol.get("protocol_id"):
        raise ValueError("dataset and protocol identifiers differ")
    if dataset.get("protocol_sha256") != protocol_sha256:
        raise ValueError("dataset is not bound to the supplied protocol")
    if dataset.get("collection_complete") is not True:
        raise ValueError("analysis requires an explicitly complete collection")
    records = dataset.get("candidates")
    declared_count = protocol.get("research_design", {}).get("candidate_count")
    if not isinstance(records, list) or len(records) != declared_count:
        raise ValueError("dataset candidate count differs from the protocol")
    if not all(isinstance(record, dict) for record in records):
        raise ValueError("dataset candidate records must be objects")
    identifiers = [record.get("candidate_id") for record in records]
    if not all(isinstance(item, str) and item.startswith("cand-") for item in identifiers):
        raise ValueError("dataset contains a non-opaque candidate identifier")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("dataset contains duplicate candidates")
    manifest_exclusions = []
    for record in records:
        exclusion = record.get("exclusion")
        if exclusion is not None:
            if not isinstance(exclusion, dict):
                raise ValueError("candidate exclusion must be an object")
            manifest_exclusions.append(
                {"candidate_id": record["candidate_id"], **exclusion}
            )
    flow = dataset.get("collection_flow")
    flow_keys = {
        "declared_candidates",
        "candidate_records",
        "complete_decision_pairs",
        "manifest_exclusions",
        "silently_missing_candidates",
    }
    if (
        not isinstance(flow, dict)
        or set(flow) != flow_keys
        or flow.get("declared_candidates") != declared_count
        or flow.get("candidate_records") != declared_count
        or flow.get("complete_decision_pairs")
        != declared_count - len(manifest_exclusions)
        or flow.get("manifest_exclusions") != manifest_exclusions
        or flow.get("silently_missing_candidates") != 0
    ):
        raise ValueError("dataset collection flow is absent or inconsistent")

    eligible = []
    excluded = []
    rows = []
    for record in records:
        exclusion = record.get("exclusion")
        if exclusion is not None:
            exclusion = validate_manifest_exclusion(record, protocol)
            excluded.append(
                {
                    "candidate_id": record["candidate_id"],
                    "source": "collection-manifest",
                    **exclusion,
                }
            )
            continue
        oracle = record.get("oracle")
        if not isinstance(oracle, dict) or oracle.get("candidate_id") != record["candidate_id"]:
            raise ValueError("candidate lacks a matching oracle adjudication")
        actual = oracle.get("observed_deploy_as_is_label")
        if actual == "inconclusive":
            if oracle.get("eligible_for_primary_analysis") is not False:
                raise ValueError("inconclusive oracle adjudication must be analysis-ineligible")
            aggregate = validate_inconclusive_oracle(oracle, protocol)
            excluded.append(
                {
                    "candidate_id": record["candidate_id"],
                    "source": "oracle-adjudication",
                    "reason_code": aggregate["reason"],
                    "reason": "oracle adjudication remained inconclusive",
                    "valid_repetitions": aggregate.get("valid_repetitions"),
                    "invalid_repetitions": aggregate.get("invalid_repetitions"),
                }
            )
            continue
        if confirmatory and oracle.get("eligible_for_primary_analysis") is not True:
            raise ValueError("confirmatory candidate is not oracle-eligible for primary analysis")
        if actual not in {"safe", "harmful"}:
            raise ValueError("oracle deploy-as-is label must be safe, harmful or inconclusive")
        labels, costs = oracle_alternative_labels(oracle)
        control_action = selected_action(record, "control")
        treatment_action = selected_action(record, "treatment")
        for action in (control_action, treatment_action):
            if action != "block" and action not in labels:
                raise ValueError("selected action is absent from oracle alternatives")
        control_unsafe = control_action != "block" and labels[control_action] == "harmful"
        treatment_unsafe = treatment_action != "block" and labels[treatment_action] == "harmful"
        oracle_action = oracle.get("selected_alternative")
        if oracle_action not in costs:
            raise ValueError("oracle selected alternative has no defined cost")
        row = {
            "candidate_id": record["candidate_id"],
            "actual_deploy_as_is_label": actual,
            "control_decision": record["control"]["decision"],
            "control_action": control_action,
            "control_unsafe_approval": control_unsafe,
            "treatment_decision": record["treatment"]["decision"],
            "treatment_action": treatment_action,
            "treatment_unsafe_approval": treatment_unsafe,
            "oracle_action": oracle_action,
            "control_action_matches_oracle": control_action == oracle_action,
            "treatment_action_matches_oracle": treatment_action == oracle_action,
            "control_change_cost_difference": costs[control_action] - costs[oracle_action],
            "treatment_change_cost_difference": costs[treatment_action] - costs[oracle_action],
        }
        rows.append(row)
        eligible.append(record)

    if not rows:
        raise ValueError("no candidates remain eligible for analysis")
    harmful_rows = [row for row in rows if row["actual_deploy_as_is_label"] == "harmful"]
    safe_rows = [row for row in rows if row["actual_deploy_as_is_label"] == "safe"]
    control_unsafe = sum(row["control_unsafe_approval"] for row in harmful_rows)
    treatment_unsafe = sum(row["treatment_unsafe_approval"] for row in harmful_rows)
    control_only = sum(
        row["control_unsafe_approval"] and not row["treatment_unsafe_approval"]
        for row in harmful_rows
    )
    treatment_only = sum(
        not row["control_unsafe_approval"] and row["treatment_unsafe_approval"]
        for row in harmful_rows
    )

    matrices = {}
    for condition in ("control", "treatment"):
        matrix = {"true_positive": 0, "false_negative": 0, "true_negative": 0, "false_positive": 0}
        for row in rows:
            actual_harmful = row["actual_deploy_as_is_label"] == "harmful"
            verdict_unsafe = row[f"{condition}_decision"] != "approve"
            if actual_harmful and verdict_unsafe:
                matrix["true_positive"] += 1
            elif actual_harmful:
                matrix["false_negative"] += 1
            elif verdict_unsafe:
                matrix["false_positive"] += 1
            else:
                matrix["true_negative"] += 1
        matrices[condition] = confusion_metrics(matrix)

    control_rate = control_unsafe / len(harmful_rows) if harmful_rows else None
    treatment_rate = treatment_unsafe / len(harmful_rows) if harmful_rows else None
    primary_difference = (
        treatment_rate - control_rate
        if control_rate is not None and treatment_rate is not None
        else None
    )
    exclusion_counts = collections.Counter(
        item["reason_code"] for item in excluded
    )
    exclusion_sources = collections.Counter(item["source"] for item in excluded)
    return {
        "schema_version": "1.0.0",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha256,
        "confirmatory_eligible": confirmatory and not allow_draft,
        "analysis_mode": "confirmatory" if confirmatory and not allow_draft else "engineering-dry-run",
        "unit_of_analysis": "candidate",
        "eligibility": {
            "declared_candidates": len(records),
            "analyzed_candidates": len(rows),
            "harmful_candidates": len(harmful_rows),
            "safe_candidates": len(safe_rows),
            "excluded_candidates": excluded,
            "exclusion_counts_by_reason": dict(sorted(exclusion_counts.items())),
            "exclusion_counts_by_source": dict(sorted(exclusion_sources.items())),
            "silently_missing_candidates": 0,
            "complete_decision_pair_rate": flow["complete_decision_pairs"] / len(records),
            "primary_analysis_rate": len(rows) / len(records),
        },
        "primary_outcome": {
            "control_unsafe_approval_rate": rate(control_unsafe, len(harmful_rows)),
            "treatment_unsafe_approval_rate": rate(treatment_unsafe, len(harmful_rows)),
            "paired_risk_difference_treatment_minus_control": primary_difference,
            "absolute_risk_reduction_control_minus_treatment": (
                -primary_difference if primary_difference is not None else None
            ),
            "discordant_pairs": {
                "control_only_unsafe": control_only,
                "treatment_only_unsafe": treatment_only,
            },
            "exact_mcnemar_two_sided_p_value": exact_mcnemar_p_value(control_only, treatment_only),
        },
        "classification": matrices,
        "incremental_utility": {
            "conventional_unsafe_approvals": control_unsafe,
            "prevented_by_pdt": control_only,
            "introduced_by_pdt": treatment_only,
            "safe_candidates_blocked_by_pdt": sum(
                row["treatment_decision"] == "block" for row in safe_rows
            ),
            "safe_candidates_unnecessarily_reconfigured_by_pdt": sum(
                row["treatment_decision"] == "reconfigure" for row in safe_rows
            ),
        },
        "prescriptive_quality": {
            "control_action_matches_oracle": rate(
                sum(row["control_action_matches_oracle"] for row in rows), len(rows)
            ),
            "treatment_action_matches_oracle": rate(
                sum(row["treatment_action_matches_oracle"] for row in rows), len(rows)
            ),
            "control_change_cost_difference": continuous_summary(
                [row["control_change_cost_difference"] for row in rows]
            ),
            "treatment_change_cost_difference": continuous_summary(
                [row["treatment_change_cost_difference"] for row in rows]
            ),
        },
        "continuous_metrics": {
            "summary_method": "median, inclusive quartiles, interquartile range and range",
            "control": collect_numeric_metrics(eligible, "control"),
            "treatment": collect_numeric_metrics(eligible, "treatment"),
        },
        "candidate_results": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=pathlib.Path, required=True)
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args()
    try:
        result = analyze(
            load(args.protocol),
            sha256_file(args.protocol),
            load(args.dataset),
            allow_draft=args.allow_draft,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"confirmatory analysis failed: {error}") from error
    result["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    result["inputs"] = {
        "protocol": str(args.protocol),
        "dataset": str(args.dataset),
        "dataset_sha256": sha256_file(args.dataset),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
