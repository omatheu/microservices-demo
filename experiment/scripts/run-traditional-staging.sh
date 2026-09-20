#!/usr/bin/env bash

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
namespace=${NAMESPACE:-staging}
mode=${MODE:-engineering}
local_ci_decision=${LOCAL_CI_DECISION:-}
candidate_definition=${CANDIDATE_DEFINITION:-}
candidate_id=${CANDIDATE_ID:-}
repetition=${REPETITION:-1}
candidate_path=${CANDIDATE_PATH:-${repo_root}/infra/kustomize/staging}
thresholds_file=${THRESHOLDS_FILE:-${repo_root}/experiment/staging/safety-thresholds.json}
fixed_load_file=${FIXED_LOAD_FILE:-${repo_root}/experiment/staging/fixed-loadgenerator.json}
keep_staging=${KEEP_STAGING:-false}
local_port=${LOCAL_PORT:-18080}
port_forward_pid=""

require_command() {
  command -v "$1" >/dev/null 2>&1 || { echo "Required command not found: $1" >&2; exit 1; }
}

for command_name in awk base64 curl gcloud git jq kubectl python3 sha256sum sort; do
  require_command "$command_name"
done

[[ "$mode" == "engineering" || "$mode" == "confirmatory" ]] || { echo "MODE must be engineering or confirmatory." >&2; exit 1; }
[[ -n "$local_ci_decision" && -f "$local_ci_decision" ]] || { echo "LOCAL_CI_DECISION must point to a local CI decision." >&2; exit 1; }
if [[ "$mode" == "confirmatory" && ! -f "$candidate_definition" ]]; then
  echo "Confirmatory staging requires CANDIDATE_DEFINITION." >&2
  exit 1
fi
if [[ -z "$candidate_id" ]]; then
  candidate_id=$(jq -er '.candidate_id' "$local_ci_decision")
fi

for identifier in "$namespace" "$candidate_id"; do
  [[ "$identifier" =~ ^[a-zA-Z0-9._-]+$ ]] || { echo "Invalid identifier: $identifier" >&2; exit 1; }
done
[[ "$repetition" =~ ^[1-9][0-9]*$ ]] || { echo "REPETITION must be a positive integer." >&2; exit 1; }
[[ "$keep_staging" == "true" || "$keep_staging" == "false" ]] || { echo "KEEP_STAGING must be true or false." >&2; exit 1; }

run_timestamp=$(date -u +%Y%m%dT%H%M%SZ)
run_id="staging-${candidate_id}-r${repetition}-${run_timestamp}"
run_dir="${repo_root}/experiment/evidence/staging/${run_id}"
candidate_bundle_dir="${run_dir}/candidate-bundle"
rendered_candidate="${run_dir}/rendered-candidate.yaml"

warmup_seconds=$(jq -r '.workload.warmup_seconds' "$thresholds_file")
sample_count=$(jq -r '.workload.sample_count' "$thresholds_file")
sample_interval=$(jq -r '.workload.sample_interval_seconds' "$thresholds_file")
minimum_success_rate=$(jq -r '.thresholds.minimum_success_rate' "$thresholds_file")
maximum_p95=$(jq -r '.thresholds.maximum_latency_p95_ms' "$thresholds_file")
maximum_p99=$(jq -r '.thresholds.maximum_latency_p99_ms' "$thresholds_file")
maximum_checkout_p95=$(jq -r '.thresholds.maximum_checkout_latency_p95_ms' "$thresholds_file")
maximum_checkout_p99=$(jq -r '.thresholds.maximum_checkout_latency_p99_ms' "$thresholds_file")
maximum_functional_failures=$(jq -r '.thresholds.maximum_functional_failures' "$thresholds_file")
maximum_unavailable=$(jq -r '.thresholds.maximum_unavailable_deployments' "$thresholds_file")
maximum_restart_increase=$(jq -r '.thresholds.maximum_restart_increase' "$thresholds_file")

mkdir -p "$run_dir"
cp "$local_ci_decision" "${run_dir}/local-ci-decision.json"
candidate_definition_sha256=""
if [[ -n "$candidate_definition" ]]; then
  [[ -f "$candidate_definition" ]] || { echo "CANDIDATE_DEFINITION does not exist." >&2; exit 1; }
  if ! jq -e --arg candidate "$candidate_id" --arg mode "$mode" '
    .candidate_id == $candidate
    and ([.alternatives[] | select(.id == "deploy-as-is" and .action == "deploy")] | length == 1)
    and ($mode != "confirmatory" or .confirmatory_eligibility == true)
  ' "$candidate_definition" >/dev/null; then
    echo "Candidate definition is invalid for this candidate or mode." >&2
    exit 1
  fi
  cp "$candidate_definition" "${run_dir}/candidate-definition.json"
  candidate_definition_sha256=$(sha256sum "${run_dir}/candidate-definition.json" | cut -d ' ' -f1)
fi
python3 "${repo_root}/experiment/scripts/prepare-staging-candidate.py" \
  --local-ci-decision "${run_dir}/local-ci-decision.json" \
  --candidate-id "$candidate_id" \
  --base-kustomization "$candidate_path" \
  --mode "$mode" \
  --output-directory "$candidate_bundle_dir" >/dev/null
kubectl kustomize "$candidate_bundle_dir" \
  --load-restrictor=LoadRestrictionsNone > "$rendered_candidate"
if [[ -n "$candidate_definition_sha256" ]]; then
  jq --arg sha256 "$candidate_definition_sha256" \
    '.candidate_definition_sha256 = $sha256' \
    "${candidate_bundle_dir}/candidate-binding.json" > "${candidate_bundle_dir}/candidate-binding.tmp.json"
  mv "${candidate_bundle_dir}/candidate-binding.tmp.json" "${candidate_bundle_dir}/candidate-binding.json"
fi

write_status() {
  jq -n --arg run_id "$run_id" --arg state "$1" --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{run_id: $run_id, state: $state, updated_at: $timestamp}' > "${run_dir}/status.json"
}

cleanup() {
  if [[ -n "$port_forward_pid" ]] && kill -0 "$port_forward_pid" 2>/dev/null; then
    kill "$port_forward_pid" 2>/dev/null || true
    wait "$port_forward_pid" 2>/dev/null || true
  fi
  if [[ "$keep_staging" == "false" ]]; then
    kubectl delete -f "$fixed_load_file" --ignore-not-found --wait=true --timeout=5m >> "${run_dir}/cleanup.log" 2>&1 || true
    if [[ -f "$rendered_candidate" ]]; then
      kubectl delete -f "$rendered_candidate" --ignore-not-found --wait=true --timeout=10m >> "${run_dir}/cleanup.log" 2>&1 || true
    fi
  fi
}

on_error() {
  write_status failed
  cleanup
}

write_status running
trap on_error ERR

cp "$thresholds_file" "${run_dir}/safety-thresholds.json"
deployment_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
kubectl apply -f "$rendered_candidate" > "${run_dir}/apply.log"
if [[ -n "$candidate_definition_sha256" ]]; then
  jq '[.alternatives[] | select(.id == "deploy-as-is") | .configuration_changes[]]' \
    "${run_dir}/candidate-definition.json" > "${run_dir}/candidate-configuration.json"
  while IFS= read -r change_encoded; do
    change=$(base64 --decode <<< "$change_encoded")
    deployment=$(jq -er '.deployment | select(test("^[a-z0-9-]+$"))' <<< "$change")
    patch=$(jq -ec '.patch | select(type == "object")' <<< "$change")
    kubectl patch deployment "$deployment" --namespace "$namespace" \
      --type strategic --patch "$patch" >> "${run_dir}/apply.log"
  done < <(jq -r '.[] | @base64' "${run_dir}/candidate-configuration.json")
fi

mapfile -t deployments < <(kubectl get deployments --namespace "$namespace" -o json | jq -r '.items[].metadata.name' | sort)
for deployment in "${deployments[@]}"; do
  kubectl rollout status "deployment/${deployment}" --namespace "$namespace" --timeout=12m
done > "${run_dir}/rollout.log"
kubectl apply -f "$fixed_load_file" > "${run_dir}/loadgenerator-apply.log"
kubectl rollout status deployment/loadgenerator --namespace "$namespace" --timeout=8m >> "${run_dir}/rollout.log"
ready_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

kubectl get deployments --namespace "$namespace" -o json > "${run_dir}/deployments-start.json"
kubectl get pods --namespace "$namespace" -o json > "${run_dir}/pods-start.json"
kubectl get services --namespace "$namespace" -o json > "${run_dir}/services.json"
kubectl get events --namespace "$namespace" -o json > "${run_dir}/events-start.json"

kubectl port-forward --namespace "$namespace" service/frontend "${local_port}:80" > "${run_dir}/port-forward.log" 2>&1 &
port_forward_pid=$!
for _ in $(seq 1 60); do
  if curl -fsS --max-time 2 "http://127.0.0.1:${local_port}/" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS --max-time 5 "http://127.0.0.1:${local_port}/" >/dev/null

if (( warmup_seconds > 0 )); then
  sleep "$warmup_seconds"
fi

kubectl get pods --namespace "$namespace" -o json > "${run_dir}/pods-measurement-start.json"
restart_count_start=$(jq '[.items[].status.containerStatuses[]?.restartCount] | add // 0' "${run_dir}/pods-measurement-start.json")
checkout_restart_start=$(jq '[.items[] | select(.metadata.labels.app == "checkoutservice") | .status.containerStatuses[]?.restartCount] | add // 0' "${run_dir}/pods-measurement-start.json")
locust_start=$(kubectl logs deployment/loadgenerator --namespace "$namespace" --container main | awk '/Aggregated/{line=$0} END{print line}')
printf '%s\n' "$locust_start" > "${run_dir}/locust-start.txt"

measurement_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf 'sequence,timestamp_utc,test_id,method,path,http_status,latency_ms,success\n' > "${run_dir}/http-samples.csv"
paths=("/" "/product/0PUK6V6EV0" "/cart" "/setCurrency")
methods=("GET" "GET" "GET" "POST")

for sequence in $(seq 1 "$sample_count"); do
  profile_index=$(((sequence - 1) % 4))
  path=${paths[$profile_index]}
  method=${methods[$profile_index]}
  timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if [[ "$method" == "POST" ]]; then
    curl_result=$(curl --silent --show-error --output /dev/null --max-time 15 --request POST \
      --data 'currency_code=USD' --write-out '%{http_code},%{time_total}' "http://127.0.0.1:${local_port}${path}" || printf '000,15.000000')
  else
    curl_result=$(curl --silent --show-error --output /dev/null --max-time 15 \
      --write-out '%{http_code},%{time_total}' "http://127.0.0.1:${local_port}${path}" || printf '000,15.000000')
  fi
  http_status=${curl_result%%,*}
  latency_seconds=${curl_result#*,}
  latency_ms=$(awk -v seconds="$latency_seconds" 'BEGIN {printf "%.3f", seconds * 1000}')
  if [[ "$http_status" =~ ^(2|3)[0-9][0-9]$ ]]; then success=true; else success=false; fi
  printf '%s,%s,%s,%s,%s,%s,%s,%s\n' "$sequence" "$timestamp" "profile-$profile_index" "$method" "$path" "$http_status" "$latency_ms" "$success" >> "${run_dir}/http-samples.csv"
  if (( sequence < sample_count )); then sleep "$sample_interval"; fi
done

checkout_test_count=10
printf 'sequence,timestamp_utc,http_status,latency_ms,confirmation_marker,success\n' > "${run_dir}/checkout-tests.csv"
expiration_year=$((10#$(date -u +%Y) + 1))
for checkout_sequence in $(seq 1 "$checkout_test_count"); do
  cookie_file="${run_dir}/checkout-cookie-${checkout_sequence}.txt"
  response_file="${run_dir}/checkout-response-${checkout_sequence}.html"
  curl -fsS --max-time 15 --cookie-jar "$cookie_file" --cookie "$cookie_file" \
    "http://127.0.0.1:${local_port}/product/0PUK6V6EV0" >/dev/null || true
  curl -fsS --max-time 15 --cookie-jar "$cookie_file" --cookie "$cookie_file" --request POST \
    --data 'product_id=0PUK6V6EV0&quantity=1' "http://127.0.0.1:${local_port}/cart" >/dev/null || true
  checkout_timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if checkout_result=$(curl --silent --show-error --output "$response_file" --max-time 30 \
    --cookie-jar "$cookie_file" --cookie "$cookie_file" --request POST \
    --data-urlencode 'email=twin@example.com' --data-urlencode 'street_address=1600 Amphitheatre Parkway' \
    --data-urlencode 'zip_code=94043' --data-urlencode 'city=Mountain View' --data-urlencode 'state=CA' \
    --data-urlencode 'country=United States' --data-urlencode 'credit_card_number=4432801561520454' \
    --data-urlencode 'credit_card_expiration_month=12' --data-urlencode "credit_card_expiration_year=${expiration_year}" \
    --data-urlencode 'credit_card_cvv=672' --write-out '%{http_code},%{time_total}' \
    "http://127.0.0.1:${local_port}/cart/checkout"); then :; else checkout_result='000,30.000000'; fi
  checkout_status=${checkout_result%%,*}; checkout_seconds=${checkout_result#*,}
  checkout_latency_ms=$(awk -v seconds="$checkout_seconds" 'BEGIN {printf "%.3f",seconds*1000}')
  if grep -q 'Your order is complete!' "$response_file"; then marker=true; else marker=false; fi
  if [[ "$checkout_status" =~ ^2[0-9][0-9]$ && "$marker" == true ]]; then checkout_success=true; else checkout_success=false; fi
  printf '%s,%s,%s,%s,%s,%s\n' "$checkout_sequence" "$checkout_timestamp" "$checkout_status" "$checkout_latency_ms" "$marker" "$checkout_success" >> "${run_dir}/checkout-tests.csv"
done
checkout_successes=$(awk -F, 'NR>1 && $6=="true" {n++} END {print n+0}' "${run_dir}/checkout-tests.csv")
checkout_failures=$((checkout_test_count-checkout_successes))
awk -F, 'NR>1 {print $4}' "${run_dir}/checkout-tests.csv" | sort -n > "${run_dir}/checkout-latencies-sorted.txt"
checkout_p95=$(awk '{v[NR]=$1} END{r=int(.95*NR+.999999);if(r<1)r=1;if(r>NR)r=NR;printf "%.3f",v[r]}' "${run_dir}/checkout-latencies-sorted.txt")
checkout_p99=$(awk '{v[NR]=$1} END{r=int(.99*NR+.999999);if(r<1)r=1;if(r>NR)r=NR;printf "%.3f",v[r]}' "${run_dir}/checkout-latencies-sorted.txt")

negative_test_count=2
negative_test_ids=("unsupported-card" "expired-card")
negative_card_numbers=("378282246310005" "4432801561520454")
negative_expiration_years=("$expiration_year" "$((10#$(date -u +%Y) - 1))")
printf 'test_id,http_status,confirmation_absent,cart_retained,success\n' > "${run_dir}/checkout-negative-tests.csv"
for negative_index in 0 1; do
  negative_test_id=${negative_test_ids[$negative_index]}
  negative_card=${negative_card_numbers[$negative_index]}
  negative_year=${negative_expiration_years[$negative_index]}
  negative_cookie_file="${run_dir}/negative-${negative_test_id}-cookie.txt"
  negative_response_file="${run_dir}/negative-${negative_test_id}-response.html"
  negative_cart_file="${run_dir}/negative-${negative_test_id}-cart.html"

  curl -fsS --max-time 15 --cookie-jar "$negative_cookie_file" --cookie "$negative_cookie_file" \
    --request POST --data 'product_id=0PUK6V6EV0&quantity=1' \
    "http://127.0.0.1:${local_port}/cart" >/dev/null
  if negative_result=$(curl --silent --show-error --output "$negative_response_file" --max-time 30 \
    --cookie-jar "$negative_cookie_file" --cookie "$negative_cookie_file" --request POST \
    --data-urlencode 'email=twin-negative@example.com' \
    --data-urlencode 'street_address=1600 Amphitheatre Parkway' \
    --data-urlencode 'zip_code=94043' --data-urlencode 'city=Mountain View' \
    --data-urlencode 'state=CA' --data-urlencode 'country=United States' \
    --data-urlencode "credit_card_number=${negative_card}" \
    --data-urlencode 'credit_card_expiration_month=12' \
    --data-urlencode "credit_card_expiration_year=${negative_year}" \
    --data-urlencode 'credit_card_cvv=672' --write-out '%{http_code}' \
    "http://127.0.0.1:${local_port}/cart/checkout"); then
    :
  else
    negative_result='000'
  fi
  curl -fsS --max-time 15 --cookie-jar "$negative_cookie_file" --cookie "$negative_cookie_file" \
    "http://127.0.0.1:${local_port}/cart" > "$negative_cart_file"
  if grep -q 'Your order is complete!' "$negative_response_file"; then confirmation_absent=false; else confirmation_absent=true; fi
  if grep -q '/product/0PUK6V6EV0' "$negative_cart_file"; then cart_retained=true; else cart_retained=false; fi
  if [[ "$negative_result" == "500" && "$confirmation_absent" == "true" && "$cart_retained" == "true" ]]; then
    negative_success=true
  else
    negative_success=false
  fi
  printf '%s,%s,%s,%s,%s\n' "$negative_test_id" "$negative_result" "$confirmation_absent" "$cart_retained" "$negative_success" >> "${run_dir}/checkout-negative-tests.csv"
done
negative_successes=$(awk -F, 'NR>1 && $5=="true" {n++} END {print n+0}' "${run_dir}/checkout-negative-tests.csv")
negative_failures=$((negative_test_count-negative_successes))
measurement_ended_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

kubectl get deployments --namespace "$namespace" -o json > "${run_dir}/deployments-end.json"
kubectl get pods --namespace "$namespace" -o json > "${run_dir}/pods-end.json"
kubectl get events --namespace "$namespace" -o json > "${run_dir}/events-end.json"

restart_count_end=$(jq '[.items[].status.containerStatuses[]?.restartCount] | add // 0' "${run_dir}/pods-end.json")
restart_increase=$((restart_count_end - restart_count_start))
checkout_restart_end=$(jq '[.items[] | select(.metadata.labels.app == "checkoutservice") | .status.containerStatuses[]?.restartCount] | add // 0' "${run_dir}/pods-end.json")
checkout_restart_increase=$((checkout_restart_end - checkout_restart_start))
unavailable=$(jq '[.items[] | select((.status.availableReplicas // 0) != (.spec.replicas // 0))] | length' "${run_dir}/deployments-end.json")
checkout_unavailable=$(jq '[.items[] | select(.metadata.name == "checkoutservice") | select((.status.availableReplicas // 0) != (.spec.replicas // 0))] | length' "${run_dir}/deployments-end.json")
successes=$(awk -F, 'NR > 1 && $8 == "true" {count++} END {print count + 0}' "${run_dir}/http-samples.csv")
failures=$((sample_count - successes))
success_rate=$(awk -v successes="$successes" -v total="$sample_count" 'BEGIN {printf "%.6f", successes / total}')
awk -F, 'NR > 1 {print $7}' "${run_dir}/http-samples.csv" | sort -n > "${run_dir}/latencies-sorted.txt"

percentile() {
  awk -v p="$1" '{v[NR]=$1} END {rank=int(p*NR+0.999999); if(rank<1)rank=1; if(rank>NR)rank=NR; printf "%.3f",v[rank]}' "${run_dir}/latencies-sorted.txt"
}

p50=$(percentile 0.50)
p95=$(percentile 0.95)
p99=$(percentile 0.99)
locust_end=$(kubectl logs deployment/loadgenerator --namespace "$namespace" --container main | awk '/Aggregated/{line=$0} END{print line}')
printf '%s\n' "$locust_end" > "${run_dir}/locust-end.txt"
locust_start_requests=$(awk '{print $2 + 0}' <<< "$locust_start"); locust_end_requests=$(awk '{print $2 + 0}' <<< "$locust_end")
locust_start_failures=$(awk '{v=$3;sub(/\(.*/,"",v);print v+0}' <<< "$locust_start"); locust_end_failures=$(awk '{v=$3;sub(/\(.*/,"",v);print v+0}' <<< "$locust_end")
locust_requests=$((locust_end_requests-locust_start_requests))
locust_failures=$((locust_end_failures-locust_start_failures))
if (( locust_requests > 0 )); then
  locust_success_rate=$(awk -v requests="$locust_requests" -v failures="$locust_failures" 'BEGIN {printf "%.6f", (requests-failures)/requests}')
else
  locust_success_rate=0
fi

reasons=$(jq -n \
  --argjson success_rate "$success_rate" --argjson min_success "$minimum_success_rate" \
  --argjson locust_success_rate "$locust_success_rate" \
  --argjson p95 "$p95" --argjson max_p95 "$maximum_p95" \
  --argjson p99 "$p99" --argjson max_p99 "$maximum_p99" \
  --argjson failures "$failures" --argjson max_failures "$maximum_functional_failures" \
  --argjson checkout_failures "$checkout_failures" --argjson checkout_p95 "$checkout_p95" --argjson max_checkout_p95 "$maximum_checkout_p95" \
  --argjson negative_failures "$negative_failures" \
  --argjson checkout_p99 "$checkout_p99" --argjson max_checkout_p99 "$maximum_checkout_p99" \
  --argjson unavailable "$checkout_unavailable" --argjson max_unavailable "$maximum_unavailable" \
  --argjson restarts "$checkout_restart_increase" --argjson max_restarts "$maximum_restart_increase" '
  [
    if $success_rate < $min_success then "success_rate_below_threshold" else empty end,
    if $locust_success_rate < $min_success then "locust_success_rate_below_threshold" else empty end,
    if $p95 > $max_p95 then "latency_p95_above_threshold" else empty end,
    if $p99 > $max_p99 then "latency_p99_above_threshold" else empty end,
    if $failures > $max_failures or $checkout_failures > $max_failures or $negative_failures > $max_failures then "functional_failures_above_threshold" else empty end,
    if $checkout_p95 > $max_checkout_p95 then "checkout_latency_p95_above_threshold" else empty end,
    if $checkout_p99 > $max_checkout_p99 then "checkout_latency_p99_above_threshold" else empty end,
    if $unavailable > $max_unavailable then "checkoutservice_unavailable_above_threshold" else empty end,
    if $restarts > $max_restarts then "checkoutservice_restart_increase_above_threshold" else empty end
  ]')
if [[ $(jq 'length' <<< "$reasons") -eq 0 ]]; then decision=PASS; else decision=FAIL; fi

jq -n \
  --arg schema_version "1.0.0" --arg run_id "$run_id" --arg candidate_id "$candidate_id" \
  --arg mode "$mode" \
  --argjson repetition "$repetition" --arg decision "$decision" --argjson reasons "$reasons" \
  --arg deployment_started_at "$deployment_started_at" --arg ready_at "$ready_at" \
  --arg measurement_started_at "$measurement_started_at" --arg measurement_ended_at "$measurement_ended_at" \
  --argjson samples "$sample_count" --argjson successes "$successes" --argjson failures "$failures" \
  --argjson success_rate "$success_rate" --argjson p50 "$p50" --argjson p95 "$p95" --argjson p99 "$p99" \
  --argjson unavailable "$unavailable" --argjson restart_increase "$restart_increase" \
  --argjson checkout_tests "$checkout_test_count" --argjson checkout_successes "$checkout_successes" --argjson checkout_failures "$checkout_failures" \
  --argjson negative_tests "$negative_test_count" --argjson negative_successes "$negative_successes" --argjson negative_failures "$negative_failures" \
  --argjson checkout_p95 "$checkout_p95" --argjson checkout_p99 "$checkout_p99" \
  --argjson checkout_unavailable "$checkout_unavailable" --argjson checkout_restart_increase "$checkout_restart_increase" \
  --argjson locust_requests "$locust_requests" --argjson locust_failures "$locust_failures" --argjson locust_success_rate "$locust_success_rate" \
  --arg git_commit "$(git -C "$repo_root" rev-parse HEAD)" \
  --slurpfile artifact_binding "${candidate_bundle_dir}/candidate-binding.json" '
  {
    schema_version: $schema_version,
    run_id: $run_id,
    mechanism: "traditional-staging",
    candidate_id: $candidate_id,
    mode: $mode,
    repetition: $repetition,
    decision: $decision,
    rationale: $reasons,
    timing: {deployment_started_at: $deployment_started_at, ready_at: $ready_at, measurement_started_at: $measurement_started_at, measurement_ended_at: $measurement_ended_at},
    observed: {samples: $samples, successes: $successes, failures: $failures, success_rate: $success_rate, latency_ms: {p50: $p50,p95:$p95,p99:$p99},checkout:{tests:$checkout_tests,successes:$checkout_successes,failures:$checkout_failures,latency_p95_ms:$checkout_p95,latency_p99_ms:$checkout_p99,negative_paths:{tests:$negative_tests,successes:$negative_successes,failures:$negative_failures,assertions:["unsupported card rejected","expired card rejected","no order confirmation","cart retained"]},unavailable:$checkout_unavailable,restart_increase:$checkout_restart_increase},context:{unavailable_deployments:$unavailable,restart_increase:$restart_increase},locust:{requests:$locust_requests,failures:$locust_failures,success_rate:$locust_success_rate}},
    controls: {operational_snapshot_access: false, workload_profile: "fixed-round-robin-v1-plus-fixed-locust-10-users-rate-1", thresholds: "safety-thresholds.json"},
    artifact_binding: $artifact_binding[0],
    git_commit: $git_commit
  }' > "${run_dir}/decision.json"

observability_dir=$(PROJECT_ID="$(gcloud config get-value project 2>/dev/null)" \
  ENVIRONMENT=staging NAMESPACE="$namespace" SCENARIO_ID=traditional-staging \
  CANDIDATE_ID="$candidate_id" ALTERNATIVE_ID=fixed REPETITION="$repetition" \
  START_TIME="$measurement_started_at" END_TIME="$measurement_ended_at" \
  "${repo_root}/experiment/scripts/export-observability-window.sh")
printf '%s\n' "${observability_dir#"${repo_root}"/}" > "${run_dir}/observability-evidence.txt"
python3 "${repo_root}/experiment/scripts/summarize-checkout-observability.py" \
  --metrics-csv "${observability_dir}/metrics.csv" --output "${run_dir}/checkoutservice-resources.json"
jq --slurpfile resources "${run_dir}/checkoutservice-resources.json" \
  '.observed.checkoutservice_resources = $resources[0]' "${run_dir}/decision.json" > "${run_dir}/decision.tmp.json"
mv "${run_dir}/decision.tmp.json" "${run_dir}/decision.json"

trap - ERR
write_status completed
cleanup
printf '%s\n' "$run_dir"
