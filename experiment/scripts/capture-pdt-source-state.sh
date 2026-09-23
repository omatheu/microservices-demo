#!/usr/bin/env bash

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
binding_file=${BINDING_FILE:-${repo_root}/experiment/pdt/source-binding.json}
project_id=$(jq -r '.project_id' "$binding_file")
cluster_name=$(jq -r '.cluster_name' "$binding_file")
cluster_location=$(jq -r '.cluster_location' "$binding_file")
source_namespace=$(jq -r '.source_namespace' "$binding_file")
target_namespace=$(jq -r '.target_namespace' "$binding_file")
twin_object=$(jq -r '.twin_object.name' "$binding_file")
lookback_minutes=${LOOKBACK_MINUTES:-15}
captured_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
snapshot_timestamp=$(date -u +%Y%m%dT%H%M%SZ)
snapshot_id="operational-state-${snapshot_timestamp}"
snapshot_dir="${repo_root}/experiment/evidence/pdt-state/${snapshot_id}"
window_start=$(date -u -d "${lookback_minutes} minutes ago" +%Y-%m-%dT%H:%M:%SZ)

require_command() {
  command -v "$1" >/dev/null 2>&1 || { echo "Required command not found: $1" >&2; exit 1; }
}
for command_name in gcloud git jq kubectl; do require_command "$command_name"; done
[[ "$lookback_minutes" =~ ^[1-9][0-9]*$ ]] || { echo "LOOKBACK_MINUTES must be a positive integer." >&2; exit 1; }

mkdir -p "$snapshot_dir"
write_status() {
  jq -n --arg snapshot_id "$snapshot_id" --arg state "$1" --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{snapshot_id: $snapshot_id, state: $state, updated_at: $timestamp}' > "${snapshot_dir}/status.json"
}
write_status running
trap 'write_status failed' ERR

cp "$binding_file" "${snapshot_dir}/source-binding.json"
gcloud container clusters describe "$cluster_name" --region "$cluster_location" --project "$project_id" --format=json > "${snapshot_dir}/cluster.json"
kubectl get namespace "$source_namespace" -o json > "${snapshot_dir}/namespace.json"
kubectl get deployments --namespace "$source_namespace" -o json > "${snapshot_dir}/deployments.json"
kubectl get pods --namespace "$source_namespace" -o json > "${snapshot_dir}/pods.json"
kubectl get services --namespace "$source_namespace" -o json > "${snapshot_dir}/services.json"
kubectl get resourcequota --namespace "$source_namespace" -o json > "${snapshot_dir}/resourcequotas.json"
kubectl get events --namespace "$source_namespace" -o json > "${snapshot_dir}/events.json"
kubectl kustomize "${repo_root}/infra/kustomize/operational" > "${snapshot_dir}/rendered-operational.yaml"
kubectl logs deployment/loadgenerator --namespace "$source_namespace" --container main | awk '/Aggregated/{line=$0} END{print line}' > "${snapshot_dir}/locust-aggregate.txt"

observability_dir=$(PROJECT_ID="$project_id" ENVIRONMENT=operational NAMESPACE="$source_namespace" \
  SCENARIO_ID=pdt-sync CANDIDATE_ID=current ALTERNATIVE_ID=observed REPETITION=1 \
  START_TIME="$window_start" END_TIME="$captured_at" \
  "${repo_root}/experiment/scripts/export-observability-window.sh")
printf '%s\n' "${observability_dir#"${repo_root}"/}" > "${snapshot_dir}/observability-evidence.txt"

jq '[.items[] | {
  name: .metadata.name,
  uid: .metadata.uid,
  generation: .metadata.generation,
  resource_version: .metadata.resourceVersion,
  replicas: (.spec.replicas // 1),
  available_replicas: (.status.availableReplicas // 0),
  containers: [.spec.template.spec.containers[] | {
    name,
    image,
    env: (.env // []),
    resources: (.resources // {})
  }]
}]' "${snapshot_dir}/deployments.json" > "${snapshot_dir}/workload-state.json"

jq '.items[] | select(.metadata.name == "loadgenerator") | {
  deployment_uid: .metadata.uid,
  replicas: (.spec.replicas // 1),
  image: .spec.template.spec.containers[0].image,
  users: ([.spec.template.spec.containers[0].env[] | select(.name == "USERS") | .value][0] // null),
  spawn_rate: ([.spec.template.spec.containers[0].env[] | select(.name == "RATE") | .value][0] // null),
  frontend_address: ([.spec.template.spec.containers[0].env[] | select(.name == "FRONTEND_ADDR") | .value][0] // null)
}' "${snapshot_dir}/deployments.json" > "${snapshot_dir}/load-profile.json"

jq -n \
  --arg schema_version "1.0.0" --arg snapshot_id "$snapshot_id" --arg captured_at "$captured_at" \
  --arg window_start "$window_start" --arg project_id "$project_id" --arg cluster_name "$cluster_name" \
  --arg cluster_location "$cluster_location" --arg source_namespace "$source_namespace" --arg target_namespace "$target_namespace" \
  --arg twin_object "$twin_object" \
  --arg cluster_self_link "$(jq -r '.selfLink' "${snapshot_dir}/cluster.json")" \
  --arg namespace_uid "$(jq -r '.metadata.uid' "${snapshot_dir}/namespace.json")" \
  --arg observability_evidence "${observability_dir#"${repo_root}"/}" \
  --arg git_commit "$(git -C "$repo_root" rev-parse HEAD)" \
  --slurpfile workloads "${snapshot_dir}/workload-state.json" \
  --slurpfile load_profile "${snapshot_dir}/load-profile.json" \
  --slurpfile quotas "${snapshot_dir}/resourcequotas.json" '
  {
    schema_version: $schema_version,
    snapshot_id: $snapshot_id,
    captured_at: $captured_at,
    observation_window: {started_at: $window_start, ended_at: $captured_at},
    binding: {
      project_id: $project_id,
      cluster_name: $cluster_name,
      cluster_location: $cluster_location,
      cluster_self_link: $cluster_self_link,
      source_namespace: $source_namespace,
      source_namespace_uid: $namespace_uid,
      target_namespace: $target_namespace,
      twin_object: {kind: "Deployment", name: $twin_object},
      relationship: "observes-and-simulates"
    },
    synchronized_state: {
      workloads: $workloads[0],
      load_profile: $load_profile[0],
      resource_quotas: $quotas[0].items
    },
    evidence: {observability: $observability_evidence},
    provenance: {git_commit: $git_commit, immutable_for_decision: true}
  }' > "${snapshot_dir}/pdt-input-state.json"

trap - ERR
write_status completed
printf '%s\n' "$snapshot_dir"
