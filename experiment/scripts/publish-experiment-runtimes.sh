#!/usr/bin/env bash

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
source_commit=${SOURCE_COMMIT:-}
source_tree=${SOURCE_TREE:-}
pull_request_number=${PULL_REQUEST_NUMBER:-}
workflow_run_id=${WORKFLOW_RUN_ID:-}
registry_prefix=${ARTIFACT_REGISTRY_PREFIX:-}
output_dir=${OUTPUT_DIR:-}
trivy_cache_dir=${TRIVY_CACHE_DIR:-${output_dir}.trivy-cache}
allow_publication=${ALLOW_RUNTIME_PUBLICATION:-false}
cost_review=${COST_REVIEW_ACKNOWLEDGED:-false}
syft_image=${SYFT_IMAGE:-ghcr.io/anchore/syft@sha256:500e2d872ac019436926e8322b4fc1f39441d94d21f6f4046c6ff29b30e8cb02}
trivy_image=${TRIVY_IMAGE:-aquasec/trivy@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

for command_name in awk date docker gcloud git jq mkdir tee; do
  require_command "$command_name"
done

[[ "$allow_publication" == "true" && "$cost_review" == "true" ]] || {
  echo "Runtime publication requires explicit cloud and financial authorization." >&2
  exit 1
}
[[ "$source_commit" =~ ^[a-f0-9]{40}$ ]] || {
  echo "SOURCE_COMMIT must be a full Git SHA." >&2
  exit 1
}
[[ "$source_tree" =~ ^[a-f0-9]{40}$ ]] || {
  echo "SOURCE_TREE must be a full Git tree SHA." >&2
  exit 1
}
[[ "$pull_request_number" =~ ^[1-9][0-9]*$ ]] || {
  echo "PULL_REQUEST_NUMBER must be positive." >&2
  exit 1
}
[[ "$workflow_run_id" =~ ^[1-9][0-9]*$ ]] || {
  echo "WORKFLOW_RUN_ID must be positive." >&2
  exit 1
}
[[ "$registry_prefix" == "us-central1-docker.pkg.dev/microservices-demo-tcc/online-boutique-experiment" ]] || {
  echo "ARTIFACT_REGISTRY_PREFIX must be the reviewed experiment repository." >&2
  exit 1
}
[[ -n "$output_dir" ]] || {
  echo "OUTPUT_DIR is required." >&2
  exit 1
}
[[ "$(git -C "$repo_root" rev-parse HEAD)" == "$source_commit" ]] || {
  echo "Checked-out commit differs from SOURCE_COMMIT." >&2
  exit 1
}
[[ "$(git -C "$repo_root" rev-parse 'HEAD^{tree}')" == "$source_tree" ]] || {
  echo "Checked-out tree differs from SOURCE_TREE." >&2
  exit 1
}

mkdir -p "$output_dir"
mkdir -p "$trivy_cache_dir"
: > "${output_dir}/images.ndjson"

images=(
  "checkout-pdt-controller|experiment/pdt/controller/Dockerfile|."
  "oracle-harness|experiment/oracle/harness/Dockerfile|."
  "currency-reference|src/currencyservice/Dockerfile|src/currencyservice"
)

for definition in "${images[@]}"; do
  IFS='|' read -r name dockerfile context <<< "$definition"
  tag="${registry_prefix}/${name}:git-${source_commit}"
  sbom_file="${name}-sbom.cdx.json"
  scan_file="${name}-trivy.json"
  docker build --pull --platform linux/amd64 \
    --file "${repo_root}/${dockerfile}" --tag "$tag" "${repo_root}/${context}"
  docker run --rm --volume /var/run/docker.sock:/var/run/docker.sock \
    "$syft_image" "$tag" -o cyclonedx-json \
    > "${output_dir}/${sbom_file}"
  docker run --rm --volume /var/run/docker.sock:/var/run/docker.sock \
    --volume "${trivy_cache_dir}:/root/.cache/" \
    "$trivy_image" image --scanners vuln --severity HIGH,CRITICAL \
    --ignore-unfixed --exit-code 1 --format json "$tag" \
    > "${output_dir}/${scan_file}"

  local_image_id=$(docker image inspect --format '{{.Id}}' "$tag")
  size_bytes=$(docker image inspect --format '{{.Size}}' "$tag")
  sbom_sha256=$(sha256sum "${output_dir}/${sbom_file}" | awk '{print $1}')
  scan_sha256=$(sha256sum "${output_dir}/${scan_file}" | awk '{print $1}')
  docker push "$tag" | tee "${output_dir}/${name}-push.log"
  registry_digest=$(awk '/^digest: sha256:[a-f0-9]{64} size:/{digest=$2} END{print digest}' \
    "${output_dir}/${name}-push.log")
  if [[ ! "$registry_digest" =~ ^sha256:[a-f0-9]{64}$ ]]; then
    echo "$name: Docker did not report an immutable pushed digest." >&2
    exit 1
  fi
  immutable_reference="${registry_prefix}/${name}@${registry_digest}"
  gcloud artifacts docker images describe "$immutable_reference" --format=json \
    > "${output_dir}/${name}-registry.json"
  described_reference=$(jq -er '.image_summary.fully_qualified_digest' \
    "${output_dir}/${name}-registry.json")
  if [[ "$described_reference" != "$immutable_reference" ]]; then
    echo "$name: registry digest verification differs from the pushed manifest." >&2
    exit 1
  fi
  jq -cn --arg name "$name" --arg source_tag "$tag" \
    --arg local_image_id "$local_image_id" --arg immutable_reference "$immutable_reference" \
    --arg registry_digest "$registry_digest" --argjson size_bytes "$size_bytes" \
    --arg sbom_path "$sbom_file" --arg sbom_sha256 "$sbom_sha256" \
    --arg scan_path "$scan_file" --arg scan_sha256 "$scan_sha256" \
    '{
      name:$name,
      source_tag:$source_tag,
      local_image_id:$local_image_id,
      immutable_reference:$immutable_reference,
      registry_digest:$registry_digest,
      uncompressed_size_bytes:$size_bytes,
      sbom:{
        status:"pass",
        path:$sbom_path,
        format:"cyclonedx-json",
        sha256:$sbom_sha256
      },
      vulnerability_scan:{
        status:"pass",
        path:$scan_path,
        scanner:"trivy",
        severity:["HIGH","CRITICAL"],
        ignore_unfixed:true,
        sha256:$scan_sha256
      },
      published:true
    }' >> "${output_dir}/images.ndjson"
done

jq -s --arg source_commit "$source_commit" --arg source_tree "$source_tree" \
  --arg repository "omatheu/microservices-demo" \
  --arg workflow_run_id "$workflow_run_id" \
  --arg published_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --argjson pull_request_number "$pull_request_number" '
  {
    schema_version:"1.1.0",
    source:{
      repository:$repository,
      commit:$source_commit,
      tree:$source_tree,
      pull_request_number:$pull_request_number,
      workflow_run_id:$workflow_run_id
    },
    authorization:{
      protected_environment:"tcc-experiment",
      explicit_cloud_gate:true,
      cost_review_acknowledged:true
    },
    build_platform:"linux/amd64",
    published_at:$published_at,
    published_to_registry:true,
    images:.
  }' "${output_dir}/images.ndjson" > "${output_dir}/summary.json"

jq . "${output_dir}/summary.json"
