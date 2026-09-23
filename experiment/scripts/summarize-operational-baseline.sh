#!/usr/bin/env bash

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
baseline_dir="${repo_root}/experiment/evidence/baseline"
output_file="${baseline_dir}/aggregate-summary.json"

mapfile -t summaries < <(
  find "$baseline_dir" -mindepth 2 -maxdepth 2 -name summary.json -print | sort
)

if [ "${#summaries[@]}" -eq 0 ]; then
  echo "No completed baseline summaries found." >&2
  exit 1
fi

jq -s '
  def stats(values):
    (values | length) as $count |
    (values | add / $count) as $mean |
    {
      min: (values | min),
      mean: $mean,
      max: (values | max),
      standard_deviation: (
        ([values[] | (. - $mean) * (. - $mean)] | add / $count) | sqrt
      )
    };

  {
    schema_version: "1.0.0",
    generated_at: (now | todateiso8601),
    completed_runs: length,
    run_ids: [.[].run_id],
    probe: {
      total_samples: ([.[].measurement.probe.samples] | add),
      total_successes: ([.[].measurement.probe.successes] | add),
      total_failures: ([.[].measurement.probe.failures] | add),
      success_rate: (
        ([.[].measurement.probe.successes] | add) /
        ([.[].measurement.probe.samples] | add)
      ),
      latency_ms_across_runs: {
        mean: stats([.[].measurement.probe.latency_ms.mean]),
        p50: stats([.[].measurement.probe.latency_ms.p50]),
        p95: stats([.[].measurement.probe.latency_ms.p95]),
        p99: stats([.[].measurement.probe.latency_ms.p99]),
        max: stats([.[].measurement.probe.latency_ms.max])
      }
    },
    locust: {
      total_requests_during_windows: ([.[].measurement.locust.requests_during_window] | add),
      total_failures_during_windows: ([.[].measurement.locust.failures_during_window] | add)
    }
  }
' "${summaries[@]}" > "$output_file"

printf '%s\n' "$output_file"
