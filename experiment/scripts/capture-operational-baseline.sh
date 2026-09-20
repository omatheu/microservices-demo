#!/usr/bin/env bash

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
namespace=${NAMESPACE:-operational}
warmup_seconds=${WARMUP_SECONDS:-30}
sample_count=${SAMPLE_COUNT:-60}
sample_interval_seconds=${SAMPLE_INTERVAL_SECONDS:-1}
run_timestamp=$(date -u +%Y%m%dT%H%M%SZ)
run_id="baseline-${run_timestamp}"
run_dir="${repo_root}/experiment/evidence/baseline/${run_id}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

for command_name in awk curl git gcloud jq kubectl sort terraform; do
  require_command "$command_name"
done

if ! [[ "$warmup_seconds" =~ ^[0-9]+$ && "$sample_count" =~ ^[1-9][0-9]*$ && "$sample_interval_seconds" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "Warmup and sampling parameters must be non-negative numeric values." >&2
  exit 1
fi

mkdir -p "$run_dir"

write_status() {
  local state=$1
  jq -n --arg run_id "$run_id" --arg state "$state" --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{run_id: $run_id, state: $state, updated_at: $timestamp}' > "${run_dir}/status.json"
}

write_status running
trap 'write_status failed' ERR

frontend_ip=$(kubectl get service frontend-external --namespace "$namespace" -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
if [ -z "$frontend_ip" ]; then
  echo "The frontend LoadBalancer does not have an external IP." >&2
  exit 1
fi
frontend_url="http://${frontend_ip}/"

unavailable_deployments=$(kubectl get deployments --namespace "$namespace" -o json | jq '[.items[] | select(.status.availableReplicas != .spec.replicas)] | length')
if [ "$unavailable_deployments" -ne 0 ]; then
  echo "Baseline aborted: ${unavailable_deployments} deployment(s) unavailable." >&2
  exit 1
fi

extract_locust_aggregate() {
  kubectl logs deployment/loadgenerator --namespace "$namespace" --container main | awk '/Aggregated/{line=$0} END{print line}'
}

locust_start=$(extract_locust_aggregate)
printf '%s\n' "$locust_start" > "${run_dir}/locust-start.txt"

kubectl get deployments --namespace "$namespace" -o json > "${run_dir}/deployments-start.json"
kubectl get pods --namespace "$namespace" -o json > "${run_dir}/pods-start.json"
kubectl get services --namespace "$namespace" -o json > "${run_dir}/services.json"
kubectl get resourcequota --namespace "$namespace" -o json > "${run_dir}/resourcequotas.json"
kubectl get events --namespace "$namespace" -o json > "${run_dir}/events-start.json"
kubectl top pods --namespace "$namespace" --no-headers > "${run_dir}/pod-metrics-start.tsv"
kubectl kustomize "${repo_root}/infra/kustomize/operational" > "${run_dir}/rendered-operational.yaml"
terraform -chdir="${repo_root}/infra/terraform" output -json > "${run_dir}/terraform-outputs.json"

measurement_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if [ "$warmup_seconds" -gt 0 ]; then
  sleep "$warmup_seconds"
fi

printf 'sequence,timestamp_utc,http_status,latency_seconds,latency_ms,success\n' > "${run_dir}/http-samples.csv"
for sequence in $(seq 1 "$sample_count"); do
  sample_timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  curl_result=$(curl --silent --show-error --output /dev/null --max-time 15 --write-out '%{http_code},%{time_total}' "$frontend_url" || printf '000,15.000000')
  http_status=${curl_result%%,*}
  latency_seconds=${curl_result#*,}
  latency_ms=$(awk -v seconds="$latency_seconds" 'BEGIN { printf "%.3f", seconds * 1000 }')
  if [[ "$http_status" =~ ^2[0-9][0-9]$ ]]; then
    success=true
  else
    success=false
  fi
  printf '%s,%s,%s,%s,%s,%s\n' "$sequence" "$sample_timestamp" "$http_status" "$latency_seconds" "$latency_ms" "$success" >> "${run_dir}/http-samples.csv"
  if [ "$sequence" -lt "$sample_count" ]; then
    sleep "$sample_interval_seconds"
  fi
done
measurement_ended_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

locust_end=$(extract_locust_aggregate)
printf '%s\n' "$locust_end" > "${run_dir}/locust-end.txt"

kubectl get deployments --namespace "$namespace" -o json > "${run_dir}/deployments-end.json"
kubectl get pods --namespace "$namespace" -o json > "${run_dir}/pods-end.json"
kubectl get events --namespace "$namespace" -o json > "${run_dir}/events-end.json"
kubectl top pods --namespace "$namespace" --no-headers > "${run_dir}/pod-metrics-end.tsv"

latencies_file="${run_dir}/latencies-sorted.txt"
awk -F, 'NR > 1 { print $5 }' "${run_dir}/http-samples.csv" | sort -n > "$latencies_file"

percentile() {
  local percentile_value=$1
  awk -v percentile_value="$percentile_value" '
    { values[NR] = $1 }
    END {
      rank = int((percentile_value * NR) + 0.999999)
      if (rank < 1) rank = 1
      if (rank > NR) rank = NR
      printf "%.3f", values[rank]
    }
  ' "$latencies_file"
}

success_count=$(awk -F, 'NR > 1 && $6 == "true" { count++ } END { print count + 0 }' "${run_dir}/http-samples.csv")
failure_count=$((sample_count - success_count))
success_rate=$(awk -v successes="$success_count" -v total="$sample_count" 'BEGIN { printf "%.6f", successes / total }')
latency_min=$(head -n 1 "$latencies_file")
latency_max=$(tail -n 1 "$latencies_file")
latency_mean=$(awk '{ sum += $1 } END { printf "%.3f", sum / NR }' "$latencies_file")
latency_p50=$(percentile 0.50)
latency_p95=$(percentile 0.95)
latency_p99=$(percentile 0.99)

locust_start_requests=$(awk '{print $2}' "${run_dir}/locust-start.txt")
locust_end_requests=$(awk '{print $2}' "${run_dir}/locust-end.txt")
locust_start_failures=$(awk '{value=$3; sub(/\(.*/, "", value); print value}' "${run_dir}/locust-start.txt")
locust_end_failures=$(awk '{value=$3; sub(/\(.*/, "", value); print value}' "${run_dir}/locust-end.txt")
locust_request_delta=$((locust_end_requests - locust_start_requests))
locust_failure_delta=$((locust_end_failures - locust_start_failures))

kubectl get deployments --namespace "$namespace" -o json | jq '[.items[] | {
  name: .metadata.name,
  desired_replicas: (.spec.replicas // 0),
  available_replicas: (.status.availableReplicas // 0),
  images: ([((.spec.template.spec.initContainers // [])[] | .image), (.spec.template.spec.containers[] | .image)]),
  resources: ([((.spec.template.spec.initContainers // [])[] | {name, resources}), (.spec.template.spec.containers[] | {name, resources})])
}]' > "${run_dir}/workload-configuration.json"

jq -n \
  --arg run_id "$run_id" \
  --arg captured_at "$measurement_ended_at" \
  --arg project_id "$(gcloud config get-value project 2>/dev/null)" \
  --arg cluster "$(kubectl config current-context)" \
  --arg namespace "$namespace" \
  --arg git_commit "$(git -C "$repo_root" rev-parse HEAD)" \
  --arg git_branch "$(git -C "$repo_root" branch --show-current)" \
  --arg kubectl_version "$(kubectl version --client -o json | jq -r .clientVersion.gitVersion)" \
  --arg terraform_version "$(terraform version -json | jq -r .terraform_version)" \
  '{
    run_id: $run_id,
    captured_at: $captured_at,
    project_id: $project_id,
    cluster_context: $cluster,
    namespace: $namespace,
    git: {commit: $git_commit, branch: $git_branch},
    tools: {kubectl: $kubectl_version, terraform: $terraform_version}
  }' > "${run_dir}/metadata.json"

jq -n \
  --arg schema_version "1.0.0" \
  --arg run_id "$run_id" \
  --arg started_at "$measurement_started_at" \
  --arg ended_at "$measurement_ended_at" \
  --arg namespace "$namespace" \
  --arg frontend_url "$frontend_url" \
  --argjson warmup_seconds "$warmup_seconds" \
  --argjson sample_count "$sample_count" \
  --arg sample_interval_seconds "$sample_interval_seconds" \
  --argjson success_count "$success_count" \
  --argjson failure_count "$failure_count" \
  --arg success_rate "$success_rate" \
  --arg latency_min "$latency_min" \
  --arg latency_max "$latency_max" \
  --arg latency_mean "$latency_mean" \
  --arg latency_p50 "$latency_p50" \
  --arg latency_p95 "$latency_p95" \
  --arg latency_p99 "$latency_p99" \
  --argjson locust_request_delta "$locust_request_delta" \
  --argjson locust_failure_delta "$locust_failure_delta" \
  '{
    schema_version: $schema_version,
    run_id: $run_id,
    environment: "operational",
    namespace: $namespace,
    measurement: {
      started_at: $started_at,
      ended_at: $ended_at,
      warmup_seconds: $warmup_seconds,
      probe: {
        url: $frontend_url,
        samples: $sample_count,
        interval_seconds: ($sample_interval_seconds | tonumber),
        successes: $success_count,
        failures: $failure_count,
        success_rate: ($success_rate | tonumber),
        latency_ms: {
          min: ($latency_min | tonumber),
          mean: ($latency_mean | tonumber),
          p50: ($latency_p50 | tonumber),
          p95: ($latency_p95 | tonumber),
          p99: ($latency_p99 | tonumber),
          max: ($latency_max | tonumber)
        }
      },
      locust: {
        requests_during_window: $locust_request_delta,
        failures_during_window: $locust_failure_delta
      }
    },
    artifacts: {
      raw_http_samples: "http-samples.csv",
      workload_configuration: "workload-configuration.json",
      pod_metrics_start: "pod-metrics-start.tsv",
      pod_metrics_end: "pod-metrics-end.tsv",
      deployments_start: "deployments-start.json",
      deployments_end: "deployments-end.json",
      pods_start: "pods-start.json",
      pods_end: "pods-end.json",
      services: "services.json",
      quotas: "resourcequotas.json",
      events_start: "events-start.json",
      events_end: "events-end.json"
    }
  }' > "${run_dir}/summary.json"

trap - ERR
write_status completed
printf '%s\n' "$run_dir"
