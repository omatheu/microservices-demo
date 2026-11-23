#!/usr/bin/env bash

set -euo pipefail

namespace=${NAMESPACE:-}
output_file=${OUTPUT_FILE:-}
minimum_expected_deployments=${MINIMUM_EXPECTED_DEPLOYMENTS:-1}
stability_window_seconds=${STABILITY_WINDOW_SECONDS:-60}
timeout_seconds=${STABILITY_TIMEOUT_SECONDS:-600}
poll_interval_seconds=${POLL_INTERVAL_SECONDS:-5}
excluded_deployments=${EXCLUDED_DEPLOYMENTS:-}

for value in "$minimum_expected_deployments" "$stability_window_seconds" "$timeout_seconds" "$poll_interval_seconds"; do
  [[ "$value" =~ ^[0-9]+$ ]] || {
    echo "Workload stability controls must be non-negative integers." >&2
    exit 2
  }
done
[[ "$namespace" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || {
  echo "NAMESPACE must be a valid Kubernetes namespace." >&2
  exit 2
}
[[ -n "$output_file" && "$minimum_expected_deployments" -gt 0 && "$timeout_seconds" -gt 0 && "$poll_interval_seconds" -gt 0 ]] || {
  echo "OUTPUT_FILE and positive workload stability limits are required." >&2
  exit 2
}

for command_name in date dirname jq kubectl mkdir mktemp rm sleep; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Required command not found: $command_name" >&2
    exit 2
  }
done

temporary_directory=$(mktemp -d /tmp/tcc-workload-stability.XXXXXX)
trap 'rm -rf -- "$temporary_directory"' EXIT
started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
deadline=$((SECONDS + timeout_seconds))
stable_since=-1
previous_restart_count=-1
sample_count=0
deployment_count=0
unavailable_deployments=0
not_ready_pods=0
restart_count=0
excluded_deployments_json=$(jq -cn --arg value "$excluded_deployments" \
  '$value | split(",") | map(select(length > 0)) | unique | sort')
unavailable_deployment_names='[]'
not_ready_pod_apps='[]'

write_receipt() {
  local state=$1
  mkdir -p "$(dirname "$output_file")"
  jq -n \
    --arg namespace "$namespace" --arg state "$state" --arg started_at "$started_at" \
    --arg completed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --argjson minimum_expected_deployments "$minimum_expected_deployments" \
    --argjson stability_window_seconds "$stability_window_seconds" \
    --argjson timeout_seconds "$timeout_seconds" --argjson samples "$sample_count" \
    --argjson excluded_deployments "$excluded_deployments_json" \
    --argjson deployment_count "$deployment_count" \
    --argjson unavailable_deployments "$unavailable_deployments" \
    --argjson unavailable_deployment_names "$unavailable_deployment_names" \
    --argjson not_ready_pods "$not_ready_pods" --argjson not_ready_pod_apps "$not_ready_pod_apps" \
    --argjson restart_count "$restart_count" '
    {
      schema_version: "1.0.0",
      mechanism: "continuous-workload-stability-gate",
      namespace: $namespace,
      state: $state,
      started_at: $started_at,
      completed_at: $completed_at,
      required: {
        minimum_expected_deployments: $minimum_expected_deployments,
        stability_window_seconds: $stability_window_seconds,
        timeout_seconds: $timeout_seconds,
        all_desired_replicas_available: true,
        all_active_pods_ready: true,
        restart_count_stable: true,
        excluded_candidate_deployments: $excluded_deployments
      },
      samples: $samples,
      final_observation: {
        deployment_count: $deployment_count,
        unavailable_deployments: $unavailable_deployments,
        unavailable_deployment_names: $unavailable_deployment_names,
        not_ready_pods: $not_ready_pods,
        not_ready_pod_apps: $not_ready_pod_apps,
        restart_count: $restart_count
      },
      classification: (if $state == "stable" then "eligible" else "infrastructure-invalid" end)
    }' >"$output_file"
}

while :; do
  sample_count=$((sample_count + 1))
  kubectl get deployments --namespace "$namespace" -o json >"${temporary_directory}/deployments.json"
  kubectl get pods --namespace "$namespace" -o json >"${temporary_directory}/pods.json"

  deployment_count=$(jq '.items | length' "${temporary_directory}/deployments.json")
  unavailable_deployment_names=$(jq -c --argjson excluded "$excluded_deployments_json" '[.items[] | select(
    (.metadata.name as $name | ($excluded | index($name)) == null)
    and
    (.spec.replicas // 1) > 0 and (
      (.status.observedGeneration // 0) < (.metadata.generation // 0)
      or (.status.availableReplicas // 0) != (.spec.replicas // 1)
      or (.status.readyReplicas // 0) != (.spec.replicas // 1)
      or (.status.updatedReplicas // 0) != (.spec.replicas // 1)
    )
  ) | .metadata.name] | unique | sort' "${temporary_directory}/deployments.json")
  unavailable_deployments=$(jq 'length' <<<"$unavailable_deployment_names")
  not_ready_pod_apps=$(jq -c --argjson excluded "$excluded_deployments_json" '[.items[] | select(
    ((.metadata.labels.app // "") as $app | ($excluded | index($app)) == null)
    and (
    .metadata.deletionTimestamp != null
    or (
      .status.phase != "Succeeded" and .status.phase != "Failed" and (
        .status.phase != "Running"
        or ([.status.conditions[]? | select(.type == "Ready" and .status == "True")] | length) != 1
        or any(.status.containerStatuses[]?; .ready != true)
      )
    ))
  ) | (.metadata.labels.app // .metadata.name)] | unique | sort' "${temporary_directory}/pods.json")
  not_ready_pods=$(jq 'length' <<<"$not_ready_pod_apps")
  restart_count=$(jq --argjson excluded "$excluded_deployments_json" '[.items[] |
    select((.metadata.labels.app // "") as $app | ($excluded | index($app)) == null) |
    .status.containerStatuses[]?.restartCount] | add // 0' "${temporary_directory}/pods.json")

  healthy=false
  if (( deployment_count >= minimum_expected_deployments && unavailable_deployments == 0 && not_ready_pods == 0 )); then
    healthy=true
  fi
  if [[ "$healthy" == "true" && ( "$previous_restart_count" -lt 0 || "$restart_count" -eq "$previous_restart_count" ) ]]; then
    if (( stable_since < 0 )); then
      stable_since=$SECONDS
    fi
    if (( SECONDS - stable_since >= stability_window_seconds )); then
      write_receipt stable
      printf '%s\n' "$output_file"
      exit 0
    fi
  else
    stable_since=-1
  fi
  previous_restart_count=$restart_count

  if (( SECONDS >= deadline )); then
    write_receipt unstable
    echo "Namespace ${namespace} did not remain healthy for ${stability_window_seconds}s." >&2
    exit 70
  fi
  sleep "$poll_interval_seconds"
done
