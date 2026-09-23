#!/usr/bin/env bash

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
POLICY_FILE="${REPO_ROOT}/experiment/ci/policy.json"
COMPONENT_MATRIX="${REPO_ROOT}/experiment/ci/components.json"
MODE="${MODE:-engineering}"
CANDIDATE_ID="${CANDIDATE_ID:-working-tree}"
CANDIDATE_BASE_REF="${CANDIDATE_BASE_REF:-}"
CANDIDATE_HEAD_REF="${CANDIDATE_HEAD_REF:-HEAD}"
CANDIDATE_CHANGED_FILES_FILE="${CANDIDATE_CHANGED_FILES_FILE:-}"
PUBLISH_ARTIFACTS="${PUBLISH_ARTIFACTS:-false}"
ARTIFACT_REGISTRY_PREFIX="${ARTIFACT_REGISTRY_PREFIX:-}"

case "${MODE}" in
  engineering|confirmatory) ;;
  *)
    echo "MODE must be engineering or confirmatory" >&2
    exit 2
    ;;
esac

if [[ "${PUBLISH_ARTIFACTS}" != "true" && "${PUBLISH_ARTIFACTS}" != "false" ]]; then
  echo "PUBLISH_ARTIFACTS must be true or false" >&2
  exit 2
fi
if [[ -n "${ARTIFACT_REGISTRY_PREFIX}" && ! "${ARTIFACT_REGISTRY_PREFIX}" =~ ^[a-z0-9.-]+/[a-z0-9._-]+/[a-z0-9._-]+$ ]]; then
  echo "ARTIFACT_REGISTRY_PREFIX must look like LOCATION-docker.pkg.dev/PROJECT/REPOSITORY" >&2
  exit 2
fi
if [[ "${PUBLISH_ARTIFACTS}" == "true" && -z "${ARTIFACT_REGISTRY_PREFIX}" ]]; then
  echo "ARTIFACT_REGISTRY_PREFIX is required when PUBLISH_ARTIFACTS=true" >&2
  exit 2
fi

if [[ ! "${CANDIDATE_ID}" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "CANDIDATE_ID may contain only letters, digits, dots, underscores and hyphens" >&2
  exit 2
fi

for tool in git jq docker kubectl terraform shellcheck python3 protoc sha256sum; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Required local tool is missing: ${tool}" >&2
    exit 2
  fi
done

if [[ ! -f "${POLICY_FILE}" || ! -f "${COMPONENT_MATRIX}" ]]; then
  echo "Missing CI policy or component matrix." >&2
  exit 2
fi

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ID="ci-${CANDIDATE_ID}-${TIMESTAMP}"
OUTPUT_DIR="${REPO_ROOT}/experiment/evidence/ci-cd/${RUN_ID}"
LOG_DIR="${OUTPUT_DIR}/logs"
GATES_NDJSON="${OUTPUT_DIR}/.gates.ndjson"
COMPONENT_SELECTION_FILE="${OUTPUT_DIR}/component-selection.json"
ARTIFACTS_NDJSON="${OUTPUT_DIR}/.artifacts.ndjson"
ARTIFACTS_FILE="${OUTPUT_DIR}/artifacts.json"
PROTOBUF_CONTRACTS_FILE="${OUTPUT_DIR}/protobuf-contracts.json"
KUBERNETES_RENDER_DIR="${OUTPUT_DIR}/kubernetes-rendered"
KUBERNETES_POLICY_REPORT="${OUTPUT_DIR}/kubernetes-policy.json"

GIT_COMMIT="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || printf 'unavailable')"
GIT_TREE_SHA="$(git -C "${REPO_ROOT}" rev-parse 'HEAD^{tree}' 2>/dev/null || printf 'unavailable')"
GIT_HEAD_REF_COMMIT="$(git -C "${REPO_ROOT}" rev-parse "${CANDIDATE_HEAD_REF}^{commit}" 2>/dev/null || printf 'unavailable')"
GIT_BASE_COMMIT="unavailable"
if [[ -n "${CANDIDATE_BASE_REF}" ]]; then
  GIT_BASE_COMMIT="$(git -C "${REPO_ROOT}" rev-parse "${CANDIDATE_BASE_REF}^{commit}" 2>/dev/null || printf 'unavailable')"
fi
GIT_TREE="$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=all 2>/dev/null || true)"
GIT_DIRTY=false
if [[ -n "${GIT_TREE}" ]]; then
  GIT_DIRTY=true
fi

mkdir -p "${LOG_DIR}" "${KUBERNETES_RENDER_DIR}"
: >"${GATES_NDJSON}"

GO_IMAGE="$(jq -er '.container_images.golang' "${POLICY_FILE}")"
NODE_IMAGE="$(jq -er '.container_images.node' "${POLICY_FILE}")"
DOTNET_SDK_IMAGE="$(jq -er '.container_images.dotnet_sdk' "${POLICY_FILE}")"
GITLEAKS_IMAGE="$(jq -er '.container_images.gitleaks' "${POLICY_FILE}")"
SEMGREP_IMAGE="$(jq -er '.container_images.semgrep' "${POLICY_FILE}")"
TRIVY_IMAGE="$(jq -er '.container_images.trivy' "${POLICY_FILE}")"
SYFT_IMAGE="$(jq -er '.container_images.syft' "${POLICY_FILE}")"
SEMGREP_RULESET="$(jq -er '.scanner_policy.semgrep_ruleset' "${POLICY_FILE}")"
PROTOC_VERSION="$(jq -er '.tool_versions.protoc' "${POLICY_FILE}")"
PYYAML_VERSION="$(jq -er '.tool_versions.pyyaml' "${POLICY_FILE}")"
PROTOBUF_PYTHON_VERSION="$(jq -er '.tool_versions.protobuf_python' "${POLICY_FILE}")"

jq -n \
  --arg schema_version "1.0.0" \
  --arg run_id "${RUN_ID}" \
  --arg candidate_id "${CANDIDATE_ID}" \
  --arg mode "${MODE}" \
  --arg started_at "${STARTED_AT}" \
  --arg git_commit "${GIT_COMMIT}" \
  --argjson git_dirty "${GIT_DIRTY}" \
  --argjson artifact_publication_requested "${PUBLISH_ARTIFACTS}" \
  '{
    schema_version: $schema_version,
    run_id: $run_id,
    candidate_id: $candidate_id,
    mode: $mode,
    started_at: $started_at,
    git: {commit: $git_commit, dirty: $git_dirty},
    artifact_scope: "affected-service-images",
    artifact_publication_requested: $artifact_publication_requested,
    scope: "local-pre-staging-ci",
    cloud_resources_created: false
  }' >"${OUTPUT_DIR}/metadata.json"

cleanup() {
  rm -f -- "${GATES_NDJSON}" "${ARTIFACTS_NDJSON}"
  if [[ -n "${ACTIVE_REMOTE_TAG:-}" ]]; then
    docker image rm "${ACTIVE_REMOTE_TAG}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${ACTIVE_IMAGE_TAG:-}" ]]; then
    docker image rm "${ACTIVE_IMAGE_TAG}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

run_gate() {
  local gate_id="$1"
  local description="$2"
  local required="$3"
  shift 3

  local log_file="${LOG_DIR}/${gate_id}.log"
  local gate_started gate_finished start_epoch finish_epoch duration exit_code status
  gate_started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  start_epoch="$(date +%s)"

  "$@" >"${log_file}" 2>&1
  exit_code=$?

  finish_epoch="$(date +%s)"
  gate_finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  duration=$((finish_epoch - start_epoch))
  status="pass"
  if [[ ${exit_code} -ne 0 ]]; then
    status="fail"
  fi

  jq -cn \
    --arg id "${gate_id}" \
    --arg description "${description}" \
    --arg status "${status}" \
    --arg started_at "${gate_started}" \
    --arg finished_at "${gate_finished}" \
    --arg log "logs/${gate_id}.log" \
    --argjson required "${required}" \
    --argjson exit_code "${exit_code}" \
    --argjson duration_seconds "${duration}" \
    '{
      id: $id,
      description: $description,
      required: $required,
      status: $status,
      exit_code: $exit_code,
      duration_seconds: $duration_seconds,
      started_at: $started_at,
      finished_at: $finished_at,
      log: $log
    }' >>"${GATES_NDJSON}"

  printf '%-30s %s\n' "${gate_id}" "${status}"
  return 0
}

gate_candidate_identity() {
  echo "candidate_id=${CANDIDATE_ID}"
  echo "git_commit=${GIT_COMMIT}"
  echo "git_tree=${GIT_TREE_SHA}"
  echo "candidate_head_commit=${GIT_HEAD_REF_COMMIT}"
  echo "candidate_base_commit=${GIT_BASE_COMMIT}"
  echo "git_dirty=${GIT_DIRTY}"
  echo "candidate_base_ref=${CANDIDATE_BASE_REF:-working-tree}"
  echo "candidate_head_ref=${CANDIDATE_HEAD_REF}"
  echo "candidate_changed_files_file=${CANDIDATE_CHANGED_FILES_FILE:-none}"
  echo "publish_artifacts=${PUBLISH_ARTIFACTS}"
  echo "artifact_registry_prefix=${ARTIFACT_REGISTRY_PREFIX:-none}"

  if [[ "${MODE}" == "confirmatory" ]]; then
    [[ "${CANDIDATE_ID}" != "working-tree" ]]
    [[ "${GIT_COMMIT}" != "unavailable" ]]
    [[ "${GIT_TREE_SHA}" != "unavailable" ]]
    [[ "${GIT_HEAD_REF_COMMIT}" == "${GIT_COMMIT}" ]]
    [[ "${GIT_BASE_COMMIT}" != "unavailable" ]]
    [[ "${GIT_DIRTY}" == "false" ]]
    [[ -n "${CANDIDATE_BASE_REF}" ]]
    [[ -z "${CANDIDATE_CHANGED_FILES_FILE}" ]]
    [[ "${PUBLISH_ARTIFACTS}" == "true" ]]
    [[ -n "${ARTIFACT_REGISTRY_PREFIX}" ]]
  elif [[ "${GIT_DIRTY}" == "true" ]]; then
    echo "Engineering mode: dirty tree accepted for diagnostics only."
  fi
}

gate_component_selection() {
  local -a selection_args
  local selection_exit=0
  selection_args=(
    --repo-root "${REPO_ROOT}"
    --matrix "${COMPONENT_MATRIX}"
    --output "${COMPONENT_SELECTION_FILE}"
  )
  if [[ -n "${CANDIDATE_CHANGED_FILES_FILE}" ]]; then
    [[ "${MODE}" == "engineering" ]]
    [[ -f "${CANDIDATE_CHANGED_FILES_FILE}" ]]
    while IFS= read -r changed_file || [[ -n "${changed_file}" ]]; do
      [[ -n "${changed_file}" ]] || continue
      selection_args+=(--changed-file "${changed_file}")
    done <"${CANDIDATE_CHANGED_FILES_FILE}"
  elif [[ -n "${CANDIDATE_BASE_REF}" ]]; then
    selection_args+=(--base-ref "${CANDIDATE_BASE_REF}" --head-ref "${CANDIDATE_HEAD_REF}")
  fi

  python3 "${REPO_ROOT}/experiment/scripts/select-affected-components.py" \
    "${selection_args[@]}" || selection_exit=$?

  if [[ ! -f "${COMPONENT_SELECTION_FILE}" ]]; then
    jq -n \
      --arg schema_version "1.0.0" \
      --arg reason "component selector failed before producing evidence" \
      '{schema_version: $schema_version, decision: "block", reasons: [$reason]}' \
      >"${COMPONENT_SELECTION_FILE}"
  fi
  jq '.' "${COMPONENT_SELECTION_FILE}"
  [[ ${selection_exit} -eq 0 ]]
  jq -e '.decision == "pass"' "${COMPONENT_SELECTION_FILE}" >/dev/null
}

gate_policy_readiness() {
  jq empty "${POLICY_FILE}"
  local policy_status rules_frozen rules_hash_expected rules_hash_actual pyyaml_actual protobuf_python_actual
  policy_status="$(jq -r '.status' "${POLICY_FILE}")"
  rules_frozen="$(jq -r '.scanner_policy.semgrep_ruleset_frozen' "${POLICY_FILE}")"
  rules_hash_expected="$(jq -r '.scanner_policy.semgrep_ruleset_sha256' "${POLICY_FILE}")"
  [[ -f "${REPO_ROOT}/${SEMGREP_RULESET}" ]]
  rules_hash_actual="$(sha256sum "${REPO_ROOT}/${SEMGREP_RULESET}" | cut -d ' ' -f1)"
  pyyaml_actual="$(python3 -c 'import yaml; print(yaml.__version__)')"
  protobuf_python_actual="$(python3 -c 'import google.protobuf; print(google.protobuf.__version__)')"
  echo "policy_status=${policy_status}"
  echo "semgrep_ruleset_frozen=${rules_frozen}"
  echo "semgrep_ruleset_sha256_expected=${rules_hash_expected}"
  echo "semgrep_ruleset_sha256_actual=${rules_hash_actual}"
  echo "pyyaml_version_expected=${PYYAML_VERSION}"
  echo "pyyaml_version_actual=${pyyaml_actual}"
  echo "protobuf_python_version_expected=${PROTOBUF_PYTHON_VERSION}"
  echo "protobuf_python_version_actual=${protobuf_python_actual}"
  [[ "${rules_hash_actual}" == "${rules_hash_expected}" ]]
  [[ "${pyyaml_actual}" == "${PYYAML_VERSION}" ]]
  [[ "${protobuf_python_actual}" == "${PROTOBUF_PYTHON_VERSION}" ]]

  if [[ "${MODE}" == "confirmatory" ]]; then
    [[ "${policy_status}" == "frozen" ]]
    [[ "${rules_frozen}" == "true" ]]
  fi
}

gate_shellcheck() {
  mapfile -d '' scripts < <(find "${REPO_ROOT}/experiment/scripts" -maxdepth 1 -type f -name '*.sh' -print0 | sort -z)
  [[ ${#scripts[@]} -gt 0 ]]
  shellcheck --severity=warning "${scripts[@]}"
}

gate_python_syntax() {
  python3 - "${REPO_ROOT}" <<'PY'
import ast
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
files = sorted((root / "experiment" / "scripts").glob("*.py"))
if not files:
    raise SystemExit("no Python scripts found")
for path in files:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print(path.relative_to(root))
PY
}

gate_ci_contract_tests() {
  python3 -m unittest discover \
    -s "${REPO_ROOT}/experiment/ci/tests" \
    -p 'test_*.py' \
    -v
}

gate_json_syntax() {
  local count=0
  while IFS= read -r -d '' file; do
    jq empty "${file}"
    count=$((count + 1))
  done < <(find "${REPO_ROOT}/experiment" \
    -path "${REPO_ROOT}/experiment/evidence" -prune -o \
    -type f -name '*.json' -print0 | sort -z)
  echo "validated_json_files=${count}"
  [[ ${count} -gt 0 ]]
}

gate_protobuf_contracts() {
  local -a protobuf_args
  protobuf_args=(
    --repo-root "${REPO_ROOT}"
    --output "${PROTOBUF_CONTRACTS_FILE}"
    --expected-protoc-version "${PROTOC_VERSION}"
  )
  if [[ -n "${CANDIDATE_BASE_REF}" ]]; then
    protobuf_args+=(--base-ref "${CANDIDATE_BASE_REF}")
  fi

  python3 "${REPO_ROOT}/experiment/scripts/validate-protobuf-contracts.py" \
    "${protobuf_args[@]}"
  jq '.' "${PROTOBUF_CONTRACTS_FILE}"
}

gate_terraform_static() {
  local terraform_directory
  for terraform_directory in \
    "${REPO_ROOT}/infra/terraform" \
    "${REPO_ROOT}/infra/terraform-billing-export"; do
    terraform -chdir="${terraform_directory}" fmt -check -recursive -diff
    terraform -chdir="${terraform_directory}" init -backend=false -input=false -no-color
    terraform -chdir="${terraform_directory}" validate -no-color
  done
}

gate_kustomize_render() {
  local count=0 directory relative output
  while IFS= read -r -d '' file; do
    directory="$(dirname "${file}")"
    relative="${directory#"${REPO_ROOT}/"}"
    output="${KUBERNETES_RENDER_DIR}/${relative//\//__}.yaml"
    echo "rendering ${relative} -> ${output#"${OUTPUT_DIR}/"}"
    kubectl kustomize "${directory}" >"${output}"
    count=$((count + 1))
  done < <(find "${REPO_ROOT}/infra/kustomize" "${REPO_ROOT}/kubernetes-manifests" \
    -type f -name 'kustomization.yaml' -print0 | sort -z)
  echo "rendered_kustomizations=${count}"
  [[ ${count} -gt 0 ]]
}

gate_kubernetes_policy_self_test() {
  local validator_exit=0
  python3 "${REPO_ROOT}/experiment/scripts/validate-kubernetes-policy.py" \
    --policy "${POLICY_FILE}" \
    --manifest "${REPO_ROOT}/experiment/ci/fixtures/kubernetes-policy-canary.yaml" \
    --output "${OUTPUT_DIR}/kubernetes-policy-self-test.json" || validator_exit=$?
  echo "expected_exit=1 actual_exit=${validator_exit}"
  [[ ${validator_exit} -eq 1 ]]
  jq -e '
    .decision == "block"
    and ([.violations[] | select(.rule == "container-privileged")] | length == 1)
  ' "${OUTPUT_DIR}/kubernetes-policy-self-test.json" >/dev/null
}

gate_kubernetes_policy() {
  local -a arguments
  arguments=(--policy "${POLICY_FILE}" --output "${KUBERNETES_POLICY_REPORT}")
  while IFS= read -r -d '' manifest; do
    arguments+=(--manifest "${manifest}")
  done < <(find "${KUBERNETES_RENDER_DIR}" -maxdepth 1 -type f -name '*.yaml' -print0 | sort -z)
  (( ${#arguments[@]} > 4 ))
  python3 "${REPO_ROOT}/experiment/scripts/validate-kubernetes-policy.py" "${arguments[@]}"
  jq -e '.decision == "pass" and .violation_count == 0' "${KUBERNETES_POLICY_REPORT}" >/dev/null
}

run_go_test_command() {
  local component="$1"
  shift
  docker run --rm \
    -e HOME=/tmp \
    -e GOCACHE=/tmp/go-build \
    -e GOMODCACHE=/tmp/go-mod \
    -v "${REPO_ROOT}/src/${component}:/workspace:ro" \
    -w /workspace \
    "${GO_IMAGE}" \
    "$@"
}

run_node_tests() {
  local component="$1"
  docker run --rm \
    -e DISABLE_PROFILER=1 \
    -e NPM_CONFIG_CACHE=/tmp/npm-cache \
    -v "${REPO_ROOT}/src/${component}:/source:ro" \
    "${NODE_IMAGE}" \
    sh -euc 'cp -a /source /workspace && cd /workspace && npm ci --ignore-scripts --no-audit --no-fund && npm test'
}

run_dotnet_tests() {
  local component="$1"
  docker run --rm \
    -e DOTNET_CLI_HOME=/tmp/dotnet \
    -e NUGET_PACKAGES=/tmp/nuget \
    -v "${REPO_ROOT}/src/${component}:/source:ro" \
    "${DOTNET_SDK_IMAGE}" \
    sh -euc 'cp -a /source /workspace && cd /workspace && dotnet test --configuration Release --nologo'
}

run_python_service_tests() {
  local component="$1"
  local test_image="online-boutique/${component}-ci-test:${CANDIDATE_ID}-${TIMESTAMP}"
  local test_exit=0

  docker build --pull=false --tag "${test_image}" "${REPO_ROOT}/src/${component}" || return 1
  case "${component}" in
    emailservice)
      docker run --rm \
        --entrypoint python \
        "${test_image}" \
        -m unittest discover -s /email_server -p 'test_*.py' -v || test_exit=$?
      ;;
    recommendationservice)
      docker run --rm \
        --entrypoint python \
        "${test_image}" \
        -m compileall -q /recommendationservice || test_exit=$?
      ;;
    *)
      echo "No Python test command is defined for ${component}." >&2
      test_exit=1
      ;;
  esac
  docker image rm "${test_image}" >/dev/null 2>&1 || true
  return "${test_exit}"
}

gate_checkout_unit_tests() {
  run_go_test_command checkoutservice go test ./...
}

gate_checkout_semantic_contracts() {
  run_go_test_command checkoutservice \
    go test -run '^TestPlaceOrderContract_' -count=1 -v .
}

gate_affected_component_tests() {
  local component profile status
  local selected=0
  while IFS=$'\t' read -r component profile status; do
    [[ -n "${component}" ]] || continue
    selected=$((selected + 1))
    echo "component=${component} profile=${profile} status=${status}"

    case "${profile}" in
      go-checkout)
        echo "${component}: covered by checkout-specific unit and semantic gates"
        ;;
      go-service)
        [[ "${status}" == "implemented" ]]
        run_go_test_command "${component}" go test ./... || return 1
        ;;
      node-service)
        [[ "${status}" == "implemented" ]]
        run_node_tests "${component}" || return 1
        ;;
      dotnet-service)
        [[ "${status}" == "implemented" ]]
        run_dotnet_tests "${component}" || return 1
        ;;
      python-service)
        [[ "${status}" == "implemented" ]]
        run_python_service_tests "${component}" || return 1
        ;;
      *)
        echo "No executable test adapter for ${component} (${profile})." >&2
        return 1
        ;;
    esac
  done < <(
    jq -r '.affected_components[] | select(.kind == "service") |
      [.name, .validation_profile, .validation_status] | @tsv' \
      "${COMPONENT_SELECTION_FILE}"
  )
  echo "selected_service_components=${selected}"
}

gate_secret_scanner_self_test() {
  local scanner_exit canary_prefix canary_suffix
  canary_prefix="AKIA"
  canary_suffix="QWERTYUIOPASDFGH"
  printf 'aws_access_key_id = "%s%s"\n' "${canary_prefix}" "${canary_suffix}" |
    docker run --rm -i "${GITLEAKS_IMAGE}" stdin --no-banner --no-color --redact
  scanner_exit=${PIPESTATUS[1]}
  echo "expected_exit=1 actual_exit=${scanner_exit}"
  [[ ${scanner_exit} -eq 1 ]]
}

gate_secret_scan() {
  docker run --rm \
    -v "${REPO_ROOT}:/repo:ro" \
    "${GITLEAKS_IMAGE}" dir \
    --config /repo/experiment/ci/gitleaks.toml \
    --no-banner \
    --no-color \
    --redact \
    /repo
}

gate_sast_self_test() {
  local scanner_exit=0
  docker run --rm \
    -e SEMGREP_SEND_METRICS=off \
    -v "${REPO_ROOT}:/src:ro" \
    -w /src \
    "${SEMGREP_IMAGE}" semgrep scan \
    --config "${SEMGREP_RULESET}" \
    --metrics=off \
    --no-git-ignore \
    --error \
    experiment/ci/fixtures/semgrep-canary.py || scanner_exit=$?
  echo "expected_exit=1 actual_exit=${scanner_exit}"
  [[ ${scanner_exit} -eq 1 ]]
}

gate_sast() {
  local component
  local -a scan_paths=(infra experiment/scripts)
  while IFS= read -r component; do
    [[ -n "${component}" ]] || continue
    scan_paths+=("src/${component}")
  done < <(jq -r '.affected_components[] | select(.kind == "service") | .name' \
    "${COMPONENT_SELECTION_FILE}")

  docker run --rm \
    -e SEMGREP_SEND_METRICS=off \
    -v "${REPO_ROOT}:/src:ro" \
    -v "${OUTPUT_DIR}:/output" \
    -w /src \
    "${SEMGREP_IMAGE}" semgrep scan \
    --config "${SEMGREP_RULESET}" \
    --metrics=off \
    --no-git-ignore \
    --error \
    --json \
    --output /output/semgrep.json \
    "${scan_paths[@]}"
}

gate_filesystem_security_scan() {
  local component
  local selected=0
  local failed=0
  while IFS= read -r component; do
    [[ -n "${component}" ]] || continue
    selected=$((selected + 1))
    echo "scanning filesystem for ${component}"
    docker run --rm \
      -v "${REPO_ROOT}:/src:ro" \
      -v "${OUTPUT_DIR}:/output" \
      -v online-boutique-trivy-cache:/root/.cache \
      "${TRIVY_IMAGE}" fs \
      --scanners vuln,misconfig \
      --severity HIGH,CRITICAL \
      --ignore-unfixed \
      --exit-code 1 \
      --format json \
      --output "/output/trivy-filesystem-${component}.json" \
      "/src/src/${component}" || failed=1
  done < <(jq -r '.affected_components[] | select(.kind == "service") | .name' \
    "${COMPONENT_SELECTION_FILE}")
  echo "scanned_service_filesystems=${selected}"
  [[ ${failed} -eq 0 ]]
}

gate_affected_artifact_validation() {
  local component docker_context source_image_name image_tag image_id
  local build_status sbom_status scan_status retained_locally
  local publication_status remote_tag remote_reference manifest_digest push_output
  local selected=0
  local failed=0
  : >"${ARTIFACTS_NDJSON}"

  while IFS=$'\t' read -r component docker_context source_image_name; do
    [[ -n "${component}" ]] || continue
    selected=$((selected + 1))
    image_tag="online-boutique/${component}-ci:${CANDIDATE_ID}-${TIMESTAMP}"
    image_id="unavailable"
    build_status="fail"
    sbom_status="not-run"
    scan_status="not-run"
    publication_status="not-requested"
    remote_tag=""
    remote_reference=""
    manifest_digest=""
    retained_locally=false
    ACTIVE_IMAGE_TAG="${image_tag}"

    echo "building ${component} from ${docker_context}"
    if docker build --progress=plain --pull=false --tag "${image_tag}" \
      "${REPO_ROOT}/${docker_context}"; then
      build_status="pass"
      image_id="$(docker image inspect "${image_tag}" --format '{{.Id}}')"

      if docker run --rm \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v "${OUTPUT_DIR}:/output" \
        "${SYFT_IMAGE}" "docker:${image_tag}" \
        -o "cyclonedx-json=/output/${component}-sbom.cdx.json"; then
        sbom_status="pass"
      else
        sbom_status="fail"
        failed=1
      fi

      if docker run --rm \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v "${OUTPUT_DIR}:/output" \
        -v online-boutique-trivy-cache:/root/.cache \
        "${TRIVY_IMAGE}" image \
        --severity HIGH,CRITICAL \
        --ignore-unfixed \
        --exit-code 1 \
        --format json \
        --output "/output/trivy-${component}-image.json" \
        "${image_tag}"; then
        scan_status="pass"
      else
        scan_status="fail"
        failed=1
      fi
    else
      failed=1
    fi

    if [[ "${PUBLISH_ARTIFACTS}" == "true" ]]; then
      publication_status="not-run"
      if [[ "${build_status}" == "pass" && "${sbom_status}" == "pass" && "${scan_status}" == "pass" ]]; then
        remote_tag="${ARTIFACT_REGISTRY_PREFIX}/${component}:${CANDIDATE_ID}"
        ACTIVE_REMOTE_TAG="${remote_tag}"
        if docker tag "${image_tag}" "${remote_tag}" && push_output="$(docker push "${remote_tag}" 2>&1)"; then
          echo "${push_output}"
          manifest_digest="$(sed -nE 's/.*digest: (sha256:[0-9a-f]{64}).*/\1/p' <<<"${push_output}" | tail -1)"
          if [[ "${manifest_digest}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
            remote_reference="${ARTIFACT_REGISTRY_PREFIX}/${component}@${manifest_digest}"
            publication_status="pass"
          else
            echo "Could not obtain immutable manifest digest after publishing ${component}." >&2
            publication_status="fail"
            failed=1
          fi
        else
          echo "${push_output:-docker push failed before producing output}" >&2
          publication_status="fail"
          failed=1
        fi
        docker image rm "${remote_tag}" >/dev/null 2>&1 || true
        ACTIVE_REMOTE_TAG=""
      else
        failed=1
      fi
    fi

    if ! docker image rm "${image_tag}" >/dev/null 2>&1; then
      if [[ "${build_status}" == "pass" ]]; then
        retained_locally=true
      fi
    else
      ACTIVE_IMAGE_TAG=""
    fi

    jq -cn \
      --arg component "${component}" \
      --arg source_image_name "${source_image_name}" \
      --arg image_tag "${image_tag}" \
      --arg image_id "${image_id}" \
      --arg build_status "${build_status}" \
      --arg sbom_status "${sbom_status}" \
      --arg scan_status "${scan_status}" \
      --arg publication_status "${publication_status}" \
      --arg remote_reference "${remote_reference}" \
      --arg manifest_digest "${manifest_digest}" \
      --argjson retained_locally "${retained_locally}" \
      '{
        component: $component,
        source_image_name: $source_image_name,
        local_image_tag: $image_tag,
        image_id: $image_id,
        build_status: $build_status,
        sbom_status: $sbom_status,
        image_scan_status: $scan_status,
        publication_status: $publication_status,
        remote_reference: (if $remote_reference == "" then null else $remote_reference end),
        manifest_digest: (if $manifest_digest == "" then null else $manifest_digest end),
        retained_locally: $retained_locally
      }' >>"${ARTIFACTS_NDJSON}"
  done < <(jq -r '.affected_components[] | select(.kind == "service") |
    [.name, .docker_context, .source_image_name] | @tsv' "${COMPONENT_SELECTION_FILE}")

  jq -s '.' "${ARTIFACTS_NDJSON}" >"${ARTIFACTS_FILE}"
  echo "validated_service_artifacts=${selected}"
  [[ ${failed} -eq 0 ]]
}

gate_policy_coverage() {
  local gate_id
  local missing=0
  local observed
  observed="$(jq -s -r '.[].id' "${GATES_NDJSON}")"

  while IFS= read -r gate_id; do
    if [[ "${gate_id}" == "policy-coverage" ]]; then
      continue
    fi
    if ! grep -Fqx -- "${gate_id}" <<<"${observed}"; then
      echo "Required policy gate was not executed: ${gate_id}" >&2
      missing=1
    fi
  done < <(jq -r '.required_gates[]' "${POLICY_FILE}")

  while IFS= read -r gate_id; do
    if ! jq -e --arg id "${gate_id}" '.required_gates | index($id) != null' "${POLICY_FILE}" >/dev/null; then
      echo "Executed required gate is absent from policy: ${gate_id}" >&2
      missing=1
    fi
  done < <(jq -s -r '.[] | select(.required == true) | .id' "${GATES_NDJSON}")

  [[ ${missing} -eq 0 ]]
}

run_gate "candidate-identity" "Candidate and Git identity" true gate_candidate_identity
run_gate "component-selection" "Affected components have deterministic validation coverage" true gate_component_selection
run_gate "policy-readiness" "Policy readiness for the selected mode" true gate_policy_readiness
run_gate "shellcheck" "Shell scripts pass ShellCheck" true gate_shellcheck
run_gate "python-syntax" "Python experiment scripts parse" true gate_python_syntax
run_gate "ci-contract-tests" "CI decision contracts pass their tests" true gate_ci_contract_tests
run_gate "json-syntax" "Experiment configuration JSON parses" true gate_json_syntax
run_gate "protobuf-contracts" "Canonical protobuf remains compatible and generated clients stay synchronized" true gate_protobuf_contracts
run_gate "terraform-static" "Terraform formatting and validation" true gate_terraform_static
run_gate "kustomize-render" "Every experiment Kustomize overlay renders" true gate_kustomize_render
run_gate "kubernetes-policy-self-test" "Kubernetes policy detects a privileged synthetic canary" true gate_kubernetes_policy_self_test
run_gate "kubernetes-policy" "Rendered workloads satisfy conventional Kubernetes security policy" true gate_kubernetes_policy
run_gate "checkout-unit-tests" "Checkoutservice compiles and passes Go tests" true gate_checkout_unit_tests
run_gate "checkout-semantic-contracts" "Checkout payment and side-effect contracts pass" true gate_checkout_semantic_contracts
run_gate "affected-component-tests" "Affected checkout-path services pass their language adapter" true gate_affected_component_tests
run_gate "secret-scanner-self-test" "Secret scanner detects a synthetic canary" true gate_secret_scanner_self_test
run_gate "secret-scan" "Candidate tree has no detected secrets" true gate_secret_scan
run_gate "sast-self-test" "Vendored SAST rules detect a synthetic canary" true gate_sast_self_test
run_gate "sast" "Static application security scan" true gate_sast
run_gate "filesystem-security-scan" "Dependency and configuration security scan" true gate_filesystem_security_scan
run_gate "affected-artifact-validation" "Affected service images build, produce SBOMs and pass vulnerability scan" true gate_affected_artifact_validation
run_gate "policy-coverage" "Executed required gates match the versioned policy" true gate_policy_coverage

jq -s '.' "${GATES_NDJSON}" >"${OUTPUT_DIR}/gates.json"

FAILED_REQUIRED="$(jq '[.[] | select(.required == true and .status != "pass")] | length' "${OUTPUT_DIR}/gates.json")"
LOCAL_DECISION="pass"
ELIGIBLE_FOR_STAGING=true
CONFIRMATORY_ELIGIBLE=false
if [[ "${FAILED_REQUIRED}" -gt 0 ]]; then
  LOCAL_DECISION="block"
  ELIGIBLE_FOR_STAGING=false
elif [[ "${MODE}" == "confirmatory" ]]; then
  CONFIRMATORY_ELIGIBLE=true
fi

FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
COMPONENT_SELECTION_SHA256="$(sha256sum "${COMPONENT_SELECTION_FILE}" | cut -d ' ' -f1)"
jq -n \
  --arg schema_version "1.0.0" \
  --arg run_id "${RUN_ID}" \
  --arg candidate_id "${CANDIDATE_ID}" \
  --arg mode "${MODE}" \
  --arg started_at "${STARTED_AT}" \
  --arg finished_at "${FINISHED_AT}" \
  --arg git_commit "${GIT_COMMIT}" \
  --arg git_tree "${GIT_TREE_SHA}" \
  --arg git_head_ref_commit "${GIT_HEAD_REF_COMMIT}" \
  --arg git_base_commit "${GIT_BASE_COMMIT}" \
  --arg local_decision "${LOCAL_DECISION}" \
  --arg component_selection_sha256 "${COMPONENT_SELECTION_SHA256}" \
  --argjson git_dirty "${GIT_DIRTY}" \
  --argjson failed_required_gates "${FAILED_REQUIRED}" \
  --argjson eligible_for_staging "${ELIGIBLE_FOR_STAGING}" \
  --argjson confirmatory_eligible "${CONFIRMATORY_ELIGIBLE}" \
  --slurpfile gates "${OUTPUT_DIR}/gates.json" \
  --slurpfile component_selection "${COMPONENT_SELECTION_FILE}" \
  --slurpfile protobuf_contracts "${PROTOBUF_CONTRACTS_FILE}" \
  --slurpfile artifacts "${ARTIFACTS_FILE}" \
  '{
    schema_version: $schema_version,
    run_id: $run_id,
    candidate_id: $candidate_id,
    mode: $mode,
    scope: "local-pre-staging-ci",
    started_at: $started_at,
    finished_at: $finished_at,
    git: {
      commit: $git_commit,
      tree: $git_tree,
      head_ref_commit: $git_head_ref_commit,
      base_commit: $git_base_commit,
      dirty: $git_dirty
    },
    artifacts: $artifacts[0],
    protobuf_contracts: {
      evidence: "protobuf-contracts.json",
      decision: $protobuf_contracts[0].decision,
      normalized_descriptor_sha256: $protobuf_contracts[0].checks.canonical.normalized_descriptor_sha256
    },
    component_selection: {
      evidence: "component-selection.json",
      sha256: $component_selection_sha256,
      changed_files_sha256: $component_selection[0].changed_files_sha256,
      decision: $component_selection[0].decision,
      affected_components: [$component_selection[0].affected_components[]?.name],
      affected_service_components: [
        $component_selection[0].affected_components[]?
        | select(.kind == "service")
        | .name
      ]
    },
    gates: $gates[0],
    failed_required_gates: $failed_required_gates,
    local_decision: $local_decision,
    eligible_for_staging: $eligible_for_staging,
    confirmatory_eligible: $confirmatory_eligible,
    final_pipeline_decision: false,
    staging_executed: false,
    pdt_executed: false,
    cloud_resources_created: false
  }' >"${OUTPUT_DIR}/ci-local-decision.json"

printf 'Evidence: %s\n' "${OUTPUT_DIR}"
printf 'Local decision: %s\n' "${LOCAL_DECISION}"

if [[ "${LOCAL_DECISION}" != "pass" ]]; then
  exit 1
fi
