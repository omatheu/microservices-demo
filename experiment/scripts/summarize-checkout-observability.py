#!/usr/bin/env python3

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics-csv", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    values = defaultdict(list)
    with Path(args.metrics_csv).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if not row["pod_name"].startswith("checkoutservice-"):
                continue
            try:
                values[row["metric_id"]].append(float(row["value"]))
            except (TypeError, ValueError):
                continue

    summary = {
        metric: {
            "samples": len(metric_values),
            "mean": statistics.fmean(metric_values),
            "max": max(metric_values),
            "min": min(metric_values),
        }
        for metric, metric_values in sorted(values.items())
    }
    Path(args.output).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
