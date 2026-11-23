#!/usr/bin/env bash

# Run one expected-to-fail command through tee without allowing the caller's
# ERR trap to turn a recoverable attempt into a terminal orchestration error.
# The command status is written to the variable named by the first argument.
run_logged_attempt() {
  local status_variable=$1
  local log_file=$2
  local err_handler=$3
  shift 3

  [[ "$status_variable" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || {
    echo "Invalid status variable for logged attempt." >&2
    return 2
  }
  [[ -n "$log_file" && -n "$err_handler" && $# -gt 0 ]] || {
    echo "Logged attempt requires a log, ERR handler and command." >&2
    return 2
  }

  trap - ERR
  set +e
  "$@" 2>&1 | tee "$log_file"
  local -a pipeline_status=("${PIPESTATUS[@]}")
  set -e
  # The caller supplies the already-defined handler name to restore now.
  # shellcheck disable=SC2064
  trap "$err_handler" ERR

  local captured_status=${pipeline_status[0]}
  if (( captured_status == 0 && pipeline_status[1] != 0 )); then
    captured_status=${pipeline_status[1]}
  fi
  printf -v "$status_variable" '%d' "$captured_status"
}
