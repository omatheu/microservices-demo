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
FIDELITY_METRICS = {
    "checkout_success_rate": "ratio",
    "checkout_latency_p95_ms": "milliseconds",
    "checkout_latency_p99_ms": "milliseconds",
    "checkoutservice_unavailable": "deployments",
    "checkoutservice_restart_increase": "restarts",
}


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


def finite_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def validate_fidelity_summary(summary, label, allow_empty=False, nonnegative=False):
    if summary is None and allow_empty:
        return
    required = {
        "count",
        "mean",
        "median",
        "sample_standard_deviation",
        "minimum",
        "maximum",
    }
    if not isinstance(summary, dict) or set(summary) != required:
        raise ValueError(f"{label} summary schema is invalid")
    count = summary["count"]
    values = [summary[name] for name in ("mean", "median", "minimum", "maximum")]
    deviation = summary["sample_standard_deviation"]
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or count <= 0
        or any(not finite_number(value) for value in values)
        or (count == 1 and deviation is not None)
        or (count > 1 and (not finite_number(deviation) or deviation < 0))
        or summary["minimum"] > summary["median"]
        or summary["median"] > summary["maximum"]
        or summary["minimum"] > summary["mean"]
        or summary["mean"] > summary["maximum"]
        or (nonnegative and summary["minimum"] < 0)
    ):
        raise ValueError(f"{label} summary values are invalid")


def validate_candidate_fidelity(
    fidelity,
    protocol,
    protocol_sha256,
    candidate_id,
    repetitions,
    confirmatory,
):
    required_repetitions = protocol.get("research_design", {}).get(
        "technical_repetitions_per_candidate"
    )
    planned_repetitions = (
        list(range(1, required_repetitions + 1))
        if isinstance(required_repetitions, int)
        and not isinstance(required_repetitions, bool)
        and required_repetitions > 0
        else None
    )
    coverage = fidelity.get("coverage") if isinstance(fidelity, dict) else None
    classification = fidelity.get("classification") if isinstance(fidelity, dict) else None
    controls = fidelity.get("controls") if isinstance(fidelity, dict) else None
    candidate_definition_sha256 = (
        fidelity.get("candidate_definition_sha256")
        if isinstance(fidelity, dict)
        else None
    )
    if (
        repetitions != planned_repetitions
        or not isinstance(fidelity, dict)
        or fidelity.get("schema_version") != "1.0.0"
        or fidelity.get("mechanism") != "candidate-level-pdt-fidelity"
        or fidelity.get("protocol_id") != protocol.get("protocol_id")
        or fidelity.get("protocol_sha256") != protocol_sha256
        or fidelity.get("policy_id") != "checkout-pdt-fidelity-v1"
        or not isinstance(fidelity.get("policy_sha256"), str)
        or not DIGEST.fullmatch(fidelity["policy_sha256"])
        or fidelity.get("candidate_id") != candidate_id
        or not isinstance(candidate_definition_sha256, str)
        or not DIGEST.fullmatch(candidate_definition_sha256)
        or not isinstance(fidelity.get("immutable_artifacts"), list)
        or fidelity.get("unit_of_analysis") != "candidate"
        or fidelity.get("execution_mode")
        != ("confirmatory" if confirmatory else "engineering")
        or fidelity.get("confirmatory_eligible") is not confirmatory
    ):
        raise ValueError(f"{candidate_id} fidelity aggregate is not protocol-bound")
    if (
        not isinstance(coverage, dict)
        or coverage.get("complete") is not True
        or coverage.get("repetitions") != planned_repetitions
        or not isinstance(coverage.get("deployable_alternatives"), list)
        or not coverage["deployable_alternatives"]
        or len(coverage["deployable_alternatives"])
        != len(set(coverage["deployable_alternatives"]))
        or "deploy-as-is" not in coverage["deployable_alternatives"]
        or not isinstance(coverage.get("expected_reports"), int)
        or isinstance(coverage.get("expected_reports"), bool)
        or coverage["expected_reports"] <= 0
        or not isinstance(coverage.get("observed_reports"), int)
        or isinstance(coverage.get("observed_reports"), bool)
        or coverage["observed_reports"] != coverage["expected_reports"]
        or coverage["expected_reports"]
        != len(coverage["deployable_alternatives"]) * len(planned_repetitions)
    ):
        raise ValueError(f"{candidate_id} fidelity coverage is incomplete")

    agreements = classification.get("agreements") if isinstance(classification, dict) else None
    comparisons = classification.get("comparisons") if isinstance(classification, dict) else None
    agreement_rate = classification.get("agreement_rate") if isinstance(classification, dict) else None
    by_alternative = classification.get("by_alternative") if isinstance(classification, dict) else None
    if (
        not isinstance(agreements, int)
        or isinstance(agreements, bool)
        or not isinstance(comparisons, int)
        or isinstance(comparisons, bool)
        or comparisons != coverage["expected_reports"]
        or agreements < 0
        or agreements > comparisons
        or not finite_number(agreement_rate)
        or not math.isclose(
            agreement_rate, agreements / comparisons, rel_tol=1e-12, abs_tol=1e-12
        )
        or not isinstance(by_alternative, dict)
        or set(by_alternative) != set(coverage["deployable_alternatives"])
    ):
        raise ValueError(f"{candidate_id} fidelity classification is inconsistent")
    for alternative_id, item in by_alternative.items():
        expected_comparisons = len(planned_repetitions)
        if (
            not isinstance(item, dict)
            or set(item) != {"agreements", "comparisons", "agreement_rate"}
            or not isinstance(item["agreements"], int)
            or isinstance(item["agreements"], bool)
            or not isinstance(item["comparisons"], int)
            or isinstance(item["comparisons"], bool)
            or item["comparisons"] != expected_comparisons
            or item["agreements"] < 0
            or item["agreements"] > expected_comparisons
            or not finite_number(item["agreement_rate"])
            or not math.isclose(
                item["agreement_rate"],
                item["agreements"] / expected_comparisons,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        ):
            raise ValueError(
                f"{candidate_id} fidelity classification for {alternative_id} is inconsistent"
            )

    metric_results = fidelity.get("metrics")
    if not isinstance(metric_results, dict) or set(metric_results) != set(FIDELITY_METRICS):
        raise ValueError(f"{candidate_id} fidelity metric set is invalid")
    for metric_id, unit in FIDELITY_METRICS.items():
        metric = metric_results[metric_id]
        if (
            not isinstance(metric, dict)
            or set(metric)
            != {
                "unit",
                "report_count",
                "signed_error",
                "absolute_error",
                "relative_error",
                "undefined_relative_error_count",
            }
            or metric.get("unit") != unit
            or not isinstance(metric.get("report_count"), int)
            or isinstance(metric.get("report_count"), bool)
            or metric["report_count"] != coverage["expected_reports"]
            or not isinstance(metric.get("undefined_relative_error_count"), int)
            or isinstance(metric.get("undefined_relative_error_count"), bool)
            or not 0 <= metric["undefined_relative_error_count"] <= metric["report_count"]
        ):
            raise ValueError(f"{candidate_id} fidelity metric {metric_id} is invalid")
        validate_fidelity_summary(metric["signed_error"], f"{candidate_id} {metric_id} signed")
        validate_fidelity_summary(
            metric["absolute_error"],
            f"{candidate_id} {metric_id} absolute",
            nonnegative=True,
        )
        validate_fidelity_summary(
            metric["relative_error"],
            f"{candidate_id} {metric_id} relative",
            allow_empty=metric["undefined_relative_error_count"] == metric["report_count"],
            nonnegative=True,
        )
        relative_count = (
            metric["relative_error"]["count"] if metric["relative_error"] is not None else 0
        )
        if relative_count + metric["undefined_relative_error_count"] != metric["report_count"]:
            raise ValueError(f"{candidate_id} fidelity relative-error accounting differs")

    report_index = fidelity.get("report_index")
    expected_identities = {
        (alternative_id, repetition)
        for alternative_id in coverage["deployable_alternatives"]
        for repetition in planned_repetitions
    }
    if not isinstance(report_index, list) or len(report_index) != len(expected_identities):
        raise ValueError(f"{candidate_id} fidelity report index is incomplete")
    indexed_identities = []
    indexed_agreements = 0
    indexed_by_alternative = {
        alternative_id: 0 for alternative_id in coverage["deployable_alternatives"]
    }
    for item in report_index:
        if (
            not isinstance(item, dict)
            or set(item)
            != {"alternative_id", "repetition", "classification_agreement"}
            or not isinstance(item.get("classification_agreement"), bool)
        ):
            raise ValueError(f"{candidate_id} fidelity report index is invalid")
        identity = (item.get("alternative_id"), item.get("repetition"))
        indexed_identities.append(identity)
        indexed_agreements += item["classification_agreement"]
        if item.get("alternative_id") in indexed_by_alternative:
            indexed_by_alternative[item["alternative_id"]] += item[
                "classification_agreement"
            ]
    if (
        len(indexed_identities) != len(set(indexed_identities))
        or set(indexed_identities) != expected_identities
        or indexed_agreements != agreements
        or any(
            indexed_by_alternative[alternative_id]
            != by_alternative[alternative_id]["agreements"]
            for alternative_id in indexed_by_alternative
        )
    ):
        raise ValueError(f"{candidate_id} fidelity report index is inconsistent")
    if (
        not isinstance(controls, dict)
        or controls.get("complete_matrix_required") is not True
        or controls.get("model_mutation_performed") is not False
        or controls.get("recalibration_allowed") is not False
        or controls.get("confirmatory_reports_are_evaluation_only") is not True
    ):
        raise ValueError(f"{candidate_id} fidelity controls are invalid")
    return fidelity


def summarize_prediction_fidelity(fidelity_records, not_applicable_control_blocked):
    metric_results = {}
    for metric_id, unit in FIDELITY_METRICS.items():
        signed = [item["metrics"][metric_id]["signed_error"]["median"] for item in fidelity_records]
        absolute = [
            item["metrics"][metric_id]["absolute_error"]["median"]
            for item in fidelity_records
        ]
        relative = [
            item["metrics"][metric_id]["relative_error"]["median"]
            for item in fidelity_records
            if item["metrics"][metric_id]["relative_error"] is not None
        ]
        metric_results[metric_id] = {
            "unit": unit,
            "candidate_median_signed_error": continuous_summary(signed),
            "candidate_median_absolute_error": continuous_summary(absolute),
            "candidate_median_relative_error": continuous_summary(relative),
            "candidates_with_undefined_relative_error": sum(
                item["metrics"][metric_id]["relative_error"] is None
                for item in fidelity_records
            ),
        }
    agreement_rates = [
        item["classification"]["agreement_rate"] for item in fidelity_records
    ]
    return {
        "unit_of_analysis": "candidate",
        "repetitions_used_only_within_candidate_aggregates": True,
        "candidates_with_pdt_prediction": len(fidelity_records),
        "not_applicable_control_blocked_candidates": not_applicable_control_blocked,
        "classification_agreement": {
            "candidate_rate_summary": continuous_summary(agreement_rates),
            "perfect_candidate_agreement": rate(
                sum(value == 1.0 for value in agreement_rates), len(agreement_rates)
            ),
        },
        "metrics": metric_results,
        "controls": {
            "candidate_level_aggregation_only": True,
            "confirmatory_recalibration_allowed": False,
            "model_mutation_performed": False,
        },
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
    expected_dataset_eligibility = confirmatory and not allow_draft
    expected_composition_mode = (
        "confirmatory" if expected_dataset_eligibility else "engineering-dry-run"
    )
    if (
        dataset.get("confirmatory_eligible") is not expected_dataset_eligibility
        or dataset.get("composition_mode") != expected_composition_mode
    ):
        raise ValueError("dataset composition mode is inconsistent with the analysis mode")
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
    required_repetitions = protocol.get("research_design", {}).get(
        "technical_repetitions_per_candidate"
    )
    planned_repetitions = (
        list(range(1, required_repetitions + 1))
        if isinstance(required_repetitions, int)
        and not isinstance(required_repetitions, bool)
        and required_repetitions > 0
        else None
    )
    manifest_exclusions = []
    validated_fidelity = {}
    fidelity_candidates = 0
    fidelity_not_applicable = 0
    for record in records:
        exclusion = record.get("exclusion")
        if exclusion is not None:
            if not isinstance(exclusion, dict):
                raise ValueError("candidate exclusion must be an object")
            manifest_exclusions.append(
                {"candidate_id": record["candidate_id"], **exclusion}
            )
            continue
        control = record.get("control")
        treatment = record.get("treatment")
        if (
            planned_repetitions is None
            or record.get("repetitions") != planned_repetitions
            or not isinstance(control, dict)
            or not isinstance(treatment, dict)
            or "fidelity" not in treatment
        ):
            raise ValueError("candidate decision pair or repetition plan is incomplete")
        if control.get("decision") == "approve":
            validated_fidelity[record["candidate_id"]] = validate_candidate_fidelity(
                treatment.get("fidelity"),
                protocol,
                protocol_sha256,
                record["candidate_id"],
                record["repetitions"],
                confirmatory,
            )
            fidelity_candidates += 1
        elif control.get("decision") == "block":
            if treatment.get("fidelity") is not None:
                raise ValueError("control-blocked candidate must not contain PDT fidelity")
            fidelity_not_applicable += 1
        else:
            raise ValueError("conventional decision must be approve or block")
    flow = dataset.get("collection_flow")
    flow_keys = {
        "declared_candidates",
        "candidate_records",
        "complete_decision_pairs",
        "pdt_fidelity_candidates",
        "pdt_fidelity_not_applicable_control_blocked",
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
        or flow.get("pdt_fidelity_candidates") != fidelity_candidates
        or flow.get("pdt_fidelity_not_applicable_control_blocked")
        != fidelity_not_applicable
        or fidelity_candidates + fidelity_not_applicable
        != flow.get("complete_decision_pairs")
        or flow.get("manifest_exclusions") != manifest_exclusions
        or flow.get("silently_missing_candidates") != 0
    ):
        raise ValueError("dataset collection flow is absent or inconsistent")

    eligible = []
    eligible_fidelity = []
    eligible_fidelity_not_applicable = 0
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
        candidate_fidelity = validated_fidelity.get(record["candidate_id"])
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
            "pdt_fidelity": (
                {
                    "classification_agreement_rate": candidate_fidelity[
                        "classification"
                    ]["agreement_rate"],
                    "metric_medians": {
                        metric_id: {
                            "unit": unit,
                            "signed_error": candidate_fidelity["metrics"][metric_id][
                                "signed_error"
                            ]["median"],
                            "absolute_error": candidate_fidelity["metrics"][metric_id][
                                "absolute_error"
                            ]["median"],
                            "relative_error": (
                                candidate_fidelity["metrics"][metric_id][
                                    "relative_error"
                                ]["median"]
                                if candidate_fidelity["metrics"][metric_id][
                                    "relative_error"
                                ]
                                is not None
                                else None
                            ),
                        }
                        for metric_id, unit in FIDELITY_METRICS.items()
                    },
                }
                if candidate_fidelity is not None
                else None
            ),
        }
        rows.append(row)
        eligible.append(record)
        if candidate_fidelity is not None:
            eligible_fidelity.append(candidate_fidelity)
        else:
            eligible_fidelity_not_applicable += 1

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
        "prediction_fidelity": summarize_prediction_fidelity(
            eligible_fidelity, eligible_fidelity_not_applicable
        ),
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
