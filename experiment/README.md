# Experiment tooling and evidence

This directory contains reproducible tooling and generated evidence for the
experiment tracked in [`../docs/tcc-experiment-roadmap.md`](../docs/tcc-experiment-roadmap.md).

O desenho comparativo e as regras contra vazamento estão em
[`protocol/README.md`](./protocol/README.md). Enquanto esse protocolo não
estiver com status `frozen`, novas execuções são apenas de engenharia e não
podem ser incluídas na análise confirmatória CI/CD convencional × CI/CD
acrescida do PDT.

O plano estatístico executável está documentado em
[`analysis/README.md`](./analysis/README.md). Seu modo normal aceita somente um
dataset completo vinculado ao hash de um protocolo congelado; pilotos usam uma
trava explícita e permanecem inelegíveis.

## Operational baseline

Run a baseline repetition with:

```sh
./experiment/scripts/capture-operational-baseline.sh
```

Optional environment variables:

```sh
NAMESPACE=operational WARMUP_SECONDS=30 SAMPLE_COUNT=60 SAMPLE_INTERVAL_SECONDS=1 \
  ./experiment/scripts/capture-operational-baseline.sh
```

Each repetition creates an immutable timestamped directory under
`evidence/baseline/` containing:

- `summary.json`: canonical result and latency percentiles;
- `http-samples.csv`: individual external HTTP measurements;
- `latencies-sorted.txt`: probe latency distribution sorted in milliseconds;
- `locust-start.txt` and `locust-end.txt`: cumulative Locust counters;
- `pod-metrics-start.tsv` and `pod-metrics-end.tsv`: CPU and memory snapshots;
- Kubernetes JSON for deployments, pods, services, quotas, and events;
- `rendered-operational.yaml`: exact rendered workload configuration;
- `terraform-outputs.json`: infrastructure outputs;
- `metadata.json`: cluster, Git, tool, and image metadata.

The HTTP probe is deliberately reported separately from Locust. Locust measures
the configured user workload and failure count. The probe supplies the raw
latency distribution used for p50, p95, and p99.

After collecting multiple repetitions, consolidate them with:

```sh
./experiment/scripts/summarize-operational-baseline.sh
```

The aggregate is written to `evidence/baseline/aggregate-summary.json` and
includes cross-run mean, range, and standard deviation for latency metrics.

Before using the baseline for protocol calibration, verify that every raw
sample and resource artifact still matches both tracked aggregates:

```sh
python3 experiment/scripts/validate-baseline-evidence.py --repo-root .
```

The committed `evidence/baseline/validation-report.json` records the SHA-256
chain for the initial three operational repetitions and three checkout
repetitions. Raw directories remain local or in pipeline artifacts; missing or
modified evidence makes the validator fail closed.

## Common observability export

The common collection process is documented in
[`observability/README.md`](./observability/README.md). It uses GKE Cloud
Monitoring and exports equivalent windows for `operational`, `staging`, and
`pdt` without depending on pod lifetime.
