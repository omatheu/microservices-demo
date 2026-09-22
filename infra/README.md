# Experimental infrastructure

This directory provisions the Google Cloud foundation used by the TCC
experiment described in [`../docs/tcc-experiment-plan.md`](../docs/tcc-experiment-plan.md).
It intentionally does not modify or replace the sample Terraform configuration
in `../terraform`.

## Topology

The cost-conscious topology uses one GKE Autopilot cluster and six
isolated namespaces:

| Namespace | Purpose |
| --- | --- |
| `operational` | Controlled operational instance and source of observed state |
| `staging` | Static pre-deployment validation baseline |
| `pdt` | State-synchronized counterfactual simulations |
| `pdt-system` | On-demand PDT control plane |
| `oracle` | Independent post-decision outcome adjudication |
| `observability` | Metrics and experiment evidence |

`ResourceQuota` objects establish explicit capacity ceilings. The application
overlays also apply the network policies supplied by Online Boutique.

## Prerequisites

- A Google Cloud project with billing enabled.
- `gcloud`, `terraform`, `kubectl`, and the GKE authentication plugin.
- A user with permission to enable project services and create GKE resources.
- Application Default Credentials (ADC) for Terraform.

Authenticate locally:

```sh
gcloud init
gcloud auth application-default login
gcloud config set project PROJECT_ID
```

## Provision the foundation

```sh
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Set `project_id` in `terraform.tfvars`, then review before creating resources:

```sh
terraform init
terraform fmt -check
terraform validate
terraform plan -out=tfplan
terraform show tfplan
terraform apply tfplan
```

Billable resources are locked by default. `allow_billable_resources` must stay
`false` until the available credit, its expiration, budget notifications,
service quotas, and the experiment execution window have been reviewed. A
Cloud Billing budget is an alerting mechanism and is not, by itself, a hard
spending cap.

Artifact Registry has a second, independent lock:
`allow_artifact_registry_creation` defaults to `false`. Enabling the general
billable-resource gate does not create the registry. When explicitly enabled,
the repository retains at least two recent versions per package and deletes
other versions older than three days. Review the Terraform plan and the
storage/egress estimate before changing this flag; no registry is created by
the CI scripts themselves.

The guard budget tracks R$1,751.10 in gross cost from September 19 through
December 19, 2026. It preserves R$10 from the reported R$1,761.10 promotional
credit. Credits are excluded from spend calculations so that they do not mask
resource consumption. Alerts are sent at 25%, 50%, 75%, 90%, 95%, and 100% to
the billing account's default recipients.

A second project-scoped gross-cost guard tracks the R$200 experiment ceiling
over the same period. Its alerts correspond to R$50, R$100, R$150, R$180, and
R$200. R$150 remains the mandatory manual review point in the protocol. Both
budgets are alerts rather than hard caps; namespace quotas, serial execution,
timeouts, cleanup, and the per-block cost review are the effective containment
controls.

### Exportação de custo por bloco

O stack separado [`terraform-billing-export`](./terraform-billing-export/README.md)
mantém `enable_billing_export_dataset = false` por padrão. Quando explicitamente
autorizado, ele cria somente o dataset
`online_boutique_billing` na multirregião `US`, protegido contra destruição, e
habilita a API do BigQuery. A ativação do **Standard usage cost export** continua
sendo uma ação separada na página de Cloud Billing; o Terraform não a habilita
implicitamente.

A localização `US` foi escolhida porque o export padrão pode receber o mês
atual e o mês anterior retroativamente. Consultas do experimento usam
`query-billing-cost-window.sh`, ficam restritas ao projeto e recusam processar
mais de 100 MB por execução. O resultado separa custo bruto, créditos e custo
líquido e nunca autoriza uma execução cloud.

The cluster is created with deletion protection enabled by default. The
configuration provisions the cluster and namespace boundaries only; application
deployment is a separate, explicit step.

## GitHub Actions identity

The pull-request cloud workflow uses keyless Workload Identity Federation.
Terraform keeps it behind a separate flag,
`enable_github_actions_federation = false`, and therefore does not create IAM
resources by default. When enabled after plan review, it creates:

- one service account without a JSON key;
- one GitHub OIDC pool/provider restricted by immutable repository and owner
  IDs, the `tcc-experiment` environment, the `workflow_run` event and the exact
  workflow on `main`;
- repository-scoped Artifact Registry writer access;
- project read access for the GKE cluster and Cloud Monitoring;
- Kubernetes mutation rights only in `staging` and `pdt`;
- direitos específicos em `pdt-system` apenas para executar e remover o Job,
  ConfigMap, ServiceAccount e NetworkPolicy do controlador sob demanda;
- read-only Kubernetes access to `operational` and namespace-name discovery.

It grants no mutation permission to `operational` or `oracle`. After applying a
reviewed plan, copy the two values from the `github_actions_federation` output
to the protected GitHub Environment secrets described in
[`../experiment/pipeline/README.md`](../experiment/pipeline/README.md). Keep the
GitHub financial kill switch disabled until each block review.

### Runtime publisher installation transaction

The publication-only identity is installed as a fail-closed transaction. First
generate a binary plan and validate that exact file from the repository root:

```sh
terraform -chdir=infra/terraform plan \
  -input=false \
  -out=/tmp/runtime-publication-controls.tfplan

python3 experiment/scripts/validate-runtime-publication-terraform-plan.py \
  --plan /tmp/runtime-publication-controls.tfplan \
  --require-safe
```

The validator accepts only three creates: the keyless publisher Service
Account, its repository-scoped OIDC binding, and
`roles/artifactregistry.writer` on the existing experiment repository. It
rejects updates, destroys, keys, project roles and compute, storage or network
changes. It records the SHA-256 of the binary plan but never authorizes or runs
`terraform apply`.

Only after a separate review and explicit apply authorization, apply that same
binary file. Then register the output without arming a publication:

```sh
terraform -chdir=infra/terraform apply /tmp/runtime-publication-controls.tfplan

publisher_service_account="$(
  terraform -chdir=infra/terraform output -json github_actions_federation |
    jq -r '.runtime_publisher_service_account'
)"

gh secret set GCP_RUNTIME_PUBLISHER_SERVICE_ACCOUNT \
  --repo omatheu/microservices-demo \
  --env tcc-experiment \
  --body "${publisher_service_account}"

gh variable set TCC_RUNTIME_PUBLICATION_ACKNOWLEDGED \
  --repo omatheu/microservices-demo \
  --env tcc-experiment \
  --body false

gh label create tcc-runtime-publication \
  --repo omatheu/microservices-demo \
  --color 1D76DB \
  --description "Authorize the isolated TCC runtime publication path"
```

The workflow must already be present on `main`. Do not attach an authorization
label to a pull request and do not change either financial variable to `true`
during installation. Finish by requiring 13/13 from
`audit-runtime-publication-readiness.py`. If any GitHub step fails, leave the
publisher unused and the switches off; do not compensate with direct IAM
changes. A future rollback must be produced and reviewed as a new Terraform
plan.

## Deploy the environments

After Terraform completes, configure `kubectl` using the command exposed by the
`get_credentials_command` output. Render each overlay before applying it:

```sh
kubectl kustomize ../kustomize/operational
kubectl kustomize ../kustomize/staging
kubectl kustomize ../kustomize/pdt
kubectl kustomize ../kustomize/oracle
```

Deploy only the operational baseline first:

```sh
kubectl apply -k ../kustomize/operational
kubectl wait --for=condition=Available deployments --all \
  --namespace operational --timeout=10m
kubectl get pods,services --namespace operational
```

The `operational` overlay includes the repository's load generator and public
frontend. The `staging`, `pdt`, and `oracle` overlays omit the continuous load
generator and expose the frontend only inside the cluster. Experiment-controlled
load is added by the runners. The oracle is separate from both decision
mechanisms: it is used only after their outputs are sealed and cannot provide
features or feedback to either one.

## Destruction safeguard

Destroying the cluster removes all experiment workloads and evidence stored
inside it. Export evidence first. Then set `deletion_protection = false`, apply
that change, and only afterward run `terraform destroy`.
