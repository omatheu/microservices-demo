#!/usr/bin/env bash

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
project_id=${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}
billing_account=${BILLING_ACCOUNT:-016329-9946EB-FE858E}
budget_display_name=${BUDGET_DISPLAY_NAME:-Online Boutique TCC - gross cost guard}
environment=${ENVIRONMENT:-operational}
namespace=${NAMESPACE:-$environment}
scenario_id=${SCENARIO_ID:-unspecified}
candidate_id=${CANDIDATE_ID:-current}
alternative_id=${ALTERNATIVE_ID:-as-is}
repetition=${REPETITION:-1}
lookback_minutes=${LOOKBACK_MINUTES:-15}
end_time=${END_TIME:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}
start_time=${START_TIME:-$(date -u -d "${lookback_minutes} minutes ago" +%Y-%m-%dT%H:%M:%SZ)}
run_timestamp=$(date -u +%Y%m%dT%H%M%SZ)
run_id="obs-${scenario_id}-${candidate_id}-${alternative_id}-r${repetition}-${run_timestamp}"
run_dir="${repo_root}/experiment/evidence/observability/${run_id}"
metrics_file="${repo_root}/experiment/observability/canonical-metrics.json"

require_command() {
  command -v "$1" >/dev/null 2>&1 || { echo "Required command not found: $1" >&2; exit 1; }
}

for command_name in curl date gcloud git jq kubectl; do
  require_command "$command_name"
done

if ! [[ "$repetition" =~ ^[1-9][0-9]*$ && "$lookback_minutes" =~ ^[1-9][0-9]*$ ]]; then
  echo "REPETITION and LOOKBACK_MINUTES must be positive integers." >&2
  exit 1
fi

for identifier in "$environment" "$namespace" "$scenario_id" "$candidate_id" "$alternative_id"; do
  if ! [[ "$identifier" =~ ^[a-zA-Z0-9._-]+$ ]]; then
    echo "Identifiers may contain only letters, numbers, dot, underscore and hyphen." >&2
    exit 1
  fi
done

mkdir -p "${run_dir}/raw"

write_status() {
  jq -n --arg run_id "$run_id" --arg state "$1" --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{run_id: $run_id, state: $state, updated_at: $timestamp}' > "${run_dir}/status.json"
}

write_status running
trap 'write_status failed' ERR

access_token=$(gcloud auth print-access-token)
while IFS=$'\t' read -r metric_id metric_type; do
  output_file="${run_dir}/raw/${metric_id}.json"
  curl -fsS -G -H "Authorization: Bearer ${access_token}" \
    --data-urlencode "filter=metric.type=\"${metric_type}\" AND resource.type=\"k8s_container\" AND resource.labels.namespace_name=\"${namespace}\"" \
    --data-urlencode "interval.startTime=${start_time}" \
    --data-urlencode "interval.endTime=${end_time}" \
    --data-urlencode 'view=FULL' \
    --data-urlencode 'pageSize=1000' \
    "https://monitoring.googleapis.com/v3/projects/${project_id}/timeSeries" > "$output_file"
done < <(jq -r '.metrics[] | [.id, .type] | @tsv' "$metrics_file")
unset access_token

printf 'metric_id,metric_type,unit,project_id,location,cluster_name,namespace_name,pod_name,container_name,point_start_time,point_end_time,value\n' > "${run_dir}/metrics.csv"
while IFS=$'\t' read -r metric_id metric_type metric_unit; do
  jq -r --arg metric_id "$metric_id" --arg metric_type "$metric_type" --arg unit "$metric_unit" '
    (.timeSeries // [])[] as $series |
    ($series.points // [])[] |
    [
      $metric_id,
      $metric_type,
      $unit,
      ($series.resource.labels.project_id // ""),
      ($series.resource.labels.location // ""),
      ($series.resource.labels.cluster_name // ""),
      ($series.resource.labels.namespace_name // ""),
      ($series.resource.labels.pod_name // ""),
      ($series.resource.labels.container_name // ""),
      (.interval.startTime // ""),
      (.interval.endTime // ""),
      (.value.doubleValue // .value.int64Value // "")
    ] | @csv
  ' "${run_dir}/raw/${metric_id}.json" >> "${run_dir}/metrics.csv"
done < <(jq -r '.metrics[] | [.id, .type, .unit] | @tsv' "$metrics_file")

kubectl get deployments --namespace "$namespace" -o json > "${run_dir}/deployments.json"
kubectl get pods --namespace "$namespace" -o json > "${run_dir}/pods.json"
kubectl get services --namespace "$namespace" -o json > "${run_dir}/services.json"
kubectl get resourcequota --namespace "$namespace" -o json > "${run_dir}/resourcequotas.json"
kubectl get events --namespace "$namespace" -o json > "${run_dir}/events.json"

duration_seconds=$(date -u -d "$end_time" +%s)
duration_seconds=$((duration_seconds - $(date -u -d "$start_time" +%s)))

resource_totals=$(kubectl get deployments --namespace "$namespace" -o json | jq '
  def cpu_cores:
    if . == null then 0
    elif endswith("m") then (rtrimstr("m") | tonumber) / 1000
    else tonumber end;
  def bytes:
    if . == null then 0
    elif endswith("Ki") then (rtrimstr("Ki") | tonumber) * 1024
    elif endswith("Mi") then (rtrimstr("Mi") | tonumber) * 1048576
    elif endswith("Gi") then (rtrimstr("Gi") | tonumber) * 1073741824
    else tonumber end;
  reduce .items[] as $deployment (
    {cpu_request_cores: 0, memory_request_bytes: 0};
    ($deployment.spec.replicas // 1) as $replicas |
    .cpu_request_cores += ($replicas * ([($deployment.spec.template.spec.containers // [])[] | (.resources.requests.cpu // null) | cpu_cores] | add // 0)) |
    .memory_request_bytes += ($replicas * ([($deployment.spec.template.spec.containers // [])[] | (.resources.requests.memory // null) | bytes] | add // 0))
  )')

budget_info=null
if budget_list=$(gcloud billing budgets list --billing-account="$billing_account" --format=json 2>/dev/null); then
  budget_info=$(jq \
    --arg display_name "$budget_display_name" \
    '[.[] | select(.displayName == $display_name)][0] // null' <<< "$budget_list")
fi

jq -n \
  --argjson duration_seconds "$duration_seconds" \
  --argjson totals "$resource_totals" \
  --argjson budget "$budget_info" \
  --arg billing_account "$billing_account" \
  '{
    measurement_duration_seconds: $duration_seconds,
    requested_capacity: {
      cpu_request_cores: $totals.cpu_request_cores,
      memory_request_bytes: $totals.memory_request_bytes,
      cpu_request_core_hours: ($totals.cpu_request_cores * $duration_seconds / 3600),
      memory_request_gib_hours: ($totals.memory_request_bytes / 1073741824 * $duration_seconds / 3600)
    },
    monetary_cost: {
      currency: "BRL",
      attributable_gross_cost: null,
      status: "billing-export-not-configured",
      note: "No monetary value is inferred from list prices; join a detailed billing export by project and interval."
    },
    budget_context: {
      billing_account: $billing_account,
      budget: $budget
    }
  }' > "${run_dir}/cost-and-duration.json"

row_count=$(($(wc -l < "${run_dir}/metrics.csv") - 1))
jq -n \
  --arg schema_version "1.0.0" \
  --arg run_id "$run_id" \
  --arg project_id "$project_id" \
  --arg environment "$environment" \
  --arg namespace "$namespace" \
  --arg scenario_id "$scenario_id" \
  --arg candidate_id "$candidate_id" \
  --arg alternative_id "$alternative_id" \
  --argjson repetition "$repetition" \
  --arg start_time "$start_time" \
  --arg end_time "$end_time" \
  --argjson duration_seconds "$duration_seconds" \
  --argjson metric_rows "$row_count" \
  --arg git_commit "$(git -C "$repo_root" rev-parse HEAD)" \
  '{
    schema_version: $schema_version,
    run_id: $run_id,
    identity: {
      project_id: $project_id,
      environment: $environment,
      namespace: $namespace,
      scenario_id: $scenario_id,
      candidate_id: $candidate_id,
      alternative_id: $alternative_id,
      repetition: $repetition
    },
    window: {started_at: $start_time, ended_at: $end_time, duration_seconds: $duration_seconds},
    collection: {provider: "google-cloud-monitoring", metric_rows: $metric_rows},
    git_commit: $git_commit,
    artifacts: {
      canonical_metrics: "../../../observability/canonical-metrics.json",
      normalized_metrics: "metrics.csv",
      raw_metrics: "raw/",
      cost_and_duration: "cost-and-duration.json",
      deployments: "deployments.json",
      pods: "pods.json",
      services: "services.json",
      quotas: "resourcequotas.json",
      events: "events.json"
    }
  }' > "${run_dir}/manifest.json"

trap - ERR
write_status completed
printf '%s\n' "$run_dir"
