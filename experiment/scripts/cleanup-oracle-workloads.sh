#!/usr/bin/env bash

set -euo pipefail

allow_cleanup=${ALLOW_ORACLE_CLEANUP:-false}
output_file=${OUTPUT_FILE:-}
expected_context="gke_microservices-demo-tcc_us-central1_online-boutique-experiment"
namespace=oracle
runtime_names=(checkoutservice oracle-harness currency-reference currency-candidate payment-candidate)
network_policy_names=(oracle-deny-all oracle-runtime-internal-only)

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

for command_name in date dirname jq kubectl mkdir sleep; do
  require_command "$command_name"
done

if [[ "$allow_cleanup" != "true" ]]; then
  echo "Oracle cleanup requires ALLOW_ORACLE_CLEANUP=true." >&2
  exit 1
fi
if [[ -z "$output_file" ]]; then
  echo "OUTPUT_FILE is required for Oracle cleanup evidence." >&2
  exit 1
fi
current_context=$(kubectl config current-context)
if [[ "$current_context" != "$expected_context" ]]; then
  echo "Refusing Oracle cleanup outside the reviewed experiment cluster context." >&2
  exit 1
fi

before_active_pods=$(kubectl get pods --namespace "$namespace" -o json | jq \
  '[.items[] | select(.status.phase != "Succeeded" and .status.phase != "Failed")] | length')

kubectl delete deployments.apps --namespace "$namespace" \
  "${runtime_names[@]}" --ignore-not-found --wait=false >/dev/null
kubectl delete services --namespace "$namespace" \
  "${runtime_names[@]}" --ignore-not-found --wait=false >/dev/null
kubectl delete serviceaccounts --namespace "$namespace" \
  "${runtime_names[@]}" --ignore-not-found --wait=false >/dev/null
kubectl delete networkpolicies.networking.k8s.io --namespace "$namespace" \
  "${network_policy_names[@]}" --ignore-not-found --wait=false >/dev/null

deadline=$((SECONDS + 600))
cleanup_complete=true
after_active_pods=$before_active_pods
while :; do
  after_active_pods=$(kubectl get pods --namespace "$namespace" -o json | jq \
    '[.items[] | select(.status.phase != "Succeeded" and .status.phase != "Failed")] | length')
  if (( after_active_pods == 0 )); then
    break
  fi
  if (( SECONDS >= deadline )); then
    cleanup_complete=false
    break
  fi
  sleep 5
done

remaining_deployments=$(kubectl get deployments --namespace "$namespace" -o json | jq \
  '[.items[] | select(.metadata.labels["experiment-role"] == "oracle-runtime")] | length')
if (( remaining_deployments > 0 )); then
  cleanup_complete=false
fi

mkdir -p "$(dirname "$output_file")"
jq -n \
  --arg context "$current_context" \
  --arg captured_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg namespace "$namespace" \
  --argjson before_active_pods "$before_active_pods" \
  --argjson after_active_pods "$after_active_pods" \
  --argjson remaining_deployments "$remaining_deployments" \
  --argjson cleanup_complete "$cleanup_complete" '
  {
    schema_version: "1.0.0",
    mechanism: "oracle-workload-cleanup",
    captured_at: $captured_at,
    cluster_context: $context,
    namespace: $namespace,
    before_active_pods: $before_active_pods,
    after_active_pods: $after_active_pods,
    remaining_oracle_deployments: $remaining_deployments,
    cleanup_complete: $cleanup_complete,
    operational_namespace_touched: false,
    persistent_volumes_touched: false
  }' >"$output_file"

jq -e '
  .cleanup_complete == true
  and .after_active_pods == 0
  and .remaining_oracle_deployments == 0
  and .operational_namespace_touched == false
  and .persistent_volumes_touched == false
' "$output_file" >/dev/null
printf '%s\n' "$output_file"
