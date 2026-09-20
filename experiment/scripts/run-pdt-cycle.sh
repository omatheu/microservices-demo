#!/usr/bin/env bash

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
candidate_file=${CANDIDATE_FILE:-${repo_root}/experiment/pdt/candidates/current.json}
conventional_decision_file=${CONVENTIONAL_DECISION:-}
mode=${MODE:-engineering}
snapshot_file=${SNAPSHOT_FILE:-$(find "${repo_root}/experiment/evidence/pdt-state" -mindepth 2 -maxdepth 2 -name pdt-input-state.json -print | sort | tail -1)}
thresholds_file=${THRESHOLDS_FILE:-${repo_root}/experiment/staging/safety-thresholds.json}
model_policy_file=${MODEL_POLICY_FILE:-${repo_root}/experiment/pdt/model-policy.json}
pdt_overlay=${PDT_OVERLAY:-${repo_root}/infra/kustomize/pdt}
namespace=${NAMESPACE:-pdt}
repetition=${REPETITION:-1}
warmup_seconds=${WARMUP_SECONDS:-$(jq -r '.workload.warmup_seconds' "$thresholds_file")}
sample_count=${SAMPLE_COUNT:-$(jq -r '.workload.sample_count' "$thresholds_file")}
sample_interval=${SAMPLE_INTERVAL_SECONDS:-$(jq -r '.workload.sample_interval_seconds' "$thresholds_file")}
local_port=${LOCAL_PORT:-18081}
candidate_id=$(jq -r '.candidate_id' "$candidate_file")
candidate_definition_sha256=$(sha256sum "$candidate_file" | cut -d ' ' -f1)
cycle_timestamp=$(date -u +%Y%m%dT%H%M%SZ)
cycle_id="pdt-${candidate_id}-r${repetition}-${cycle_timestamp}"
cycle_dir="${repo_root}/experiment/evidence/pdt-cycles/${cycle_id}"
port_forward_pid=""

require_command() {
  command -v "$1" >/dev/null 2>&1 || { echo "Required command not found: $1" >&2; exit 1; }
}
for command_name in awk base64 curl gcloud git jq kubectl python3 sha256sum sort; do require_command "$command_name"; done
[[ -n "$snapshot_file" && -f "$snapshot_file" ]] || { echo "No PDT input snapshot found." >&2; exit 1; }
[[ "$mode" == "engineering" || "$mode" == "confirmatory" ]] || { echo "MODE must be engineering or confirmatory." >&2; exit 1; }
[[ -n "$conventional_decision_file" && -f "$conventional_decision_file" ]] || { echo "CONVENTIONAL_DECISION must point to the sealed control decision." >&2; exit 1; }
if ! jq -e --arg candidate "$candidate_id" '
  .mechanism == "conventional-ci-cd-with-staging"
  and .candidate_id == $candidate
  and .decision == "approve"
  and .control_decision_sealed == true
  and .staging.artifact_binding_verified == true
  and (.immutable_artifacts | type == "array")
' "$conventional_decision_file" >/dev/null; then
  echo "The PDT requires an approved, sealed conventional decision for the same candidate and artifacts." >&2
  exit 1
fi
if [[ "$mode" == "confirmatory" ]] && ! jq -e '.confirmatory_eligibility == true' "$candidate_file" >/dev/null; then
  echo "Confirmatory PDT requires a confirmatory-eligible candidate definition." >&2
  exit 1
fi
control_candidate_definition_sha256=$(jq -r '.candidate_definition_sha256 // empty' "$conventional_decision_file")
if [[ -n "$control_candidate_definition_sha256" && "$candidate_definition_sha256" != "$control_candidate_definition_sha256" ]]; then
  echo "PDT candidate definition differs from the definition sealed by staging." >&2
  exit 1
fi
if [[ -z "$control_candidate_definition_sha256" ]]; then
  echo "PDT requires a candidate definition hash sealed by staging." >&2
  exit 1
fi
[[ "$warmup_seconds" =~ ^[0-9]+$ && "$sample_count" =~ ^[1-9][0-9]*$ ]] || { echo "Invalid sampling parameters." >&2; exit 1; }
[[ "$repetition" =~ ^[1-9][0-9]*$ ]] || { echo "REPETITION must be a positive integer." >&2; exit 1; }

mkdir -p "${cycle_dir}/alternatives"
cp "$candidate_file" "${cycle_dir}/candidate.json"
cp "$conventional_decision_file" "${cycle_dir}/conventional-decision.json"
cp "$snapshot_file" "${cycle_dir}/pdt-input-state.json"
cp "$thresholds_file" "${cycle_dir}/safety-thresholds.json"
cp "$model_policy_file" "${cycle_dir}/model-policy.json"

python3 "${repo_root}/experiment/pdt/controller/checkout_pdt_controller.py" plan \
  --candidate "${cycle_dir}/candidate.json" \
  --conventional-decision "${cycle_dir}/conventional-decision.json" \
  --snapshot "${cycle_dir}/pdt-input-state.json" \
  --thresholds "${cycle_dir}/safety-thresholds.json" \
  --model-policy "${cycle_dir}/model-policy.json" \
  --repetition "$repetition" \
  --output "${cycle_dir}/controller-plan.json"
jq -e '
  .controller_id == "checkout-pdt-controller-v1"
  and .source_binding.target_namespace == "pdt"
  and .execution.operational_mutation_allowed == false
  and .decision_contract.human_confirmation_required == true
' "${cycle_dir}/controller-plan.json" >/dev/null

write_status() {
  jq -n --arg cycle_id "$cycle_id" --arg state "$1" --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{cycle_id: $cycle_id, state: $state, updated_at: $timestamp}' > "${cycle_dir}/status.json"
}

stop_port_forward() {
  if [[ -n "$port_forward_pid" ]] && kill -0 "$port_forward_pid" 2>/dev/null; then
    kill "$port_forward_pid" 2>/dev/null || true
    wait "$port_forward_pid" 2>/dev/null || true
  fi
  port_forward_pid=""
}

cleanup_pdt() {
  stop_port_forward
  kubectl delete deployment loadgenerator --namespace "$namespace" --ignore-not-found --wait=true --timeout=5m >/dev/null 2>&1 || true
  kubectl delete -k "$pdt_overlay" --ignore-not-found --wait=true --timeout=10m >/dev/null 2>&1 || true
}

on_error() {
  write_status failed
  cleanup_pdt
}

write_status running
trap on_error ERR
cleanup_pdt

while IFS= read -r alternative; do
  alternative_id=$(jq -r '.id' <<< "$alternative")
  action=$(jq -r '.action' <<< "$alternative")
  alternative_dir="${cycle_dir}/alternatives/${alternative_id}"
  mkdir -p "$alternative_dir"
  jq . <<< "$alternative" > "${alternative_dir}/definition.json"

  if [[ "$action" == "block" ]]; then
    jq -n --arg alternative_id "$alternative_id" '{alternative_id: $alternative_id, action: "block", executed: true, observed: null}' > "${alternative_dir}/summary.json"
    continue
  fi

  kubectl kustomize "$pdt_overlay" > "${alternative_dir}/rendered-base.yaml"
  kubectl apply -k "$pdt_overlay" > "${alternative_dir}/apply.log"

  while IFS= read -r workload_encoded; do
    workload=$(base64 --decode <<< "$workload_encoded")
    deployment=$(jq -r '.name' <<< "$workload")
    patch=$(jq -c '{spec: {replicas: .replicas, template: {spec: {containers: [.containers[] | {name, image, env, resources}]}}}}' <<< "$workload")
    kubectl patch deployment "$deployment" --namespace "$namespace" --type strategic --patch "$patch" >/dev/null
  done < <(jq -r '.synchronized_state.workloads[] | select(.name != "loadgenerator") | @base64' "$snapshot_file")

  while IFS= read -r change_encoded; do
    change=$(base64 --decode <<< "$change_encoded")
    deployment=$(jq -r '.deployment' <<< "$change")
    patch=$(jq -c '.patch' <<< "$change")
    kubectl patch deployment "$deployment" --namespace "$namespace" --type strategic --patch "$patch" >/dev/null
  done < <(jq -r '.configuration_changes[] | @base64' <<< "$alternative")

  # Apply the sealed candidate image last so neither synchronized state nor an
  # alternative configuration can replace the artifact approved by staging.
  while IFS= read -r artifact_encoded; do
    artifact=$(base64 --decode <<< "$artifact_encoded")
    deployment=$(jq -r '.component' <<< "$artifact")
    immutable_image=$(jq -r '.remote_reference' <<< "$artifact")
    container_name=$(jq -er --arg deployment "$deployment" \
      '.synchronized_state.workloads[] | select(.name == $deployment) | .containers[0].name' \
      "$snapshot_file")
    image_patch=$(jq -n --arg container "$container_name" --arg image "$immutable_image" \
      '{spec: {template: {spec: {containers: [{name: $container, image: $image}]}}}}')
    kubectl patch deployment "$deployment" --namespace "$namespace" \
      --type strategic --patch "$image_patch" >/dev/null
  done < <(jq -r '.immutable_artifacts[] | @base64' "$conventional_decision_file")

  mapfile -t deployments < <(kubectl get deployments --namespace "$namespace" -o json | jq -r '.items[].metadata.name' | sort)
  for deployment in "${deployments[@]}"; do
    kubectl rollout status "deployment/${deployment}" --namespace "$namespace" --timeout=12m
  done > "${alternative_dir}/rollout.log"

  jq -n --arg namespace "$namespace" --slurpfile snapshot "$snapshot_file" '
    ($snapshot[0].synchronized_state.workloads[] | select(.name == "loadgenerator")) as $load |
    {
      apiVersion: "apps/v1", kind: "Deployment",
      metadata: {name: "loadgenerator", namespace: $namespace, labels: {app: "loadgenerator"}},
      spec: {
        replicas: $load.replicas,
        selector: {matchLabels: {app: "loadgenerator"}},
        template: {
          metadata: {labels: {app: "loadgenerator"}},
          spec: {
            serviceAccountName: "loadgenerator",
            terminationGracePeriodSeconds: 5,
            securityContext: {fsGroup: 1000, runAsGroup: 1000, runAsNonRoot: true, runAsUser: 1000},
            containers: [$load.containers[] | {name, image, env, resources, securityContext: {allowPrivilegeEscalation: false, capabilities: {drop: ["ALL"]}, privileged: false, readOnlyRootFilesystem: true}}]
          }
        }
      }
    }' > "${alternative_dir}/loadgenerator.json"
  kubectl apply -f "${alternative_dir}/loadgenerator.json" >/dev/null
  kubectl rollout status deployment/loadgenerator --namespace "$namespace" --timeout=8m >> "${alternative_dir}/rollout.log"

  kubectl port-forward --namespace "$namespace" service/frontend "${local_port}:80" > "${alternative_dir}/port-forward.log" 2>&1 &
  port_forward_pid=$!
  for _ in $(seq 1 60); do
    if curl -fsS --max-time 2 "http://127.0.0.1:${local_port}/" >/dev/null 2>&1; then break; fi
    sleep 1
  done
  curl -fsS --max-time 5 "http://127.0.0.1:${local_port}/" >/dev/null

  if (( warmup_seconds > 0 )); then sleep "$warmup_seconds"; fi
  kubectl get deployments --namespace "$namespace" -o json > "${alternative_dir}/deployments-start.json"
  kubectl get pods --namespace "$namespace" -o json > "${alternative_dir}/pods-start.json"
  restart_start=$(jq '[.items[].status.containerStatuses[]?.restartCount] | add // 0' "${alternative_dir}/pods-start.json")
  checkout_restart_start=$(jq '[.items[] | select(.metadata.labels.app == "checkoutservice") | .status.containerStatuses[]?.restartCount] | add // 0' "${alternative_dir}/pods-start.json")
  locust_start=$(kubectl logs deployment/loadgenerator --namespace "$namespace" --container main | awk '/Aggregated/{line=$0} END{print line}')
  printf '%s\n' "$locust_start" > "${alternative_dir}/locust-start.txt"

  measurement_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  printf 'sequence,timestamp_utc,test_id,method,path,http_status,latency_ms,success\n' > "${alternative_dir}/http-samples.csv"
  paths=("/" "/product/0PUK6V6EV0" "/cart" "/setCurrency")
  methods=("GET" "GET" "GET" "POST")
  for sequence in $(seq 1 "$sample_count"); do
    profile_index=$(((sequence - 1) % 4)); path=${paths[$profile_index]}; method=${methods[$profile_index]}
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    if [[ "$method" == "POST" ]]; then
      curl_result=$(curl --silent --show-error --output /dev/null --max-time 15 --request POST --data 'currency_code=USD' --write-out '%{http_code},%{time_total}' "http://127.0.0.1:${local_port}${path}" || printf '000,15.000000')
    else
      curl_result=$(curl --silent --show-error --output /dev/null --max-time 15 --write-out '%{http_code},%{time_total}' "http://127.0.0.1:${local_port}${path}" || printf '000,15.000000')
    fi
    http_status=${curl_result%%,*}; latency_seconds=${curl_result#*,}
    latency_ms=$(awk -v seconds="$latency_seconds" 'BEGIN {printf "%.3f", seconds * 1000}')
    if [[ "$http_status" =~ ^(2|3)[0-9][0-9]$ ]]; then success=true; else success=false; fi
    printf '%s,%s,%s,%s,%s,%s,%s,%s\n' "$sequence" "$timestamp" "profile-$profile_index" "$method" "$path" "$http_status" "$latency_ms" "$success" >> "${alternative_dir}/http-samples.csv"
    if (( sequence < sample_count )); then sleep "$sample_interval"; fi
  done
  checkout_test_count=10
  printf 'sequence,timestamp_utc,http_status,latency_ms,confirmation_marker,success\n' > "${alternative_dir}/checkout-tests.csv"
  expiration_year=$((10#$(date -u +%Y) + 1))
  for checkout_sequence in $(seq 1 "$checkout_test_count"); do
    cookie_file="${alternative_dir}/checkout-cookie-${checkout_sequence}.txt"
    response_file="${alternative_dir}/checkout-response-${checkout_sequence}.html"
    curl -fsS --max-time 15 --cookie-jar "$cookie_file" --cookie "$cookie_file" \
      "http://127.0.0.1:${local_port}/product/0PUK6V6EV0" >/dev/null || true
    curl -fsS --max-time 15 --cookie-jar "$cookie_file" --cookie "$cookie_file" \
      --request POST --data 'product_id=0PUK6V6EV0&quantity=1' \
      "http://127.0.0.1:${local_port}/cart" >/dev/null || true
    checkout_timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    if checkout_result=$(curl --silent --show-error --output "$response_file" --max-time 30 \
      --cookie-jar "$cookie_file" --cookie "$cookie_file" --request POST \
      --data-urlencode 'email=twin@example.com' \
      --data-urlencode 'street_address=1600 Amphitheatre Parkway' \
      --data-urlencode 'zip_code=94043' --data-urlencode 'city=Mountain View' \
      --data-urlencode 'state=CA' --data-urlencode 'country=United States' \
      --data-urlencode 'credit_card_number=4432801561520454' \
      --data-urlencode 'credit_card_expiration_month=12' \
      --data-urlencode "credit_card_expiration_year=${expiration_year}" \
      --data-urlencode 'credit_card_cvv=672' \
      --write-out '%{http_code},%{time_total}' "http://127.0.0.1:${local_port}/cart/checkout"); then
      :
    else
      checkout_result='000,30.000000'
    fi
    checkout_status=${checkout_result%%,*}; checkout_latency_seconds=${checkout_result#*,}
    checkout_latency_ms=$(awk -v seconds="$checkout_latency_seconds" 'BEGIN {printf "%.3f", seconds * 1000}')
    if grep -q 'Your order is complete!' "$response_file"; then confirmation_marker=true; else confirmation_marker=false; fi
    if [[ "$checkout_status" =~ ^2[0-9][0-9]$ && "$confirmation_marker" == "true" ]]; then checkout_success=true; else checkout_success=false; fi
    printf '%s,%s,%s,%s,%s,%s\n' "$checkout_sequence" "$checkout_timestamp" "$checkout_status" "$checkout_latency_ms" "$confirmation_marker" "$checkout_success" >> "${alternative_dir}/checkout-tests.csv"
  done
  checkout_successes=$(awk -F, 'NR > 1 && $6 == "true" {n++} END {print n + 0}' "${alternative_dir}/checkout-tests.csv")
  checkout_failures=$((checkout_test_count - checkout_successes))
  awk -F, 'NR > 1 {print $4}' "${alternative_dir}/checkout-tests.csv" | sort -n > "${alternative_dir}/checkout-latencies-sorted.txt"
  checkout_p95=$(awk '{v[NR]=$1} END {r=int(0.95*NR+0.999999);if(r<1)r=1;if(r>NR)r=NR;printf "%.3f",v[r]}' "${alternative_dir}/checkout-latencies-sorted.txt")
  checkout_p99=$(awk '{v[NR]=$1} END {r=int(0.99*NR+0.999999);if(r<1)r=1;if(r>NR)r=NR;printf "%.3f",v[r]}' "${alternative_dir}/checkout-latencies-sorted.txt")

  negative_test_count=2
  negative_test_ids=("unsupported-card" "expired-card")
  negative_card_numbers=("378282246310005" "4432801561520454")
  negative_expiration_years=("$expiration_year" "$((10#$(date -u +%Y) - 1))")
  printf 'test_id,http_status,confirmation_absent,cart_retained,success\n' > "${alternative_dir}/checkout-negative-tests.csv"
  for negative_index in 0 1; do
    negative_test_id=${negative_test_ids[$negative_index]}
    negative_card=${negative_card_numbers[$negative_index]}
    negative_year=${negative_expiration_years[$negative_index]}
    negative_cookie_file="${alternative_dir}/negative-${negative_test_id}-cookie.txt"
    negative_response_file="${alternative_dir}/negative-${negative_test_id}-response.html"
    negative_cart_file="${alternative_dir}/negative-${negative_test_id}-cart.html"

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
    printf '%s,%s,%s,%s,%s\n' "$negative_test_id" "$negative_result" "$confirmation_absent" "$cart_retained" "$negative_success" >> "${alternative_dir}/checkout-negative-tests.csv"
  done
  negative_successes=$(awk -F, 'NR > 1 && $5 == "true" {n++} END {print n + 0}' "${alternative_dir}/checkout-negative-tests.csv")
  negative_failures=$((negative_test_count - negative_successes))
  measurement_ended_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  kubectl get deployments --namespace "$namespace" -o json > "${alternative_dir}/deployments-end.json"
  kubectl get pods --namespace "$namespace" -o json > "${alternative_dir}/pods-end.json"
  kubectl get events --namespace "$namespace" -o json > "${alternative_dir}/events.json"
  restart_end=$(jq '[.items[].status.containerStatuses[]?.restartCount] | add // 0' "${alternative_dir}/pods-end.json")
  restart_increase=$((restart_end - restart_start))
  checkout_restart_end=$(jq '[.items[] | select(.metadata.labels.app == "checkoutservice") | .status.containerStatuses[]?.restartCount] | add // 0' "${alternative_dir}/pods-end.json")
  checkout_restart_increase=$((checkout_restart_end - checkout_restart_start))
  unavailable=$(jq '[.items[] | select((.status.availableReplicas // 0) != (.spec.replicas // 0))] | length' "${alternative_dir}/deployments-end.json")
  checkout_unavailable=$(jq '[.items[] | select(.metadata.name == "checkoutservice") | select((.status.availableReplicas // 0) != (.spec.replicas // 0))] | length' "${alternative_dir}/deployments-end.json")
  successes=$(awk -F, 'NR > 1 && $8 == "true" {n++} END {print n + 0}' "${alternative_dir}/http-samples.csv")
  failures=$((sample_count - successes)); success_rate=$(awk -v a="$successes" -v b="$sample_count" 'BEGIN {printf "%.6f",a/b}')
  awk -F, 'NR > 1 {print $7}' "${alternative_dir}/http-samples.csv" | sort -n > "${alternative_dir}/latencies-sorted.txt"
  percentile() { awk -v p="$1" '{v[NR]=$1} END {r=int(p*NR+0.999999);if(r<1)r=1;if(r>NR)r=NR;printf "%.3f",v[r]}' "${alternative_dir}/latencies-sorted.txt"; }
  p50=$(percentile 0.50); p95=$(percentile 0.95); p99=$(percentile 0.99)
  locust_end=$(kubectl logs deployment/loadgenerator --namespace "$namespace" --container main | awk '/Aggregated/{line=$0} END{print line}')
  printf '%s\n' "$locust_end" > "${alternative_dir}/locust-end.txt"
  locust_start_requests=$(awk '{print $2 + 0}' <<< "$locust_start"); locust_end_requests=$(awk '{print $2 + 0}' <<< "$locust_end")
  locust_start_failures=$(awk '{v=$3;sub(/\(.*/,"",v);print v+0}' <<< "$locust_start"); locust_end_failures=$(awk '{v=$3;sub(/\(.*/,"",v);print v+0}' <<< "$locust_end")
  locust_requests=$((locust_end_requests-locust_start_requests))
  locust_failures=$((locust_end_failures-locust_start_failures))
  if (( locust_requests > 0 )); then
    locust_success_rate=$(awk -v requests="$locust_requests" -v failures="$locust_failures" 'BEGIN {printf "%.6f", (requests-failures)/requests}')
  else
    locust_success_rate=0
  fi

  jq -n --arg alternative_id "$alternative_id" --arg action "$action" \
    --arg started_at "$measurement_started_at" --arg ended_at "$measurement_ended_at" \
    --argjson samples "$sample_count" --argjson successes "$successes" --argjson failures "$failures" \
    --argjson success_rate "$success_rate" --argjson p50 "$p50" --argjson p95 "$p95" --argjson p99 "$p99" \
    --argjson unavailable "$unavailable" --argjson restart_increase "$restart_increase" \
    --argjson checkout_unavailable "$checkout_unavailable" --argjson checkout_restart_increase "$checkout_restart_increase" \
    --argjson checkout_tests "$checkout_test_count" --argjson checkout_successes "$checkout_successes" \
    --argjson checkout_failures "$checkout_failures" --argjson checkout_p95 "$checkout_p95" \
    --argjson checkout_p99 "$checkout_p99" --argjson negative_tests "$negative_test_count" \
    --argjson negative_successes "$negative_successes" --argjson negative_failures "$negative_failures" \
    --argjson locust_requests "$locust_requests" --argjson locust_failures "$locust_failures" \
    --argjson locust_success_rate "$locust_success_rate" '
    {alternative_id:$alternative_id,action:$action,executed:true,window:{started_at:$started_at,ended_at:$ended_at},observed:{samples:$samples,successes:$successes,failures:$failures,success_rate:$success_rate,latency_ms:{p50:$p50,p95:$p95,p99:$p99},checkout:{tests:$checkout_tests,successes:$checkout_successes,failures:$checkout_failures,latency_p95_ms:$checkout_p95,latency_p99_ms:$checkout_p99,confirmation_marker:"Your order is complete!",negative_paths:{tests:$negative_tests,successes:$negative_successes,failures:$negative_failures,assertions:["unsupported card rejected","expired card rejected","no order confirmation","cart retained"]},unavailable:$checkout_unavailable,restart_increase:$checkout_restart_increase},context:{unavailable_deployments:$unavailable,restart_increase:$restart_increase},locust:{requests:$locust_requests,failures:$locust_failures,success_rate:$locust_success_rate}}}' > "${alternative_dir}/summary.json"

  observability_dir=$(PROJECT_ID="$(jq -r '.binding.project_id' "$snapshot_file")" ENVIRONMENT=pdt NAMESPACE="$namespace" \
    SCENARIO_ID=pdt-cycle CANDIDATE_ID="$candidate_id" ALTERNATIVE_ID="$alternative_id" REPETITION="$repetition" \
    START_TIME="$measurement_started_at" END_TIME="$measurement_ended_at" \
    "${repo_root}/experiment/scripts/export-observability-window.sh")
  printf '%s\n' "${observability_dir#"${repo_root}"/}" > "${alternative_dir}/observability-evidence.txt"
  python3 "${repo_root}/experiment/scripts/summarize-checkout-observability.py" \
    --metrics-csv "${observability_dir}/metrics.csv" --output "${alternative_dir}/checkoutservice-resources.json"
  jq --slurpfile resources "${alternative_dir}/checkoutservice-resources.json" \
    '.observed.checkoutservice_resources = $resources[0]' "${alternative_dir}/summary.json" > "${alternative_dir}/summary.tmp.json"
  mv "${alternative_dir}/summary.tmp.json" "${alternative_dir}/summary.json"
  cleanup_pdt
done < <(jq -c '.alternatives[]' "$candidate_file")

python3 "${repo_root}/experiment/scripts/decide-pdt.py" \
  --candidate "${cycle_dir}/candidate.json" --snapshot "${cycle_dir}/pdt-input-state.json" \
  --repetition "$repetition" \
  --thresholds "${cycle_dir}/safety-thresholds.json" --model-policy "${cycle_dir}/model-policy.json" \
  --alternatives-dir "${cycle_dir}/alternatives" --output "${cycle_dir}/decision.json"

conventional_decision_sha256=$(sha256sum "$conventional_decision_file" | cut -d ' ' -f1)
jq --arg mode "$mode" --arg control_sha256 "$conventional_decision_sha256" \
  --arg candidate_definition_sha256 "$candidate_definition_sha256" \
  --slurpfile control "${cycle_dir}/conventional-decision.json" '
  . + {
    execution_mode: $mode,
    artifact_binding: {
      conventional_decision_sha256: $control_sha256,
      candidate_definition_sha256: $candidate_definition_sha256,
      staging_binding_verified: $control[0].staging.artifact_binding_verified,
      immutable_artifacts: $control[0].immutable_artifacts
    }
  }' "${cycle_dir}/decision.json" > "${cycle_dir}/decision.tmp.json"
mv "${cycle_dir}/decision.tmp.json" "${cycle_dir}/decision.json"

trap - ERR
write_status completed
cleanup_pdt
printf '%s\n' "$cycle_dir"
