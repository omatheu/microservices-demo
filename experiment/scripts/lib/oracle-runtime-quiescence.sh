#!/usr/bin/env bash

# Poll the isolated Oracle namespace until both the pods created by the previous
# repetition and every resource declared by its runtime manifest are gone. The
# caller remains responsible for issuing the delete operation and for recording
# the returned counters in its evidence bundle.

oracle_active_pod_count() {
  local namespace=$1
  kubectl get pods --namespace "$namespace" -o json | jq \
    '[.items[] | select(.status.phase != "Succeeded" and .status.phase != "Failed")] | length'
}

oracle_runtime_resource_count() {
  local namespace=$1
  local runtime_manifest=$2
  local cleanup_log=$3
  local resources

  resources=$(kubectl get --namespace "$namespace" --filename "$runtime_manifest" \
    --ignore-not-found --output=name 2>>"$cleanup_log") || return 1
  if [[ -z "$resources" ]]; then
    printf '0\n'
  else
    printf '%s\n' "$resources" | awk 'NF { count += 1 } END { print count + 0 }'
  fi
}

wait_for_oracle_runtime_quiescence() {
  local namespace=$1
  local runtime_manifest=$2
  local cleanup_log=$3
  local timeout_seconds=$4
  local poll_interval_seconds=$5
  local quiescence_window_seconds=$6
  local deadline=$((SECONDS + timeout_seconds))
  local quiescent_since=-1

  ORACLE_CLEANUP_AFTER_ACTIVE_PODS=-1
  ORACLE_CLEANUP_REMAINING_RESOURCES=-1
  ORACLE_CLEANUP_OBSERVATIONS=0
  ORACLE_CLEANUP_QUIESCENT_SECONDS=0

  while :; do
    ORACLE_CLEANUP_AFTER_ACTIVE_PODS=$(oracle_active_pod_count "$namespace") || return 1
    ORACLE_CLEANUP_REMAINING_RESOURCES=$(
      oracle_runtime_resource_count "$namespace" "$runtime_manifest" "$cleanup_log"
    ) || return 1
    ORACLE_CLEANUP_OBSERVATIONS=$((ORACLE_CLEANUP_OBSERVATIONS + 1))

    if (( ORACLE_CLEANUP_AFTER_ACTIVE_PODS == 0 && ORACLE_CLEANUP_REMAINING_RESOURCES == 0 )); then
      if (( quiescent_since < 0 )); then
        quiescent_since=$SECONDS
      fi
      ORACLE_CLEANUP_QUIESCENT_SECONDS=$((SECONDS - quiescent_since))
      if (( ORACLE_CLEANUP_QUIESCENT_SECONDS >= quiescence_window_seconds )); then
        return 0
      fi
    else
      quiescent_since=-1
      ORACLE_CLEANUP_QUIESCENT_SECONDS=0
    fi

    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep "$poll_interval_seconds"
  done
}
