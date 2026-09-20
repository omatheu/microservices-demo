#!/usr/bin/env bash

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
namespace=${NAMESPACE:-operational}
repetitions=${REPETITIONS:-3}
tests_per_repetition=${TESTS_PER_REPETITION:-20}
run_timestamp=$(date -u +%Y%m%dT%H%M%SZ)
batch_id="checkout-baseline-${run_timestamp}"
batch_dir="${repo_root}/experiment/evidence/checkout-baseline/${batch_id}"

for command_name in awk curl git jq kubectl sort; do
  command -v "$command_name" >/dev/null 2>&1 || { echo "Required command not found: $command_name" >&2; exit 1; }
done
[[ "$repetitions" =~ ^[1-9][0-9]*$ && "$tests_per_repetition" =~ ^[1-9][0-9]*$ ]] || { echo "Counts must be positive integers." >&2; exit 1; }

mkdir -p "$batch_dir"
frontend_ip=$(kubectl get service frontend-external --namespace "$namespace" -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
frontend_url="http://${frontend_ip}"
expiration_year=$((10#$(date -u +%Y) + 1))

write_status() {
  jq -n --arg batch_id "$batch_id" --arg state "$1" --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{batch_id:$batch_id,state:$state,updated_at:$timestamp}' > "${batch_dir}/status.json"
}
write_status running
trap 'write_status failed' ERR

for repetition in $(seq 1 "$repetitions"); do
  repetition_dir="${batch_dir}/repetition-${repetition}"
  mkdir -p "$repetition_dir"
  printf 'sequence,timestamp_utc,http_status,latency_ms,confirmation_marker,success\n' > "${repetition_dir}/checkout-tests.csv"
  for sequence in $(seq 1 "$tests_per_repetition"); do
    cookie_file="${repetition_dir}/cookie-${sequence}.txt"
    response_file="${repetition_dir}/response-${sequence}.html"
    curl -fsS --max-time 15 --cookie-jar "$cookie_file" --cookie "$cookie_file" "${frontend_url}/product/0PUK6V6EV0" >/dev/null
    curl -fsS --max-time 15 --cookie-jar "$cookie_file" --cookie "$cookie_file" --request POST \
      --data 'product_id=0PUK6V6EV0&quantity=1' "${frontend_url}/cart" >/dev/null
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    result=$(curl --silent --show-error --output "$response_file" --max-time 30 \
      --cookie-jar "$cookie_file" --cookie "$cookie_file" --request POST \
      --data-urlencode 'email=twin@example.com' --data-urlencode 'street_address=1600 Amphitheatre Parkway' \
      --data-urlencode 'zip_code=94043' --data-urlencode 'city=Mountain View' --data-urlencode 'state=CA' \
      --data-urlencode 'country=United States' --data-urlencode 'credit_card_number=4432801561520454' \
      --data-urlencode 'credit_card_expiration_month=12' --data-urlencode "credit_card_expiration_year=${expiration_year}" \
      --data-urlencode 'credit_card_cvv=672' --write-out '%{http_code},%{time_total}' \
      "${frontend_url}/cart/checkout" || printf '000,30.000000')
    status=${result%%,*}; seconds=${result#*,}; latency_ms=$(awk -v seconds="$seconds" 'BEGIN {printf "%.3f",seconds*1000}')
    if grep -q 'Your order is complete!' "$response_file"; then marker=true; else marker=false; fi
    if [[ "$status" =~ ^2[0-9][0-9]$ && "$marker" == true ]]; then success=true; else success=false; fi
    printf '%s,%s,%s,%s,%s,%s\n' "$sequence" "$timestamp" "$status" "$latency_ms" "$marker" "$success" >> "${repetition_dir}/checkout-tests.csv"
  done
  awk -F, 'NR>1 {print $4}' "${repetition_dir}/checkout-tests.csv" | sort -n > "${repetition_dir}/latencies-sorted.txt"
  successes=$(awk -F, 'NR>1 && $6=="true" {n++} END {print n+0}' "${repetition_dir}/checkout-tests.csv")
  failures=$((tests_per_repetition-successes))
  percentile() { awk -v p="$1" '{v[NR]=$1} END{r=int(p*NR+0.999999);if(r<1)r=1;if(r>NR)r=NR;printf "%.3f",v[r]}' "${repetition_dir}/latencies-sorted.txt"; }
  jq -n --argjson repetition "$repetition" --argjson tests "$tests_per_repetition" --argjson successes "$successes" --argjson failures "$failures" \
    --argjson p50 "$(percentile 0.50)" --argjson p95 "$(percentile 0.95)" --argjson p99 "$(percentile 0.99)" \
    '{repetition:$repetition,tests:$tests,successes:$successes,failures:$failures,latency_ms:{p50:$p50,p95:$p95,p99:$p99}}' > "${repetition_dir}/summary.json"
done

jq -s '
  def stats(v): (v|add/length) as $m | {min:(v|min),mean:$m,max:(v|max),standard_deviation:(([v[]|(. - $m)*(. - $m)]|add/length)|sqrt)};
  {schema_version:"1.0.0",generated_at:(now|todateiso8601),repetitions:length,total_tests:([.[].tests]|add),total_successes:([.[].successes]|add),total_failures:([.[].failures]|add),latency_ms:{p50:stats([.[].latency_ms.p50]),p95:stats([.[].latency_ms.p95]),p99:stats([.[].latency_ms.p99])}}
' "${batch_dir}"/repetition-*/summary.json > "${batch_dir}/aggregate-summary.json"

trap - ERR
write_status completed
printf '%s\n' "$batch_dir"
