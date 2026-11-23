#!/usr/bin/env bash

set -euo pipefail

allow_cleanup=${ALLOW_EXPERIMENTAL_CLEANUP:-false}
output_file=${OUTPUT_FILE:-}
expected_context="gke_microservices-demo-tcc_us-central1_online-boutique-experiment"
workload_namespaces=(staging pdt)
controller_namespace=pdt-system
quiescence_window_seconds=${QUIESCENCE_WINDOW_SECONDS:-30}
poll_interval_seconds=${POLL_INTERVAL_SECONDS:-5}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

for command_name in date dirname jq kubectl mkdir mktemp rm sleep; do
  require_command "$command_name"
done

if [[ "$allow_cleanup" != "true" ]]; then
  echo "Experimental cleanup requires ALLOW_EXPERIMENTAL_CLEANUP=true." >&2
  exit 1
fi
if [[ -z "$output_file" ]]; then
  echo "OUTPUT_FILE is required for cleanup evidence." >&2
  exit 1
fi
for value in "$quiescence_window_seconds" "$poll_interval_seconds"; do
  [[ "$value" =~ ^[0-9]+$ ]] || {
    echo "Cleanup quiescence controls must be non-negative integers." >&2
    exit 1
  }
done
(( poll_interval_seconds > 0 )) || {
  echo "POLL_INTERVAL_SECONDS must be positive." >&2
  exit 1
}

current_context=$(kubectl config current-context)
if [[ "$current_context" != "$expected_context" ]]; then
  echo "Refusing cleanup outside the reviewed experiment cluster context." >&2
  exit 1
fi

temporary_directory=$(mktemp -d)
trap 'rm -rf "$temporary_directory"' EXIT

snapshot_pods() {
  local suffix=$1
  local namespace
  for namespace in "${workload_namespaces[@]}" "$controller_namespace"; do
    kubectl get pods --namespace "$namespace" -o json \
      >"${temporary_directory}/${namespace}-${suffix}.json"
  done
}

active_pod_count() {
  local suffix=$1
  jq -s '[.[].items[] | select(.status.phase != "Succeeded" and .status.phase != "Failed")] | length' \
    "${temporary_directory}/staging-${suffix}.json" \
    "${temporary_directory}/pdt-${suffix}.json" \
    "${temporary_directory}/pdt-system-${suffix}.json"
}

snapshot_resources() {
  local suffix=$1
  local namespace
  for namespace in "${workload_namespaces[@]}"; do
    kubectl get \
      deployments.apps,replicasets.apps,pods,services,endpoints,endpointslices.discovery.k8s.io,networkpolicies.networking.k8s.io \
      --namespace "$namespace" -o json >"${temporary_directory}/${namespace}-resources-${suffix}.json"
  done
  kubectl get jobs.batch,pods --namespace "$controller_namespace" -o json \
    >"${temporary_directory}/${controller_namespace}-resources-${suffix}.json"
}

remaining_resource_count() {
  local suffix=$1
  jq -s '[.[].items[]] | length' \
    "${temporary_directory}/staging-resources-${suffix}.json" \
    "${temporary_directory}/pdt-resources-${suffix}.json" \
    "${temporary_directory}/pdt-system-resources-${suffix}.json"
}

snapshot_pods before
before_active_pods=$(active_pod_count before)
snapshot_resources before
before_resources=$(remaining_resource_count before)

for namespace in "${workload_namespaces[@]}"; do
  kubectl delete deployments.apps,services,networkpolicies.networking.k8s.io --all --namespace "$namespace" \
    --ignore-not-found --wait=false
done
kubectl delete jobs.batch --all --namespace "$controller_namespace" \
  --ignore-not-found --wait=false

deadline=$((SECONDS + 600))
cleanup_complete=true
quiescent_since=-1
after_resources=$before_resources
while :; do
  snapshot_pods after
  after_active_pods=$(active_pod_count after)
  snapshot_resources after
  after_resources=$(remaining_resource_count after)
  if (( after_active_pods == 0 && after_resources == 0 )); then
    if (( quiescent_since < 0 )); then
      quiescent_since=$SECONDS
    fi
    if (( SECONDS - quiescent_since >= quiescence_window_seconds )); then
      break
    fi
  else
    quiescent_since=-1
  fi
  if (( SECONDS >= deadline )); then
    echo "Experimental workloads remain after the cleanup deadline." >&2
    cleanup_complete=false
    break
  fi
  sleep "$poll_interval_seconds"
done

mkdir -p "$(dirname "$output_file")"
jq -n \
  --arg context "$current_context" \
  --arg captured_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --argjson before_active_pods "$before_active_pods" \
  --argjson after_active_pods "$after_active_pods" \
    --argjson before_resources "$before_resources" \
    --argjson after_resources "$after_resources" \
    --argjson quiescence_window_seconds "$quiescence_window_seconds" \
  --argjson cleanup_complete "$cleanup_complete" \
  '{
    schema_version: "1.0.0",
    mechanism: "experimental-workload-cleanup",
    captured_at: $captured_at,
    cluster_context: $context,
    allowed_namespaces: ["staging", "pdt", "pdt-system"],
    deleted_controller_classes: {
      staging: ["deployments.apps", "services", "networkpolicies.networking.k8s.io"],
      pdt: ["deployments.apps", "services", "networkpolicies.networking.k8s.io"],
      "pdt-system": ["jobs.batch"]
    },
    before_active_pods: $before_active_pods,
    after_active_pods: $after_active_pods,
    before_resources: $before_resources,
    after_resources: $after_resources,
    quiescence_window_seconds: $quiescence_window_seconds,
    cleanup_complete: $cleanup_complete,
    operational_namespace_touched: false,
    oracle_namespace_touched: false,
    persistent_volumes_touched: false
  }' >"$output_file"

jq -e '.cleanup_complete == true and .after_active_pods == 0 and .after_resources == 0' "$output_file" >/dev/null
printf '%s\n' "$output_file"
