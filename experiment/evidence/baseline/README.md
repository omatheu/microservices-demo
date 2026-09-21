# Operational baseline — initial result

## Collection status

- Environment: `operational`
- Valid repetitions: 3
- Warmup per repetition: 30 seconds
- Probe samples per repetition: 60
- Probe interval: 1 second
- Locust users: 10
- Valid run IDs:
  - `baseline-20260920T022124Z`
  - `baseline-20260920T022349Z`
  - `baseline-20260920T022612Z`

The directory `baseline-20260920T021817Z` is explicitly marked incomplete and
must not be used in analysis. It records a collector serialization defect found
before the three valid repetitions.

## Initial aggregate

| Metric | Result |
| --- | ---: |
| Probe samples | 180 |
| Probe successes | 180 |
| Probe failures | 0 |
| Probe success rate | 100% |
| Mean latency across runs | 426.074 ms |
| Mean run p50 | 420.466 ms |
| Mean run p95 | 506.872 ms |
| Mean run p99 | 889.166 ms |
| Locust requests during windows | 818 |
| Locust failures during windows | 0 |

Cross-run standard deviation:

| Metric | Standard deviation |
| --- | ---: |
| Mean latency | 10.317 ms |
| p50 | 5.836 ms |
| p95 | 20.690 ms |
| p99 | 283.090 ms |

The canonical machine-readable result is
[`aggregate-summary.json`](./aggregate-summary.json).

The fail-closed auditor
[`../../scripts/validate-baseline-evidence.py`](../../scripts/validate-baseline-evidence.py)
recomputed counts, nearest-rank quantiles and cross-run statistics from every
raw sample; it also verified the completed status, timestamps, resource
artifacts and stable deployment set. The resulting
[`validation-report.json`](./validation-report.json) binds every local raw
artifact by SHA-256 to the tracked operational and checkout aggregates. Both
the auditor and report are frozen protocol inputs.

## Interpretation boundary

The external HTTP probe and Locust answer different questions:

- the external probe measures end-to-end reachability and latency from the
  collection host to the public frontend;
- Locust measures the configured internal user journey and its failures.

The initial baseline is sufficient to validate the evidence pipeline and
estimate normal behavior for the next phase. It is not yet a final statistical
baseline. With only 60 probe samples per repetition, p99 is the largest sample
in each run and is sensitive to isolated network outliers. Longer measurement
windows and more repetitions must be used for the definitive experiment.

CPU, memory, replicas, resources, images, restarts, events, quotas, and exact
rendered configuration are preserved inside every valid run directory.
