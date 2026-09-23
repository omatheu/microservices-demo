#!/usr/bin/env bash

set -euo pipefail

project_id=${PROJECT_ID:-microservices-demo-tcc}
dataset_id=${BILLING_EXPORT_DATASET:-online_boutique_billing}
dataset_location=${BILLING_EXPORT_LOCATION:-US}
window_start=${START_TIME:-}
window_end=${END_TIME:-}
output_file=${OUTPUT_FILE:-}
maximum_bytes_billed=${MAXIMUM_BYTES_BILLED:-100000000}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

for command_name in bq dirname jq mkdir mktemp rm; do
  require_command "$command_name"
done

[[ "$project_id" == "microservices-demo-tcc" ]] || {
  echo "PROJECT_ID must be microservices-demo-tcc." >&2
  exit 1
}
[[ "$dataset_id" == "online_boutique_billing" ]] || {
  echo "BILLING_EXPORT_DATASET must be online_boutique_billing." >&2
  exit 1
}
[[ "$dataset_location" == "US" ]] || {
  echo "BILLING_EXPORT_LOCATION must be US." >&2
  exit 1
}
rfc3339='^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
[[ "$window_start" =~ $rfc3339 && "$window_end" =~ $rfc3339 && "$window_start" < "$window_end" ]] || {
  echo "START_TIME and END_TIME must define an increasing RFC3339 UTC window." >&2
  exit 1
}
[[ -n "$output_file" ]] || {
  echo "OUTPUT_FILE is required." >&2
  exit 1
}
[[ "$maximum_bytes_billed" =~ ^[1-9][0-9]*$ ]] || {
  echo "MAXIMUM_BYTES_BILLED must be a positive integer." >&2
  exit 1
}
if (( maximum_bytes_billed > 100000000 )); then
  echo "MAXIMUM_BYTES_BILLED cannot exceed the 100 MB protocol guard." >&2
  exit 1
fi

temporary_dir=$(mktemp -d /tmp/tcc-billing-window.XXXXXX)
cleanup() {
  rm -rf -- "$temporary_dir"
}
trap cleanup EXIT

bq --project_id="$project_id" --location="$dataset_location" ls --format=json \
  "${project_id}:${dataset_id}" > "${temporary_dir}/tables.json"
mapfile -t standard_tables < <(jq -r '
  [.[] | .tableReference.tableId | select(startswith("gcp_billing_export_v1_"))]
  | unique[]
' "${temporary_dir}/tables.json")
if (( ${#standard_tables[@]} != 1 )); then
  echo "Expected exactly one Standard Cloud Billing export table; found ${#standard_tables[@]}." >&2
  exit 1
fi
table_id=${standard_tables[0]}
[[ "$table_id" =~ ^gcp_billing_export_v1_[A-Fa-f0-9_]+$ ]] || {
  echo "Billing export table ID is unsafe." >&2
  exit 1
}

read -r -d '' query <<SQL || true
SELECT
  currency,
  ROUND(SUM(cost), 6) AS gross_cost_brl,
  ROUND(SUM(IFNULL((SELECT SUM(credit.amount) FROM UNNEST(credits) AS credit), 0)), 6) AS credits_brl,
  ROUND(SUM(cost + IFNULL((SELECT SUM(credit.amount) FROM UNNEST(credits) AS credit), 0)), 6) AS net_cost_brl,
  COUNT(*) AS line_items,
  MIN(usage_start_time) AS first_usage_start_time,
  MAX(usage_end_time) AS last_usage_end_time,
  MAX(export_time) AS billing_data_as_of
FROM \`${project_id}.${dataset_id}.${table_id}\`
WHERE project.id = @project_id
  AND usage_start_time >= @window_start
  AND usage_start_time < @window_end
GROUP BY currency
SQL

bq --project_id="$project_id" --location="$dataset_location" query \
  --format=json \
  --use_legacy_sql=false \
  --use_query_cache=true \
  --maximum_bytes_billed="$maximum_bytes_billed" \
  --parameter="project_id:STRING:${project_id}" \
  --parameter="window_start:TIMESTAMP:${window_start}" \
  --parameter="window_end:TIMESTAMP:${window_end}" \
  "$query" > "${temporary_dir}/rows.json"

if ! jq -e '
  length == 1
  and .[0].currency == "BRL"
  and (.[0].line_items | tonumber) > 0
  and (.[0].billing_data_as_of | type == "string")
' "${temporary_dir}/rows.json" >/dev/null; then
  echo "Billing export returned no complete BRL cost observation for the requested window." >&2
  exit 1
fi

mkdir -p "$(dirname "$output_file")"
jq --arg project_id "$project_id" --arg dataset_id "$dataset_id" \
  --arg dataset_location "$dataset_location" --arg table_id "$table_id" \
  --arg window_start "$window_start" --arg window_end "$window_end" \
  --argjson maximum_bytes_billed "$maximum_bytes_billed" '
  .[0] as $row |
  {
    schema_version: "1.0.0",
    observation_mode: "Cloud Billing Standard usage cost export",
    project_id: $project_id,
    source: {
      dataset_id: $dataset_id,
      location: $dataset_location,
      table_id: $table_id,
      maximum_bytes_billed: $maximum_bytes_billed,
      query_cache_enabled: true
    },
    window: {start: $window_start, end: $window_end},
    currency: $row.currency,
    gross_cost_brl: ($row.gross_cost_brl | tonumber),
    credits_brl: ($row.credits_brl | tonumber),
    net_cost_brl: ($row.net_cost_brl | tonumber),
    line_items: ($row.line_items | tonumber),
    first_usage_start_time: $row.first_usage_start_time,
    last_usage_end_time: $row.last_usage_end_time,
    billing_data_as_of: $row.billing_data_as_of,
    finalized_invoice_amount: false,
    cloud_execution_authorized: false
  }
' "${temporary_dir}/rows.json" > "$output_file"

jq . "$output_file"
