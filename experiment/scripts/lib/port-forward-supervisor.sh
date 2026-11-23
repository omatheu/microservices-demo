#!/usr/bin/env bash

SUPERVISED_PORT_FORWARD_EXIT_CODE=70
# Consumed by callers that distinguish candidate-target loss from tunnel loss.
# shellcheck disable=SC2034
SUPERVISED_PORT_FORWARD_FAILED_NAME=""
supervised_port_forward_names=()
supervised_port_forward_pids=()
supervised_port_forward_logs=()

start_supervised_port_forward() {
  local namespace=$1
  local service=$2
  local local_port=$3
  local remote_port=$4
  local log_file=$5
  local pid

  kubectl port-forward --namespace "$namespace" "service/${service}" \
    "${local_port}:${remote_port}" >"$log_file" 2>&1 &
  pid=$!
  supervised_port_forward_names+=("$service")
  supervised_port_forward_pids+=("$pid")
  supervised_port_forward_logs+=("$log_file")

  for _ in $(seq 1 60); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "Port-forward for ${service} exited during startup." >&2
      return "$SUPERVISED_PORT_FORWARD_EXIT_CODE"
    fi
    if grep -q 'Forwarding from' "$log_file"; then
      return 0
    fi
    sleep 1
  done
  echo "Port-forward for ${service} did not become ready." >&2
  return "$SUPERVISED_PORT_FORWARD_EXIT_CODE"
}

assert_supervised_port_forwards() {
  local phase=$1
  local index pid name log_file
  SUPERVISED_PORT_FORWARD_FAILED_NAME=""
  for index in "${!supervised_port_forward_pids[@]}"; do
    pid=${supervised_port_forward_pids[$index]}
    name=${supervised_port_forward_names[$index]}
    log_file=${supervised_port_forward_logs[$index]}
    if ! kill -0 "$pid" 2>/dev/null; then
      # Exported state is inspected by the staging caller after this returns.
      # shellcheck disable=SC2034
      SUPERVISED_PORT_FORWARD_FAILED_NAME=$name
      echo "Port-forward for ${name} was lost during ${phase}." >&2
      if [[ -f "$log_file" ]]; then
        tail -n 20 "$log_file" >&2 || true
      fi
      return "$SUPERVISED_PORT_FORWARD_EXIT_CODE"
    fi
  done
}

discard_last_supervised_port_forward() {
  local last_index=$(( ${#supervised_port_forward_pids[@]} - 1 ))
  if (( last_index < 0 )); then
    return 0
  fi
  local pid=${supervised_port_forward_pids[$last_index]}
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
  unset 'supervised_port_forward_names[last_index]'
  unset 'supervised_port_forward_pids[last_index]'
  unset 'supervised_port_forward_logs[last_index]'
  supervised_port_forward_names=("${supervised_port_forward_names[@]}")
  supervised_port_forward_pids=("${supervised_port_forward_pids[@]}")
  supervised_port_forward_logs=("${supervised_port_forward_logs[@]}")
}

stop_supervised_port_forwards() {
  local pid
  for pid in "${supervised_port_forward_pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
  supervised_port_forward_names=()
  supervised_port_forward_pids=()
  supervised_port_forward_logs=()
}
