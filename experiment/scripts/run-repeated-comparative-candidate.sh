#!/usr/bin/env bash

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
protocol_file=${PROTOCOL_FILE:-${repo_root}/experiment/protocol/protocol-v1.json}
candidate_id=${CANDIDATE_ID:-}
candidate_definition=${CANDIDATE_DEFINITION:-}
candidate_base_ref=${CANDIDATE_BASE_REF:-}
candidate_head_ref=${CANDIDATE_HEAD_REF:-HEAD}
artifact_registry_prefix=${ARTIFACT_REGISTRY_PREFIX:-}
controller_image=${PDT_CONTROLLER_IMAGE:-}
allow_cloud=${ALLOW_EXPERIMENTAL_CLOUD_EXECUTION:-false}
cost_review=${COST_REVIEW_ACKNOWLEDGED:-false}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

for command_name in git jq kubectl python3 sha256sum tee; do
  require_command "$command_name"
done

[[ "$candidate_id" =~ ^[a-zA-Z0-9._-]+$ ]] || {
  echo "CANDIDATE_ID is required and contains invalid characters." >&2
  exit 1
}
[[ -f "$candidate_definition" ]] || {
  echo "CANDIDATE_DEFINITION must point to the public candidate definition." >&2
  exit 1
}
[[ -n "$candidate_base_ref" ]] || {
  echo "Confirmatory execution requires CANDIDATE_BASE_REF." >&2
  exit 1
}
[[ "$artifact_registry_prefix" =~ ^[a-z0-9.-]+/[a-z0-9._-]+/[a-z0-9._-]+$ ]] || {
  echo "ARTIFACT_REGISTRY_PREFIX must identify the experiment registry." >&2
  exit 1
}
if [[ "$allow_cloud" != "true" || "$cost_review" != "true" ]]; then
  echo "Repeated confirmatory execution starts billable GKE workloads." >&2
  echo "Set both cloud and cost gates only after the current block review." >&2
  exit 1
fi

jq -e '
  .status == "frozen"
  and .confirmatory_collection_allowed == true
  and (.frozen_at | type == "string" and length > 0)
  and .research_design.execution == "sequential"
  and .research_design.technical_repetitions_per_candidate == 3
  and .aggregation.mechanism_repetition_rule.planned_repetitions == 3
  and .aggregation.mechanism_repetition_rule.minimum_valid_repetitions == 2
  and .aggregation.mechanism_repetition_rule.safe_votes_to_approve == 2
' "$protocol_file" >/dev/null || {
  echo "Confirmatory repetition orchestration requires the frozen three-repetition protocol." >&2
  exit 1
}
jq -e --arg candidate "$candidate_id" '
  .candidate_id == $candidate
  and .confirmatory_eligibility == true
  and ([.alternatives[] | select(.id == "deploy-as-is" and .action == "deploy")] | length == 1)
' "$candidate_definition" >/dev/null || {
  echo "Candidate is not eligible for confirmatory repetition orchestration." >&2
  exit 1
}
[[ "$controller_image" =~ ^us-central1-docker\.pkg\.dev/microservices-demo-tcc/online-boutique-experiment/checkout-pdt-controller@sha256:[a-f0-9]{64}$ ]] || {
  echo "PDT_CONTROLLER_IMAGE must be the frozen immutable controller image." >&2
  exit 1
}

for namespace in staging pdt pdt-system; do
  kubectl get namespace "$namespace" >/dev/null
  active_pods=$(kubectl get pods --namespace "$namespace" -o json | jq '[.items[] | select(.status.phase != "Succeeded" and .status.phase != "Failed")] | length')
  if (( active_pods > 0 )); then
    echo "Namespace $namespace contains active pods; cleanup is required." >&2
    exit 1
  fi
done

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
pipeline_id="paired-${candidate_id}-confirmatory-${timestamp}"
pipeline_dir="${repo_root}/experiment/evidence/pipeline/${pipeline_id}"
mkdir -p "$pipeline_dir"
cp "$candidate_definition" "${pipeline_dir}/candidate-definition.json"

write_status() {
  jq -n --arg pipeline_id "$pipeline_id" --arg state "$1" \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{pipeline_id: $pipeline_id, state: $state, updated_at: $timestamp}' \
    >"${pipeline_dir}/status.json"
}

cleanup_after_attempt() {
  local label=$1
  ALLOW_EXPERIMENTAL_CLEANUP=true \
    OUTPUT_FILE="${pipeline_dir}/cleanup-${label}.json" \
    "${repo_root}/experiment/scripts/cleanup-experimental-workloads.sh" >/dev/null
}

json_number_array() {
  if (( $# == 0 )); then
    printf '[]\n'
  else
    printf '%s\n' "$@" | jq -R 'tonumber' | jq -s '.'
  fi
}

on_error() {
  local exit_code=$?
  trap - ERR
  cleanup_after_attempt error-final || true
  write_status failed || true
  exit "$exit_code"
}

write_status running
trap on_error ERR

ci_log="${pipeline_dir}/local-ci.log"
ci_command=(
  env
  MODE=confirmatory
  "CANDIDATE_ID=${candidate_id}"
  "CANDIDATE_BASE_REF=${candidate_base_ref}"
  "CANDIDATE_HEAD_REF=${candidate_head_ref}"
  PUBLISH_ARTIFACTS=true
  "ARTIFACT_REGISTRY_PREFIX=${artifact_registry_prefix}"
  "${repo_root}/experiment/scripts/run-conventional-ci-local.sh"
)
set +e
"${ci_command[@]}" 2>&1 | tee "$ci_log"
ci_exit=${PIPESTATUS[0]}
set -e
ci_dir=$(awk -F'Evidence: ' '/^Evidence: / {path=$2} END {print path}' "$ci_log")
local_decision="${ci_dir}/ci-local-decision.json"
[[ -n "$ci_dir" && -f "$local_decision" ]] || {
  echo "Local CI did not produce a canonical decision." >&2
  exit 1
}
cp "$local_decision" "${pipeline_dir}/local-ci-decision.json"
local_result=$(jq -er '.local_decision' "$local_decision")
if [[ "$local_result" == "pass" && "$ci_exit" -ne 0 ]]; then
  echo "Local CI exit status contradicts its decision." >&2
  exit 1
fi

conventional_decision="${pipeline_dir}/conventional-decision.json"
if [[ "$local_result" == "block" ]]; then
  python3 "${repo_root}/experiment/scripts/aggregate-conventional-repetitions.py" \
    --protocol "$protocol_file" \
    --local-ci-decision "$local_decision" \
    --candidate-definition "$candidate_definition" \
    --output "$conventional_decision"
  jq -n --arg pipeline_id "$pipeline_id" --arg candidate_id "$candidate_id" \
    --slurpfile control "$conventional_decision" '
    {
      schema_version: "1.0.0",
      pipeline_id: $pipeline_id,
      candidate_id: $candidate_id,
      execution_mode: "confirmatory",
      completed_condition: "conventional-ci-cd-with-staging",
      staging_executed: false,
      pdt_executed: false,
      control_decision: $control[0].decision,
      treatment_decision: "block",
      treatment_source: "inherited-control-block",
      human_confirmation_required: false,
      operational_mutation_performed: false
    }' >"${pipeline_dir}/summary.json"
  trap - ERR
  write_status completed
  printf '%s\n' "$pipeline_dir"
  exit 0
fi

valid_staging_repetitions=()
staging_decisions=()
invalid_staging_repetitions=()
declare -A staging_failure_one staging_failure_two

for repetition in 1 2 3; do
  for attempt in 1 2; do
    log="${pipeline_dir}/staging-r${repetition}-attempt${attempt}.log"
    set +e
    env MODE=confirmatory LOCAL_CI_DECISION="$local_decision" \
      CANDIDATE_DEFINITION="$candidate_definition" CANDIDATE_ID="$candidate_id" \
      REPETITION="$repetition" \
      "${repo_root}/experiment/scripts/run-traditional-staging.sh" \
      2>&1 | tee "$log"
    attempt_exit=${PIPESTATUS[0]}
    set -e
    cleanup_after_attempt "staging-r${repetition}-attempt${attempt}"
    staging_dir=$(tail -n 1 "$log")
    staging_decision="${staging_dir}/decision.json"
    if [[ "$attempt_exit" -eq 0 && -f "$staging_decision" ]] \
      && [[ $(jq -er '.repetition' "$staging_decision") == "$repetition" ]]; then
      valid_staging_repetitions+=("$repetition")
      staging_decisions+=("$staging_decision")
      break
    fi
    reason="exit-${attempt_exit}:$(tail -n 1 "$log" | tr '\n\r' '  ' | cut -c1-300)"
    if [[ "$attempt" -eq 1 ]]; then
      staging_failure_one[$repetition]=$reason
    else
      staging_failure_two[$repetition]=$reason
      invalid_staging_repetitions+=("$repetition")
    fi
  done
done

staging_ledger=""
if (( ${#invalid_staging_repetitions[@]} > 0 )); then
  staging_ledger="${pipeline_dir}/staging-infrastructure-invalid-ledger.json"
  entries='[]'
  for repetition in "${invalid_staging_repetitions[@]}"; do
    entries=$(jq -c \
      --argjson repetition "$repetition" \
      --arg first "${staging_failure_one[$repetition]}" \
      --arg second "${staging_failure_two[$repetition]}" \
      '. + [{repetition:$repetition,attempts:2,reasons:[$first,$second]}]' \
      <<<"$entries")
  done
  valid_json=$(json_number_array "${valid_staging_repetitions[@]}")
  jq -n --arg candidate_id "$candidate_id" --argjson valid "$valid_json" \
    --argjson invalid "$entries" '
    {
      schema_version: "1.0.0",
      candidate_id: $candidate_id,
      classification: "infrastructure-invalid",
      label_revealed: false,
      planned_repetitions: [1,2,3],
      valid_repetitions: $valid,
      invalid_repetitions: $invalid
    }' >"$staging_ledger"
fi

if (( ${#valid_staging_repetitions[@]} < 2 )); then
  jq -n --arg pipeline_id "$pipeline_id" --arg candidate_id "$candidate_id" \
    --arg ledger "$staging_ledger" '
    {
      schema_version: "1.0.0",
      pipeline_id: $pipeline_id,
      candidate_id: $candidate_id,
      execution_mode: "confirmatory",
      outcome: "excluded-before-oracle-label",
      reason: "insufficient-valid-staging-repetitions-after-retry",
      infrastructure_invalid_ledger: $ledger,
      oracle_label_revealed: false,
      human_confirmation_required: false,
      operational_mutation_performed: false
    }' >"${pipeline_dir}/summary.json"
  trap - ERR
  write_status completed-excluded
  printf '%s\n' "$pipeline_dir"
  exit 0
fi

control_args=(
  python3 "${repo_root}/experiment/scripts/aggregate-conventional-repetitions.py"
  --protocol "$protocol_file"
  --local-ci-decision "$local_decision"
  --candidate-definition "$candidate_definition"
  --output "$conventional_decision"
)
for decision_file in "${staging_decisions[@]}"; do
  control_args+=(--staging-decision "$decision_file")
done
if [[ -n "$staging_ledger" ]]; then
  control_args+=(--infrastructure-invalid-ledger "$staging_ledger")
fi
"${control_args[@]}"

control_result=$(jq -er '.decision' "$conventional_decision")
if [[ "$control_result" == "block" ]]; then
  jq -n --arg pipeline_id "$pipeline_id" --arg candidate_id "$candidate_id" \
    --slurpfile control "$conventional_decision" '
    {
      schema_version: "1.0.0",
      pipeline_id: $pipeline_id,
      candidate_id: $candidate_id,
      execution_mode: "confirmatory",
      completed_condition: "conventional-ci-cd-with-staging",
      staging_executed: true,
      pdt_executed: false,
      control_decision: $control[0].decision,
      treatment_decision: "block",
      treatment_source: "inherited-control-block",
      human_confirmation_required: false,
      operational_mutation_performed: false
    }' >"${pipeline_dir}/summary.json"
  trap - ERR
  write_status completed
  printf '%s\n' "$pipeline_dir"
  exit 0
fi

pdt_decisions=()
snapshot_files=()
pdt_infrastructure_invalid=false
valid_pdt_repetitions=()
invalid_pdt_repetitions=()
declare -A pdt_failure_one pdt_failure_two
for repetition in "${valid_staging_repetitions[@]}"; do
  repetition_succeeded=false
  for attempt in 1 2; do
    snapshot_log="${pipeline_dir}/pdt-snapshot-r${repetition}-attempt${attempt}.log"
    pdt_log="${pipeline_dir}/pdt-r${repetition}-attempt${attempt}.log"
    set +e
    "${repo_root}/experiment/scripts/capture-pdt-source-state.sh" \
      2>&1 | tee "$snapshot_log"
    snapshot_exit=${PIPESTATUS[0]}
    snapshot_dir=$(tail -n 1 "$snapshot_log")
    snapshot_file="${snapshot_dir}/pdt-input-state.json"
    if [[ "$snapshot_exit" -eq 0 && -f "$snapshot_file" ]]; then
      env MODE=confirmatory CANDIDATE_FILE="$candidate_definition" \
        CONVENTIONAL_DECISION="$conventional_decision" SNAPSHOT_FILE="$snapshot_file" \
        REPETITION="$repetition" PDT_CONTROLLER_IMAGE="$controller_image" \
        "${repo_root}/experiment/scripts/run-pdt-cycle.sh" \
        2>&1 | tee "$pdt_log"
      pdt_exit=${PIPESTATUS[0]}
    else
      pdt_exit=$snapshot_exit
    fi
    set -e
    cleanup_after_attempt "pdt-r${repetition}-attempt${attempt}"
    pdt_dir=$(tail -n 1 "$pdt_log" 2>/dev/null || true)
    pdt_decision="${pdt_dir}/decision.json"
    if [[ "$pdt_exit" -eq 0 && -f "$pdt_decision" ]] \
      && [[ $(jq -er '.repetition' "$pdt_decision") == "$repetition" ]]; then
      pdt_decisions+=("$pdt_decision")
      snapshot_files+=("$snapshot_file")
      valid_pdt_repetitions+=("$repetition")
      repetition_succeeded=true
      break
    fi
    if [[ -f "$pdt_log" ]]; then
      reason="exit-${pdt_exit}:$(tail -n 1 "$pdt_log" | tr '\n\r' '  ' | cut -c1-300)"
    else
      reason="exit-${pdt_exit}:$(tail -n 1 "$snapshot_log" | tr '\n\r' '  ' | cut -c1-300)"
    fi
    if [[ "$attempt" -eq 1 ]]; then
      pdt_failure_one[$repetition]=$reason
    else
      pdt_failure_two[$repetition]=$reason
    fi
  done
  if [[ "$repetition_succeeded" != "true" ]]; then
    pdt_infrastructure_invalid=true
    invalid_pdt_repetitions+=("$repetition")
  fi
done

if [[ "$pdt_infrastructure_invalid" == "true" ]]; then
  pdt_ledger="${pipeline_dir}/paired-infrastructure-invalid-ledger.json"
  paired_entries='[]'
  for repetition in "${invalid_staging_repetitions[@]}"; do
    paired_entries=$(jq -c \
      --argjson repetition "$repetition" \
      --arg first "${staging_failure_one[$repetition]}" \
      --arg second "${staging_failure_two[$repetition]}" \
      '. + [{repetition:$repetition,attempts:2,reasons:[$first,$second]}]' \
      <<<"$paired_entries")
  done
  for repetition in "${invalid_pdt_repetitions[@]}"; do
    paired_entries=$(jq -c \
      --argjson repetition "$repetition" \
      --arg first "${pdt_failure_one[$repetition]}" \
      --arg second "${pdt_failure_two[$repetition]}" \
      '. + [{repetition:$repetition,attempts:2,reasons:[$first,$second]}]' \
      <<<"$paired_entries")
  done
  paired_entries=$(jq -c 'sort_by(.repetition)' <<<"$paired_entries")
  valid_pdt_json=$(json_number_array "${valid_pdt_repetitions[@]}")
  jq -n --arg candidate_id "$candidate_id" --argjson valid "$valid_pdt_json" \
    --argjson invalid "$paired_entries" '
    {
      schema_version: "1.0.0",
      candidate_id: $candidate_id,
      classification: "infrastructure-invalid",
      label_revealed: false,
      planned_repetitions: [1,2,3],
      valid_repetitions: $valid,
      invalid_repetitions: $invalid
    }' >"$pdt_ledger"
  jq -n --arg pipeline_id "$pipeline_id" --arg candidate_id "$candidate_id" \
    --arg ledger "$pdt_ledger" '
    {
      schema_version: "1.0.0",
      pipeline_id: $pipeline_id,
      candidate_id: $candidate_id,
      execution_mode: "confirmatory",
      outcome: "excluded-before-oracle-label",
      reason: "paired-PDT-repetition-remained-infrastructure-invalid-after-retry",
      infrastructure_invalid_ledger: $ledger,
      control_decision_sealed: true,
      oracle_label_revealed: false,
      human_confirmation_required: false,
      operational_mutation_performed: false
    }' >"${pipeline_dir}/summary.json"
  trap - ERR
  write_status completed-excluded
  printf '%s\n' "$pipeline_dir"
  exit 0
fi

pdt_decision="${pipeline_dir}/pdt-decision.json"
pdt_args=(
  python3 "${repo_root}/experiment/scripts/aggregate-pdt-repetitions.py"
  --protocol "$protocol_file"
  --candidate-definition "$candidate_definition"
  --conventional-decision "$conventional_decision"
  --output "$pdt_decision"
)
for decision_file in "${pdt_decisions[@]}"; do
  pdt_args+=(--pdt-decision "$decision_file")
done
if [[ -n "$staging_ledger" ]]; then
  pdt_args+=(--infrastructure-invalid-ledger "$staging_ledger")
fi
"${pdt_args[@]}"

gate_file="${pipeline_dir}/gate.json"
python3 "${repo_root}/experiment/scripts/evaluate-deployment-gate.py" \
  --conventional-decision "$conventional_decision" \
  --pdt-decision "$pdt_decision" \
  --output "$gate_file"

action_plan="${pipeline_dir}/deployment-action.json"
action_plan_prepared=false
if [[ $(jq -er '.gate_state' "$gate_file") == "awaiting-human-confirmation" ]]; then
  latest_snapshot_index=$((${#snapshot_files[@]} - 1))
  latest_snapshot=${snapshot_files[$latest_snapshot_index]}
  [[ $(jq -er '.snapshot_id' "$latest_snapshot") == $(jq -er '.snapshot_id' "$pdt_decision") ]]
  python3 "${repo_root}/experiment/scripts/prepare-deployment-action.py" \
    --candidate-definition "$candidate_definition" \
    --snapshot "$latest_snapshot" \
    --conventional-decision "$conventional_decision" \
    --pdt-decision "$pdt_decision" \
    --deployment-gate "$gate_file" \
    --output "$action_plan"
  action_plan_prepared=true
fi

jq -n --arg pipeline_id "$pipeline_id" --arg candidate_id "$candidate_id" \
  --argjson action_plan_prepared "$action_plan_prepared" \
  --slurpfile control "$conventional_decision" \
  --slurpfile pdt "$pdt_decision" \
  --slurpfile gate "$gate_file" '
  {
    schema_version: "1.0.0",
    pipeline_id: $pipeline_id,
    candidate_id: $candidate_id,
    execution_mode: "confirmatory",
    completed_condition: "same-pipeline-plus-pdt",
    repetitions: [1,2,3],
    staging_executed: true,
    pdt_executed: true,
    control_decision: $control[0].decision,
    treatment_decision: $pdt[0].decision,
    deployment_gate: $gate[0].gate_state,
    human_confirmation_required: $gate[0].human_confirmation.required,
    deployment_action_prepared: $action_plan_prepared,
    deployment_action_scope: (
      if $action_plan_prepared then "isolated-oracle-validation" else null end
    ),
    oracle_label_revealed: false,
    operational_mutation_performed: false
  }' >"${pipeline_dir}/summary.json"

trap - ERR
cleanup_after_attempt success-final
write_status completed
printf '%s\n' "$pipeline_dir"
