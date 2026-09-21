#!/usr/bin/env bash

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
mode=${MODE:-engineering}
candidate_id=${CANDIDATE_ID:-}
candidate_definition=${CANDIDATE_DEFINITION:-}
candidate_base_ref=${CANDIDATE_BASE_REF:-}
candidate_head_ref=${CANDIDATE_HEAD_REF:-HEAD}
artifact_registry_prefix=${ARTIFACT_REGISTRY_PREFIX:-}
repetition=${REPETITION:-1}
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

[[ "$mode" == "engineering" || "$mode" == "confirmatory" ]] || {
  echo "MODE must be engineering or confirmatory." >&2
  exit 1
}
[[ "$candidate_id" =~ ^[a-zA-Z0-9._-]+$ ]] || {
  echo "CANDIDATE_ID is required and contains invalid characters." >&2
  exit 1
}
[[ "$repetition" =~ ^[1-9][0-9]*$ ]] || {
  echo "REPETITION must be a positive integer." >&2
  exit 1
}
[[ -f "$candidate_definition" ]] || {
  echo "CANDIDATE_DEFINITION must point to the public candidate definition." >&2
  exit 1
}
[[ "$artifact_registry_prefix" =~ ^[a-z0-9.-]+/[a-z0-9._-]+/[a-z0-9._-]+$ ]] || {
  echo "ARTIFACT_REGISTRY_PREFIX must identify the experiment registry." >&2
  exit 1
}
if ! jq -e --arg candidate "$candidate_id" --arg mode "$mode" '
  .candidate_id == $candidate
  and ([.alternatives[] | select(.id == "deploy-as-is" and .action == "deploy")] | length == 1)
  and ($mode != "confirmatory" or .confirmatory_eligibility == true)
' "$candidate_definition" >/dev/null; then
  echo "Candidate definition does not match the candidate or execution mode." >&2
  exit 1
fi
if [[ "$allow_cloud" != "true" || "$cost_review" != "true" ]]; then
  echo "End-to-end execution can publish images and start billable GKE workloads." >&2
  echo "Set ALLOW_EXPERIMENTAL_CLOUD_EXECUTION=true and COST_REVIEW_ACKNOWLEDGED=true only after the current block cost review." >&2
  exit 1
fi
if [[ "$mode" == "confirmatory" && -z "$candidate_base_ref" ]]; then
  echo "Confirmatory execution requires CANDIDATE_BASE_REF." >&2
  exit 1
fi

for namespace in staging pdt; do
  kubectl get namespace "$namespace" >/dev/null
  active_pods=$(kubectl get pods --namespace "$namespace" -o json | jq '[.items[] | select(.status.phase != "Succeeded" and .status.phase != "Failed")] | length')
  if (( active_pods > 0 )); then
    echo "Namespace $namespace contains active pods; cleanup is required before a paired run." >&2
    exit 1
  fi
done

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
pipeline_id="paired-${candidate_id}-r${repetition}-${timestamp}"
pipeline_dir="${repo_root}/experiment/evidence/pipeline/${pipeline_id}"
mkdir -p "$pipeline_dir"
cp "$candidate_definition" "${pipeline_dir}/candidate-definition.json"

write_status() {
  jq -n --arg pipeline_id "$pipeline_id" --arg state "$1" \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{pipeline_id: $pipeline_id, state: $state, updated_at: $timestamp}' \
    >"${pipeline_dir}/status.json"
}

on_error() {
  write_status failed
}

write_status running
trap on_error ERR

ci_command=(
  env
  "MODE=${mode}"
  "CANDIDATE_ID=${candidate_id}"
  "CANDIDATE_HEAD_REF=${candidate_head_ref}"
  "PUBLISH_ARTIFACTS=true"
  "ARTIFACT_REGISTRY_PREFIX=${artifact_registry_prefix}"
)
if [[ -n "$candidate_base_ref" ]]; then
  ci_command+=("CANDIDATE_BASE_REF=${candidate_base_ref}")
fi
ci_command+=("${repo_root}/experiment/scripts/run-conventional-ci-local.sh")

set +e
"${ci_command[@]}" 2>&1 | tee "${pipeline_dir}/local-ci.log"
ci_exit=${PIPESTATUS[0]}
set -e
ci_dir=$(awk -F'Evidence: ' '/^Evidence: / {path=$2} END {print path}' "${pipeline_dir}/local-ci.log")
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
  python3 "${repo_root}/experiment/scripts/compose-conventional-decision.py" \
    --local-ci-decision "$local_decision" \
    --candidate-definition "$candidate_definition" \
    --output "$conventional_decision"
  jq -n --arg pipeline_id "$pipeline_id" --arg candidate_id "$candidate_id" \
    --slurpfile control "$conventional_decision" '
    {
      schema_version: "1.0.0",
      pipeline_id: $pipeline_id,
      candidate_id: $candidate_id,
      completed_condition: "conventional-ci-cd-with-staging",
      staging_executed: false,
      pdt_executed: false,
      control_decision: $control[0].decision,
      treatment_decision: "block",
      treatment_source: "inherited-control-block",
      operational_mutation_performed: false
    }' >"${pipeline_dir}/summary.json"
  trap - ERR
  write_status completed
  printf '%s\n' "$pipeline_dir"
  exit 0
fi

staging_log="${pipeline_dir}/staging.log"
env MODE="$mode" LOCAL_CI_DECISION="$local_decision" \
  CANDIDATE_DEFINITION="$candidate_definition" CANDIDATE_ID="$candidate_id" \
  REPETITION="$repetition" \
  "${repo_root}/experiment/scripts/run-traditional-staging.sh" 2>&1 | tee "$staging_log"
staging_dir=$(tail -n 1 "$staging_log")
staging_decision="${staging_dir}/decision.json"
[[ -d "$staging_dir" && -f "$staging_decision" ]] || {
  echo "Staging did not produce a canonical decision." >&2
  exit 1
}
cp "$staging_decision" "${pipeline_dir}/staging-decision.json"

python3 "${repo_root}/experiment/scripts/compose-conventional-decision.py" \
  --local-ci-decision "$local_decision" \
  --staging-decision "$staging_decision" \
  --candidate-definition "$candidate_definition" \
  --output "$conventional_decision"

control_result=$(jq -er '.decision' "$conventional_decision")
if [[ "$control_result" == "block" ]]; then
  jq -n --arg pipeline_id "$pipeline_id" --arg candidate_id "$candidate_id" \
    --slurpfile control "$conventional_decision" '
    {
      schema_version: "1.0.0",
      pipeline_id: $pipeline_id,
      candidate_id: $candidate_id,
      completed_condition: "conventional-ci-cd-with-staging",
      staging_executed: true,
      pdt_executed: false,
      control_decision: $control[0].decision,
      treatment_decision: "block",
      treatment_source: "inherited-control-block",
      operational_mutation_performed: false
    }' >"${pipeline_dir}/summary.json"
  trap - ERR
  write_status completed
  printf '%s\n' "$pipeline_dir"
  exit 0
fi

snapshot_log="${pipeline_dir}/pdt-snapshot.log"
"${repo_root}/experiment/scripts/capture-pdt-source-state.sh" 2>&1 | tee "$snapshot_log"
snapshot_dir=$(tail -n 1 "$snapshot_log")
snapshot_file="${snapshot_dir}/pdt-input-state.json"
[[ -d "$snapshot_dir" && -f "$snapshot_file" ]] || {
  echo "PDT synchronization did not produce an immutable snapshot." >&2
  exit 1
}
cp "$snapshot_file" "${pipeline_dir}/pdt-input-state.json"

pdt_log="${pipeline_dir}/pdt.log"
env MODE="$mode" CANDIDATE_FILE="$candidate_definition" \
  CONVENTIONAL_DECISION="$conventional_decision" SNAPSHOT_FILE="$snapshot_file" \
  REPETITION="$repetition" \
  "${repo_root}/experiment/scripts/run-pdt-cycle.sh" 2>&1 | tee "$pdt_log"
pdt_dir=$(tail -n 1 "$pdt_log")
pdt_decision="${pdt_dir}/decision.json"
[[ -d "$pdt_dir" && -f "$pdt_decision" ]] || {
  echo "PDT did not produce a canonical decision." >&2
  exit 1
}
cp "$pdt_decision" "${pipeline_dir}/pdt-decision.json"

gate_file="${pipeline_dir}/gate.json"
python3 "${repo_root}/experiment/scripts/evaluate-deployment-gate.py" \
  --conventional-decision "$conventional_decision" \
  --pdt-decision "$pdt_decision" \
  --output "$gate_file"

action_plan="${pipeline_dir}/deployment-action.json"
action_plan_prepared=false
if [[ $(jq -er '.gate_state' "$gate_file") == "awaiting-human-confirmation" ]]; then
  python3 "${repo_root}/experiment/scripts/prepare-deployment-action.py" \
    --candidate-definition "$candidate_definition" \
    --snapshot "$snapshot_file" \
    --conventional-decision "$conventional_decision" \
    --pdt-decision "$pdt_decision" \
    --deployment-gate "$gate_file" \
    --output "$action_plan"
  action_plan_prepared=true
fi

jq -n --arg pipeline_id "$pipeline_id" --arg candidate_id "$candidate_id" \
  --arg snapshot "$snapshot_file" \
  --argjson action_plan_prepared "$action_plan_prepared" \
  --slurpfile control "$conventional_decision" \
  --slurpfile pdt "$pdt_decision" \
  --slurpfile gate "$gate_file" '
  {
    schema_version: "1.0.0",
    pipeline_id: $pipeline_id,
    candidate_id: $candidate_id,
    completed_condition: "same-pipeline-plus-pdt",
    staging_executed: true,
    pdt_executed: true,
    pdt_snapshot: $snapshot,
    control_decision: $control[0].decision,
    treatment_decision: $pdt[0].decision,
    deployment_gate: $gate[0].gate_state,
    human_confirmation_required: $gate[0].human_confirmation.required,
    deployment_action_prepared: $action_plan_prepared,
    deployment_action_scope: (
      if $action_plan_prepared then "isolated-oracle-validation" else null end
    ),
    operational_mutation_performed: false
  }' >"${pipeline_dir}/summary.json"

trap - ERR
write_status completed
printf '%s\n' "$pipeline_dir"
