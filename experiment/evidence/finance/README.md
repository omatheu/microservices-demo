# Evidências financeiras do experimento

Este diretório registra somente observações necessárias à governança do
protocolo. Um orçamento do Cloud Billing é um alerta, não um limite rígido, e
não substitui a revisão do custo incremental entre blocos.

O snapshot mais recente, de 22/09/2026 UTC, confirma que os dois orçamentos e o
dataset protegido estão configurados, mas o dataset ainda possui zero tabelas:
o Cloud Billing não criou `gcp_billing_export_v1_*`. Nenhuma query faturável foi
executada. Por isso, a revisão financeira exigida para congelar o protocolo
ainda não pode ser aprovada e a coleta confirmatória permanece bloqueada. A
evidência somente leitura está em
[`protocol-freeze-readiness-20260922T013315Z.json`](./protocol-freeze-readiness-20260922T013315Z.json).
Ela registra também 12/12 deployments e pods operacionais disponíveis, os
cinco namespaces auxiliares vazios e apenas a imagem de engenharia anterior do
`checkoutservice` no Artifact Registry.

## Plano de publicação dos runtimes

O artefato `experiment-runtime-images-*` produzido pela CI registra o commit, a
árvore Git, o pull request, a plataforma, os IDs locais, os tamanhos, o SBOM e o
resultado da análise de vulnerabilidades das três imagens experimentais. Antes
de qualquer publicação, ele pode ser convertido em um plano verificável com:

```bash
python3 experiment/scripts/prepare-runtime-publication-plan.py \
  --summary <artifact>/summary.json \
  --expected-commit <sha-completo-validado> \
  --existing-repository-bytes <bytes-observados-no-registro> \
  --registry-prefix us-central1-docker.pkg.dev/microservices-demo-tcc/online-boutique-experiment
```

O tamanho não comprimido é tratado como limite superior conservador para o
armazenamento adicional. O resultado distingue a capacidade potencial do
repositório da franquia compartilhada na conta de faturamento. Sem o consumo
total da conta e o custo corrente detalhado, ele permanece como
`review-required-no-publication-authorized`: o plano nunca autoriza escrita no
GCP, aprovação financeira ou execução cloud.

Depois de uma publicação explicitamente autorizada, os digests ainda precisam
passar por `bind-runtime-publication.py`. O binder gera propostas de manifests
com a mesma proveniência de commit, árvore, workflow protegido, SBOM e scan;
ele não publica, congela nem autoriza execução.

A identidade de publicação foi desacoplada da identidade que executa workloads.
O plano somente leitura em
[`runtime-publication-identity-plan-20260922T025300Z.json`](./runtime-publication-identity-plan-20260922T025300Z.json)
contém três adições: Service Account sem chave, vínculo OIDC e Writer apenas no
repositório Artifact Registry. Não há IAM de projeto, RBAC Kubernetes, mudança
ou destruição de recurso existente. Esse arquivo preserva o estado anterior ao
apply; a instalação controlada posterior aplicou exatamente as três adições e
continua sem autorizar armazenamento de imagens ou execução de workloads.

O plano binário foi regenerado em 22/09/2026 UTC e conferido diretamente por
[`validate-runtime-publication-terraform-plan.py`](../../scripts/validate-runtime-publication-terraform-plan.py).
Os 9/9 controles passaram: somente as três criações previstas aparecem, todas
são `create`, o principal OIDC é o repositório imutável esperado, o Writer está
limitado ao repositório, o grafo referencia a identidade exclusiva e não existe
chave, compute, storage ou rede nova. O relatório sanitizado, vinculado ao
SHA-256 do plano binário, está em
[`runtime-publication-terraform-plan-validation-20260922T033401Z.json`](./runtime-publication-terraform-plan-validation-20260922T033401Z.json).
O plano binário não é versionado porque contém o estado integral da
infraestrutura. O relatório preserva a validação pré-apply e declara
explicitamente que ele próprio não executou mutação, publicação ou autorização
de custo.

O auditor somente leitura
[`audit-runtime-publication-readiness.py`](../../scripts/audit-runtime-publication-readiness.py)
transforma essas pendências em 13 controles verificáveis. A leitura de
22/09/2026 UTC aprovou 5/13: `main`, revisor obrigatório `omatheu`, política de
branch restrita a `main`, PR #1 aberto e desarmado e ausência de papel de projeto
na identidade proposta. Os oito bloqueios restantes são o workflow ainda fora
de `main`, o rótulo, o secret, a variável financeira exclusiva e a identidade
publisher com seus vínculos mínimos. O relatório está em
[`runtime-publication-readiness-20260922T031427Z.json`](./runtime-publication-readiness-20260922T031427Z.json).
Ele registra `read_only: true`, nenhuma mutação GitHub/GCP pelo auditor e nenhuma
autorização de publicação. Uma nova conferência fail-closed pode ser executada
com:

```bash
python3 experiment/scripts/audit-runtime-publication-readiness.py \
  --pull-request 1 \
  --require-ready
```

Após autorização, o plano binário vinculado foi aplicado com **3 adições, 0
alterações e 0 destruições**. Em seguida foram cadastrados o secret da identidade
publisher, a variável exclusiva com valor `false` e o rótulo passivo, sem
anexá-lo ao PR #1. O plano Terraform pós-apply retornou `No changes`. O recibo
está em
[`runtime-publication-controls-installation-20260922T033857Z.json`](./runtime-publication-controls-installation-20260922T033857Z.json).

A auditoria somente leitura pós-instalação passou em 12/13 controles. Ela
confirmou zero chaves, Writer somente no repositório, nenhum papel de projeto,
principal OIDC exato, variáveis financeiras desligadas e PR desarmado. O único
bloqueio restante é o workflow revisado ainda não existir na `main`. A evidência
está em
[`runtime-publication-readiness-20260922T033857Z.json`](./runtime-publication-readiness-20260922T033857Z.json).
O campo `cloud_mutation_performed: false` desse arquivo descreve o auditor
somente leitura; o recibo separado registra as mutações de instalação que o
precederam.

Depois do merge do PR #1, o workflow revisado passou a existir em `main` e o
auditor foi refinado para separar prontidão estrutural de prontidão da
candidata. A leitura de 24/09/2026 UTC comprova **12/12 controles de
infraestrutura prontos** e **0/1 controle de candidata**, porque o PR #1 está
corretamente fechado após o merge. O resultado geral permanece 12/13 e não
autoriza publicação. A evidência está em
[`runtime-publication-readiness-post-merge-20260924T223256Z.json`](./runtime-publication-readiness-post-merge-20260924T223256Z.json).
O próximo 13/13 depende de um novo PR candidato aberto, do próprio repositório,
não draft e inicialmente sem qualquer rótulo de autorização.

Uma leitura posterior da conta de faturamento retornou somente o projeto
`microservices-demo-tcc` e somente o repositório Docker do experimento, com
7.843.495 bytes. A projeção conservadora após as três imagens é 236.019.643
bytes, abaixo dos 500.000.000 bytes considerados para a franquia. A evidência
está em
[`artifact-registry-storage-readiness-20260920T222357Z.json`](./artifact-registry-storage-readiness-20260920T222357Z.json).
Isso resolve a incerteza de armazenamento visível na conta, mas não substitui a
exportação do custo corrente: publicação e execução continuam bloqueadas.

Após a criação e ativação explicitamente autorizadas do Standard usage cost
export, uma janela pode ser conferida com:

```bash
START_TIME=2026-09-19T00:00:00Z \
END_TIME=<fim-exclusivo-em-UTC> \
OUTPUT_FILE=experiment/evidence/finance/cost-window.json \
./experiment/scripts/query-billing-cost-window.sh
```

A consulta é limitada a 100 MB, usa cache, exige exatamente uma tabela padrão,
filtra `microservices-demo-tcc` e falha se não houver uma observação completa em
BRL. O valor é uma estimativa exportada, não uma fatura finalizada. O arquivo de
revisão financeira deve referenciar essa saída por caminho relativo e SHA-256;
o auditor confere que `confirmatory_incremental_spend_brl` é exatamente o custo
bruto observado. O snapshot de prontidão, que não contém custo corrente, é
deliberadamente inelegível como substituto.

O plano do stack isolado foi validado sem aplicação. Com a trava desligada não
há mudança; com a trava ligada aparecem somente a API do BigQuery e o dataset
`US`, sem alterações em GKE, Kubernetes, Artifact Registry, IAM ou orçamento.
A evidência está em
[`billing-export-plan-readiness-20260920T224203Z.json`](./billing-export-plan-readiness-20260920T224203Z.json).
