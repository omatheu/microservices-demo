#!/usr/bin/env bash

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
mode=${MODE:-engineering}
candidate_id=${CANDIDATE_ID:-}
candidate_definition=${CANDIDATE_DEFINITION:-}
conventional_decision=${CONVENTIONAL_DECISION:-}
pdt_decision=${PDT_DECISION:-}
pdt_prediction_decision=${PDT_PREDICTION_DECISION:-}
pdt_invalid_repetition_ledger=${PDT_INVALID_REPETITION_LEDGER:-}
deployment_gate=${DEPLOYMENT_GATE:-}
deployment_action=${DEPLOYMENT_ACTION:-}
human_gate_decision=${HUMAN_GATE_DECISION:-}
github_approval_history=${GITHUB_APPROVAL_HISTORY:-}
private_work_item=${PRIVATE_WORK_ITEM:-}
snapshot_file=${SNAPSHOT_FILE:-}
alternative_id=${ALTERNATIVE_ID:-deploy-as-is}
repetition=${REPETITION:-1}
harness_image=${ORACLE_HARNESS_IMAGE:-}
currency_reference_image=${CURRENCY_REFERENCE_IMAGE:-}
policy_file=${ORACLE_POLICY:-${repo_root}/experiment/oracle/policy-v1.json}
fidelity_policy=${FIDELITY_POLICY:-${repo_root}/experiment/pdt/fidelity-policy.json}
namespace=${NAMESPACE:-oracle}
local_port=${LOCAL_PORT:-18082}
engineering_duration=${ENGINEERING_DURATION_SECONDS:-}
engineering_users=${ENGINEERING_USERS:-}
allow_cloud=${ALLOW_EXPERIMENTAL_CLOUD_EXECUTION:-false}
cost_review=${COST_REVIEW_ACKNOWLEDGED:-false}
allow_oracle=${ALLOW_ORACLE_CLOUD_EXECUTION:-false}
candidate_rollout_timeout=${CANDIDATE_ROLLOUT_TIMEOUT:-3m}

port_forward_pid=""
cloud_started=false
run_succeeded=false
run_dir=""
runtime_manifest=""
human_gate_validation=""
treatment_decision="block"
prediction_available=false

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

for command_name in curl date find git jq kubectl python3 sha256sum sort stat timeout; do
  require_command "$command_name"
done

[[ "$mode" == "engineering" || "$mode" == "confirmatory" ]] || {
  echo "MODE must be engineering or confirmatory." >&2
  exit 1
}
[[ "$candidate_id" =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "CANDIDATE_ID is required and contains invalid characters." >&2
  exit 1
}
[[ "$alternative_id" =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "ALTERNATIVE_ID contains invalid characters." >&2
  exit 1
}
[[ "$namespace" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || {
  echo "NAMESPACE must be a valid Kubernetes namespace name." >&2
  exit 1
}
[[ "$repetition" =~ ^[1-9][0-9]*$ ]] || {
  echo "REPETITION must be a positive integer." >&2
  exit 1
}
if [[ ! "$local_port" =~ ^[1-9][0-9]*$ ]] || (( local_port > 65535 )); then
  echo "LOCAL_PORT must be between 1 and 65535." >&2
  exit 1
fi
for required_file in "$candidate_definition" "$conventional_decision" "$private_work_item" "$snapshot_file" "$policy_file" "$fidelity_policy"; do
  [[ -f "$required_file" ]] || {
    echo "Required oracle input file not found: $required_file" >&2
    exit 1
  }
done

immutable_image_pattern='^[a-z0-9.-]+/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$'
[[ "$harness_image" =~ $immutable_image_pattern ]] || {
  echo "ORACLE_HARNESS_IMAGE must be an immutable registry digest." >&2
  exit 1
}
[[ "$currency_reference_image" =~ $immutable_image_pattern ]] || {
  echo "CURRENCY_REFERENCE_IMAGE must be an immutable registry digest." >&2
  exit 1
}

candidate_definition_sha256=$(sha256sum "$candidate_definition" | cut -d ' ' -f1)
private_mode=$(stat -c '%a' "$private_work_item")
if (( (8#$private_mode & 8#077) != 0 )); then
  echo "PRIVATE_WORK_ITEM must not be readable or writable by group or others." >&2
  exit 1
fi
if ! jq -e --arg candidate "$candidate_id" --arg alternative "$alternative_id" --arg mode "$mode" '
  .candidate_id == $candidate
  and ([.alternatives[] | select(.id == $alternative and .action == "deploy")] | length == 1)
  and ($mode != "confirmatory" or .confirmatory_eligibility == true)
' "$candidate_definition" >/dev/null; then
  echo "Candidate definition does not contain the requested deployable alternative or mode eligibility." >&2
  exit 1
fi
control_decision=$(jq -er '.decision' "$conventional_decision")
if ! jq -e --arg candidate "$candidate_id" --arg sha256 "$candidate_definition_sha256" '
  .mechanism == "conventional-ci-cd-with-staging"
  and .candidate_id == $candidate
  and (.decision == "approve" or .decision == "block")
  and .control_decision_sealed == true
  and .candidate_definition_sha256 == $sha256
  and (.immutable_artifacts | type == "array")
  and (
    .decision == "approve"
    or (
      .staging.executed == true
      and (.immutable_artifacts | length > 0)
    )
  )
' "$conventional_decision" >/dev/null; then
  echo "Oracle runtime requires either an approved control or a staging-blocked control with sealed deployable artifacts." >&2
  exit 1
fi
if [[ "$control_decision" == "approve" ]]; then
  for required_file in "$pdt_decision" "$deployment_gate"; do
    [[ -f "$required_file" ]] || {
      echo "Approved control requires sealed PDT and gate input: $required_file" >&2
      exit 1
    }
  done
  if [[ -z "$pdt_prediction_decision" ]] \
    && [[ $(jq -r '.mechanism // ""' "$pdt_decision") != "candidate-level-pdt-decision" ]]; then
    pdt_prediction_decision=$pdt_decision
  fi
  treatment_decision=$(jq -er '.decision | select(. == "approve" or . == "block" or . == "reconfigure")' "$pdt_decision")
  if [[ "$treatment_decision" == "approve" || "$treatment_decision" == "reconfigure" ]]; then
    for required_file in "$deployment_action" "$human_gate_decision" \
      "$github_approval_history"; do
      [[ -f "$required_file" ]] || {
        echo "Deployable PDT action requires protected human gate input: $required_file" >&2
        exit 1
      }
    done
    human_gate_validation=$(python3 \
      "${repo_root}/experiment/scripts/validate-human-gate-receipt.py" \
      --candidate-definition "$candidate_definition" \
      --snapshot "$snapshot_file" \
      --conventional-decision "$conventional_decision" \
      --pdt-decision "$pdt_decision" \
      --deployment-gate "$deployment_gate" \
      --deployment-action "$deployment_action" \
      --human-gate-decision "$human_gate_decision" \
      --github-approval-history "$github_approval_history")
    [[ $(jq -r '.validated' <<<"$human_gate_validation") == "true" ]] || {
      echo "Protected human gate validation did not succeed." >&2
      exit 1
    }
    pdt_selected_alternative=$(jq -er '.selected_alternative' "$pdt_decision")
    [[ $(jq -r '.selected_alternative' <<<"$human_gate_validation") == "$pdt_selected_alternative" ]] || {
      echo "Protected human decision differs from the sealed PDT action." >&2
      exit 1
    }
  else
    if ! jq -e --arg candidate "$candidate_id" --arg snapshot "$(jq -er '.snapshot_id' "$snapshot_file")" \
      --slurpfile control "$conventional_decision" '
      .candidate == $candidate
      and .snapshot_id == $snapshot
      and .decision == "block"
      and .artifact_binding.staging_binding_verified == true
      and .artifact_binding.immutable_artifacts == $control[0].immutable_artifacts
      and .artifact_binding.candidate_definition_sha256 == $control[0].candidate_definition_sha256
    ' "$pdt_decision" >/dev/null || ! jq -e --arg candidate "$candidate_id" '
      .candidate_id == $candidate
      and .gate_state == "blocked"
      and .pdt.decision == "block"
      and .human_confirmation.status == "not-requested"
      and .operational_mutation_performed == false
    ' "$deployment_gate" >/dev/null; then
      echo "Blocked PDT oracle path requires matching sealed PDT and gate decisions." >&2
      exit 1
    fi
  fi
  pdt_decision_sha256=$(sha256sum "$pdt_decision" | cut -d ' ' -f1)
  if [[ -n "$pdt_prediction_decision" ]]; then
    if [[ ! -f "$pdt_prediction_decision" ]] || ! jq -e \
      --arg candidate "$candidate_id" --arg alternative "$alternative_id" \
      --arg mode "$mode" --argjson repetition "$repetition" \
      --arg candidate_sha256 "$candidate_definition_sha256" \
      --slurpfile control "$conventional_decision" '
      .candidate == $candidate
      and .repetition == $repetition
      and .execution_mode == $mode
      and .operational_mutation_performed == false
      and .artifact_binding.candidate_definition_sha256 == $candidate_sha256
      and .artifact_binding.staging_binding_verified == true
      and .artifact_binding.immutable_artifacts == $control[0].immutable_artifacts
      and ([.alternatives_evaluated[] |
        select(
          .id == $alternative
          and .action == "deploy"
          and (.predicted_metrics | type == "object")
        )] | length == 1)
    ' "$pdt_prediction_decision" >/dev/null; then
      echo "Oracle alternative lacks a matching sealed PDT prediction for this repetition." >&2
      exit 1
    fi
    pdt_prediction_decision_sha256=$(sha256sum "$pdt_prediction_decision" | cut -d ' ' -f1)
    if [[ "$pdt_decision_sha256" != "$pdt_prediction_decision_sha256" ]] \
      && ! jq -e --arg sha256 "$pdt_prediction_decision_sha256" \
        --argjson repetition "$repetition" '
        .mechanism == "candidate-level-pdt-decision"
        and .repetition == null
        and ([.evidence.pdt_decisions[] |
          select(.repetition == $repetition and .sha256 == $sha256)] | length == 1)
      ' "$pdt_decision" >/dev/null; then
        echo "PDT repetition prediction is not an input of the sealed candidate-level decision." >&2
        exit 1
    fi
    prediction_available=true
  else
    [[ -f "$pdt_invalid_repetition_ledger" ]] || {
      echo "Missing PDT prediction requires a pre-label infrastructure-invalid ledger." >&2
      exit 1
    }
    pdt_invalid_repetition_ledger_sha256=$(sha256sum "$pdt_invalid_repetition_ledger" | cut -d ' ' -f1)
    if ! jq -e --arg candidate "$candidate_id" --argjson repetition "$repetition" '
      .candidate_id == $candidate
      and .classification == "infrastructure-invalid"
      and .label_revealed == false
      and (.valid_repetitions | index($repetition) == null)
      and ([.invalid_repetitions[] |
        select(
          .repetition == $repetition
          and .attempts == 2
          and (.reasons | type == "array" and length == 2)
          and all(.reasons[]; type == "string" and length > 0)
        )] | length == 1)
    ' "$pdt_invalid_repetition_ledger" >/dev/null \
      || ! jq -e --arg sha256 "$pdt_invalid_repetition_ledger_sha256" '
        .mechanism == "candidate-level-pdt-decision"
        and .evidence.infrastructure_invalid_ledger.sha256 == $sha256
      ' "$pdt_decision" >/dev/null; then
      echo "Missing PDT prediction is not authorized by the sealed pre-label ledger." >&2
      exit 1
    fi
  fi
fi
if ! jq -e --arg candidate "$candidate_id" --arg sha256 "$candidate_definition_sha256" \
  --arg control_decision "$control_decision" --arg treatment_decision "$treatment_decision" \
  --argjson repetition "$repetition" '
  .candidate_id == $candidate
  and .candidate_definition_sha256 == $sha256
  and (.repetitions | index($repetition) != null)
  and .control_decision == $control_decision
  and .treatment_decision.decision == $treatment_decision
' "$private_work_item" >/dev/null; then
  echo "Private oracle work item does not authorize this candidate and repetition." >&2
  exit 1
fi
if ! jq -e --arg mode "$mode" '
  .policy_id == "checkout-oracle-v1"
  and (.execution_limits.cleanup_required == true)
  and ($mode != "confirmatory" or .status == "frozen")
' "$policy_file" >/dev/null; then
  echo "Oracle policy is invalid or not frozen for confirmatory execution." >&2
  exit 1
fi
if ! jq -e --arg mode "$mode" '
  .policy_id == "checkout-pdt-fidelity-v1"
  and .twin_object == "checkoutservice"
  and .controls.post_decision_only == true
  and .controls.model_mutation_allowed == false
  and .controls.confirmatory_corpus_recalibration_allowed == false
  and .controls.minimum_valid_repetitions == 2
  and .controls.missing_repetitions_require_prelabel_infrastructure_ledger == true
  and .controls.complete_matrix_scope
    == "every-deployable-alternative-x-every-valid-pdt-repetition"
  and (
    $mode != "confirmatory"
    or (.status == "frozen" and (.frozen_at | type == "string" and length > 0))
  )
' "$fidelity_policy" >/dev/null; then
  echo "Fidelity policy is invalid or not frozen for confirmatory execution." >&2
  exit 1
fi
if ! jq -e '
  .binding.twin_object.kind == "Deployment"
  and .binding.twin_object.name == "checkoutservice"
  and (.binding.source_namespace | type == "string" and length > 0)
  and (.binding.source_namespace_uid | type == "string" and length > 0)
  and ([.synchronized_state.workloads[] | select(.name == "checkoutservice")] | length == 1)
  and ([.synchronized_state.workloads[] | select(.name == "currencyservice")] | length == 1)
' "$snapshot_file" >/dev/null; then
  echo "SNAPSHOT_FILE is not a valid checkout PDT source snapshot." >&2
  exit 1
fi
if [[ "$mode" == "confirmatory" && ( -n "$engineering_duration" || -n "$engineering_users" ) ]]; then
  echo "Confirmatory oracle execution does not accept engineering workload overrides." >&2
  exit 1
fi
if [[ -n "$engineering_duration" && ! "$engineering_duration" =~ ^[1-9][0-9]*$ ]]; then
  echo "ENGINEERING_DURATION_SECONDS must be a positive integer." >&2
  exit 1
fi
if [[ -n "$engineering_users" && ! "$engineering_users" =~ ^[1-9][0-9]*$ ]]; then
  echo "ENGINEERING_USERS must be a positive integer." >&2
  exit 1
fi

if [[ "$allow_cloud" != "true" || "$cost_review" != "true" || "$allow_oracle" != "true" ]]; then
  echo "Oracle execution starts billable GKE workloads and is disabled by default." >&2
  echo "It requires ALLOW_EXPERIMENTAL_CLOUD_EXECUTION=true, COST_REVIEW_ACKNOWLEDGED=true and ALLOW_ORACLE_CLOUD_EXECUTION=true after protocol and cost review." >&2
  exit 1
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
run_id="oracle-${candidate_id}-${alternative_id}-r${repetition}-${timestamp}"
run_dir="${repo_root}/experiment/evidence/oracle/${run_id}"
runtime_manifest="${run_dir}/runtime.json"
functional_dir="${run_dir}/functional-results"
performance_dir="${run_dir}/performance"
mkdir -p "$run_dir" "$performance_dir"

write_status() {
  jq -n --arg run_id "$run_id" --arg state "$1" \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{run_id: $run_id, state: $state, updated_at: $timestamp}' >"${run_dir}/status.json"
}

stop_port_forward() {
  if [[ -n "$port_forward_pid" ]] && kill -0 "$port_forward_pid" 2>/dev/null; then
    kill "$port_forward_pid" 2>/dev/null || true
    wait "$port_forward_pid" 2>/dev/null || true
  fi
  port_forward_pid=""
}

cleanup_runtime() {
  local cleanup_ok=true
  stop_port_forward
  if [[ "$cloud_started" == "true" && -f "$runtime_manifest" ]]; then
    if ! kubectl delete -f "$runtime_manifest" --ignore-not-found --wait=true --timeout=10m \
      >>"${run_dir}/cleanup.log" 2>&1; then
      cleanup_ok=false
    fi
    if [[ -n $(kubectl get deployments --namespace "$namespace" \
      --selector experiment-role=oracle-runtime -o name 2>>"${run_dir}/cleanup.log") ]]; then
      cleanup_ok=false
    fi
  fi
  jq -n --argjson attempted "$cloud_started" --argjson completed "$cleanup_ok" \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{attempted: $attempted, completed: $completed, checked_at: $timestamp}' \
    >"${run_dir}/cleanup.json"
  if [[ "$cleanup_ok" != "true" ]]; then
    return 1
  fi
  cloud_started=false
}

on_exit() {
  local exit_code=$?
  trap - EXIT
  if [[ "$run_succeeded" != "true" ]]; then
    cleanup_runtime || true
    write_status failed || true
  fi
  exit "$exit_code"
}

remaining_seconds() {
  local current remaining
  current=$(date +%s)
  remaining=$((deadline_epoch - current))
  if (( remaining <= 0 )); then
    echo "Oracle repetition exceeded its policy time limit." >&2
    return 1
  fi
  printf '%s\n' "$remaining"
}

run_with_deadline() {
  local remaining
  remaining=$(remaining_seconds)
  timeout --signal=TERM --kill-after=10s "${remaining}s" "$@"
}

write_status running
trap on_exit EXIT
trap 'exit 130' INT TERM

cp "$candidate_definition" "${run_dir}/candidate-definition.json"
cp "$conventional_decision" "${run_dir}/conventional-decision.json"
cp "$snapshot_file" "${run_dir}/pdt-input-state.json"
cp "$policy_file" "${run_dir}/oracle-policy.json"
if [[ "$control_decision" == "approve" ]]; then
  cp "$pdt_decision" "${run_dir}/pdt-decision.json"
  if [[ "$prediction_available" == "true" ]]; then
    cp "$pdt_prediction_decision" "${run_dir}/pdt-prediction-decision.json"
  else
    cp "$pdt_invalid_repetition_ledger" \
      "${run_dir}/pdt-invalid-repetition-ledger.json"
  fi
  cp "$deployment_gate" "${run_dir}/deployment-gate.json"
  if [[ "$treatment_decision" == "approve" || "$treatment_decision" == "reconfigure" ]]; then
    cp "$deployment_action" "${run_dir}/deployment-action.json"
    cp "$human_gate_decision" "${run_dir}/human-gate-decision.json"
    cp "$github_approval_history" "${run_dir}/github-environment-approvals.json"
    printf '%s\n' "$human_gate_validation" | jq . \
      >"${run_dir}/human-gate-validation.json"
  fi
fi

python3 "${repo_root}/experiment/scripts/prepare-oracle-runtime.py" \
  --private-work-item "$private_work_item" \
  --candidate-definition "$candidate_definition" \
  --conventional-decision "$conventional_decision" \
  --snapshot "$snapshot_file" \
  --alternative-id "$alternative_id" \
  --harness-image "$harness_image" \
  --currency-reference-image "$currency_reference_image" \
  --namespace "$namespace" \
  --output "$runtime_manifest" >"${run_dir}/prepare-runtime.log"

source_namespace=$(jq -er '.binding.source_namespace | select(test("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"))' "$snapshot_file")
source_namespace_uid=$(jq -er '.binding.source_namespace_uid' "$snapshot_file")
current_source_uid=$(kubectl get namespace "$source_namespace" -o jsonpath='{.metadata.uid}')
[[ "$current_source_uid" == "$source_namespace_uid" ]] || {
  echo "Current Kubernetes context is not the cluster instance bound to the PDT snapshot." >&2
  exit 1
}
kubectl get namespace "$namespace" >/dev/null
active_pods=$(kubectl get pods --namespace "$namespace" -o json | jq '[.items[] | select(.status.phase != "Succeeded" and .status.phase != "Failed")] | length')
if (( active_pods > 0 )); then
  echo "Namespace $namespace contains active pods; cleanup is required before an oracle repetition." >&2
  exit 1
fi

maximum_minutes=$(jq -er '.execution_limits.maximum_minutes_per_repetition | select(type == "number" and . > 0)' "$policy_file")
deadline_epoch=$(($(date +%s) + maximum_minutes * 60))
cloud_started=true
kubectl apply -f "$runtime_manifest" >"${run_dir}/apply.log"

run_with_deadline kubectl rollout status deployment/oracle-harness \
  --namespace "$namespace" --timeout=5m >>"${run_dir}/rollout.log"
run_with_deadline kubectl rollout status deployment/currency-reference \
  --namespace "$namespace" --timeout=5m >>"${run_dir}/rollout.log"

jq -r '.items[] | select(.kind == "Deployment") | select(.metadata.name != "oracle-harness" and .metadata.name != "currency-reference") | [.metadata.name, (.spec.replicas // 1)] | @tsv' \
  "$runtime_manifest" | while IFS=$'\t' read -r deployment desired_replicas; do
    if (( desired_replicas == 0 )); then
      printf '%s\n' "deployment/${deployment}: desired replicas are zero; readiness intentionally not required" \
        >>"${run_dir}/candidate-rollout.log"
      continue
    fi
    if kubectl rollout status "deployment/${deployment}" --namespace "$namespace" \
      --timeout="$candidate_rollout_timeout" >>"${run_dir}/candidate-rollout.log" 2>&1; then
      printf '%s\n' "deployment/${deployment}: ready" >>"${run_dir}/candidate-rollout.log"
    else
      printf '%s\n' "deployment/${deployment}: not ready; preserved as candidate behavior" \
        >>"${run_dir}/candidate-rollout.log"
    fi
  done

kubectl get deployments --namespace "$namespace" -o json >"${run_dir}/deployments-start.json"
kubectl get pods --namespace "$namespace" -o json >"${run_dir}/pods-start.json"
kubectl get services --namespace "$namespace" -o json >"${run_dir}/services.json"
kubectl get events --namespace "$namespace" -o json >"${run_dir}/events-start.json"

kubectl port-forward --namespace "$namespace" service/oracle-harness \
  "${local_port}:8080" >"${run_dir}/port-forward.log" 2>&1 &
port_forward_pid=$!
for _ in $(seq 1 60); do
  if ! kill -0 "$port_forward_pid" 2>/dev/null; then
    echo "Oracle harness port-forward exited before becoming healthy." >&2
    exit 1
  fi
  if curl -fsS --max-time 2 "http://127.0.0.1:${local_port}/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS --max-time 5 "http://127.0.0.1:${local_port}/healthz" >"${run_dir}/harness-health.txt"
endpoint="http://127.0.0.1:${local_port}"

run_with_deadline python3 "${repo_root}/experiment/scripts/run-oracle-functional-suite.py" \
  --policy "$policy_file" --candidate-id "$candidate_id" \
  --alternative-id "$alternative_id" --repetition "$repetition" \
  --endpoint "$endpoint" --output-directory "$functional_dir" \
  >"${run_dir}/functional-suite.log"

mapfile -t functional_results < <(find "$functional_dir" -maxdepth 1 -type f \
  -name '*.json' ! -name manifest.json -print | sort)
(( ${#functional_results[@]} > 0 )) || {
  echo "Oracle functional suite produced no result files." >&2
  exit 1
}
functional_arguments=()
for result_file in "${functional_results[@]}"; do
  functional_arguments+=(--result "$result_file")
done
run_with_deadline python3 "${repo_root}/experiment/scripts/evaluate-oracle-functional.py" \
  --policy "$policy_file" --manifest "${functional_dir}/manifest.json" \
  "${functional_arguments[@]}" --output "${run_dir}/functional-report.json" \
  >"${run_dir}/functional-evaluation.log"

performance_arguments=()
while IFS= read -r profile_id; do
  profile_output="${performance_dir}/${profile_id}.json"
  samples_output="${performance_dir}/${profile_id}-samples.csv"
  profile_command=(
    python3 "${repo_root}/experiment/scripts/run-oracle-performance-profile.py"
    --policy "$policy_file" --profile-id "$profile_id"
    --candidate-id "$candidate_id" --alternative-id "$alternative_id"
    --repetition "$repetition" --endpoint "$endpoint" --mode "$mode"
    --output "$profile_output" --samples-output "$samples_output"
  )
  if [[ -n "$engineering_duration" ]]; then
    profile_command+=(--engineering-duration-seconds "$engineering_duration")
  fi
  if [[ -n "$engineering_users" ]]; then
    profile_command+=(--engineering-users "$engineering_users")
  fi
  run_with_deadline "${profile_command[@]}" >"${performance_dir}/${profile_id}.log"
  performance_arguments+=(--performance-profile "$profile_output")
done < <(jq -r '.performance_profiles[] | select(.required == true) | .id' "$policy_file")

kubectl get deployments --namespace "$namespace" -o json >"${run_dir}/deployments-end.json"
kubectl get pods --namespace "$namespace" -o json >"${run_dir}/pods-end.json"
kubectl get events --namespace "$namespace" -o json >"${run_dir}/events-end.json"

python3 "${repo_root}/experiment/scripts/evaluate-oracle-health.py" \
  --candidate-id "$candidate_id" --alternative-id "$alternative_id" \
  --repetition "$repetition" --pods-start "${run_dir}/pods-start.json" \
  --pods-end "${run_dir}/pods-end.json" \
  --deployments-end "${run_dir}/deployments-end.json" \
  --output "${run_dir}/health.json" >"${run_dir}/health-evaluation.log"

python3 "${repo_root}/experiment/scripts/compose-oracle-observation.py" \
  --policy "$policy_file" --candidate-id "$candidate_id" \
  --alternative-id "$alternative_id" --repetition "$repetition" --mode "$mode" \
  --functional-report "${run_dir}/functional-report.json" \
  "${performance_arguments[@]}" --health "${run_dir}/health.json" \
  --output "${run_dir}/observation.json" >"${run_dir}/compose-observation.log"

fidelity_report=""
if [[ "$control_decision" == "approve" && "$prediction_available" == "true" ]]; then
  fidelity_report="${run_dir}/pdt-fidelity.json"
  python3 "${repo_root}/experiment/scripts/calculate-pdt-fidelity.py" \
    --policy "$fidelity_policy" --oracle-policy "$policy_file" \
    --pdt-decision "$pdt_prediction_decision" \
    --oracle-observation "${run_dir}/observation.json" \
    --output "$fidelity_report" >"${run_dir}/fidelity.log"
fi

pdt_decision_sha256=""
pdt_prediction_decision_sha256=""
pdt_invalid_repetition_ledger_sha256=""
fidelity_report_sha256=""
if [[ -n "$pdt_decision" ]]; then
  pdt_decision_sha256=$(sha256sum "$pdt_decision" | cut -d ' ' -f1)
fi
if [[ -n "$pdt_prediction_decision" ]]; then
  pdt_prediction_decision_sha256=$(sha256sum "$pdt_prediction_decision" | cut -d ' ' -f1)
fi
if [[ -n "$pdt_invalid_repetition_ledger" ]]; then
  pdt_invalid_repetition_ledger_sha256=$(sha256sum "$pdt_invalid_repetition_ledger" | cut -d ' ' -f1)
fi
if [[ -n "$fidelity_report" ]]; then
  fidelity_report_sha256=$(sha256sum "$fidelity_report" | cut -d ' ' -f1)
fi

jq -n \
  --arg schema_version "1.0.0" --arg run_id "$run_id" --arg mode "$mode" \
  --arg candidate_id "$candidate_id" --arg alternative_id "$alternative_id" \
  --argjson repetition "$repetition" --arg namespace "$namespace" \
  --arg harness_image "$harness_image" --arg currency_reference_image "$currency_reference_image" \
  --arg candidate_definition_sha256 "$candidate_definition_sha256" \
  --arg conventional_decision_sha256 "$(sha256sum "$conventional_decision" | cut -d ' ' -f1)" \
  --arg private_work_item_sha256 "$(sha256sum "$private_work_item" | cut -d ' ' -f1)" \
  --arg snapshot_sha256 "$(sha256sum "$snapshot_file" | cut -d ' ' -f1)" \
  --arg oracle_policy_sha256 "$(sha256sum "$policy_file" | cut -d ' ' -f1)" \
  --arg fidelity_policy_sha256 "$(sha256sum "$fidelity_policy" | cut -d ' ' -f1)" \
  --arg pdt_decision_sha256 "$pdt_decision_sha256" \
  --arg pdt_prediction_decision_sha256 "$pdt_prediction_decision_sha256" \
  --arg pdt_invalid_repetition_ledger_sha256 "$pdt_invalid_repetition_ledger_sha256" \
  --arg fidelity_report_sha256 "$fidelity_report_sha256" \
  --arg runtime_sha256 "$(sha256sum "$runtime_manifest" | cut -d ' ' -f1)" '
  {
    schema_version: $schema_version,
    run_id: $run_id,
    mode: $mode,
    candidate_id: $candidate_id,
    alternative_id: $alternative_id,
    repetition: $repetition,
    namespace: $namespace,
    public_endpoint_created: false,
    operational_mutation_performed: false,
    images: {oracle_harness: $harness_image, currency_reference: $currency_reference_image},
    input_sha256: {
      candidate_definition: $candidate_definition_sha256,
      conventional_decision: $conventional_decision_sha256,
      private_work_item: $private_work_item_sha256,
      pdt_snapshot: $snapshot_sha256,
      oracle_policy: $oracle_policy_sha256,
      fidelity_policy: $fidelity_policy_sha256,
      pdt_decision: (if $pdt_decision_sha256 == "" then null else $pdt_decision_sha256 end),
      pdt_prediction_decision: (
        if $pdt_prediction_decision_sha256 == "" then null
        else $pdt_prediction_decision_sha256
        end
      ),
      pdt_invalid_repetition_ledger: (
        if $pdt_invalid_repetition_ledger_sha256 == "" then null
        else $pdt_invalid_repetition_ledger_sha256
        end
      ),
      runtime: $runtime_sha256
    },
    pdt_fidelity: (
      if $fidelity_report_sha256 == "" then null
      else {path: "pdt-fidelity.json", sha256: $fidelity_report_sha256}
      end
    )
  }' >"${run_dir}/metadata.json"

cleanup_runtime
write_status completed
run_succeeded=true
printf '%s\n' "$run_dir"
