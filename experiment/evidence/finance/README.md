# Evidências financeiras do experimento

Este diretório registra somente observações necessárias à governança do
protocolo. Um orçamento do Cloud Billing é um alerta, não um limite rígido, e
não substitui a revisão do custo incremental entre blocos.

O estado mais recente, de 04/10/2026 UTC, confirma que o Standard usage cost
export está ativo e que a tabela particionada `gcp_billing_export_v1_*` já foi
entregue no dataset protegido em `US`. A consulta versionada e limitada a
100 MB observou R$519,736015 de custo bruto, R$-519,737769 em créditos e
R$-0,001754 de custo líquido entre 19/09 e 03/10. O review preserva R$200 como
teto incremental futuro e projeta R$719,736015 de custo bruto total, abaixo do
orçamento de R$1.751,10. A evidência está elegível para aprovação humana, mas a
aprovação canônica foi gerada após a confirmação literal do pesquisador e
permanece não autorizadora de cloud. Os registros atuais estão em
[`cost-window-20260919-20261004.json`](./cost-window-20260919-20261004.json) e
[`financial-review-eligibility-20261004T030924Z.json`](./financial-review-eligibility-20261004T030924Z.json).
O vínculo canônico está em
[`../../protocol/approvals/cost-review-v1.json`](../../protocol/approvals/cost-review-v1.json).
Os recibos históricos de ativação permanecem em
[`billing-export-activation-20260929T052504Z.json`](./billing-export-activation-20260929T052504Z.json)
e
[`billing-export-dataset-readiness-20260929T054404Z.json`](./billing-export-dataset-readiness-20260929T054404Z.json).

O snapshot consolidado anterior, de 27/09/2026 UTC, está em
[`pre-freeze-readiness-post-pr4-20260927T002039Z.json`](./pre-freeze-readiness-post-pr4-20260927T002039Z.json).
Ele registra o protocolo em 6/17 controles, a infraestrutura de
publicação em 12/12, a prontidão estrutural então em 13/21, 12/12
deployments e pods operacionais disponíveis, os cinco namespaces auxiliares
vazios e apenas a imagem de engenharia anterior do `checkoutservice` no
Artifact Registry. O PR #4 foi incorporado sem rótulos de autorização; nenhuma
publicação ou execução cloud foi habilitada. O snapshot anterior permanece em
[`pre-freeze-readiness-post-pr2-20260926T004340Z.json`](./pre-freeze-readiness-post-pr2-20260926T004340Z.json),
e o registro inicial permanece em
[`protocol-freeze-readiness-20260922T013315Z.json`](./protocol-freeze-readiness-20260922T013315Z.json).

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

O plano separado do RBAC Oracle foi gerado em 26/09/2026 UTC com refresh
desligado e sem `apply`. O validador selado passou em 10/10 controles: somente
`kubernetes_role_v1.github_experiment_oracle_runner[0]` e sua RoleBinding seriam
criadas; há 0 alterações, 0 destruições e nenhum recurso de compute, storage,
rede ou faturamento contínuo. A evidência sanitizada está em
[`oracle-rbac-terraform-plan-validation-20260926T163444Z.json`](./oracle-rbac-terraform-plan-validation-20260926T163444Z.json).
O plano binário contém estado e não é versionado; o relatório vincula seu
SHA-256 e não autoriza `apply`, custo ou execução Oracle.

Depois do merge do PR #4, o plano foi regenerado com refresh real do estado
remoto. O resultado continuou limitado às mesmas duas criações, com 0
alterações, 0 destruições e 10/10 controles aprovados. A evidência atualizada
está em
[`oracle-rbac-terraform-plan-validation-post-pr4-20260927T002511Z.json`](./oracle-rbac-terraform-plan-validation-post-pr4-20260927T002511Z.json).
Esse plano histórico permaneceu fora do Git e não foi aplicado naquele
momento. Em 29/09/2026 UTC, um plano fresco passou novamente em 10/10 e o mesmo
binário foi aplicado: duas adições, zero alterações e zero destruições. A
auditoria Oracle confirmou Role e RoleBinding exatas, o namespace vazio e
18/21 controles estruturais. O recibo de aplicação está em
[`oracle-rbac-terraform-application-20260929T055307Z.json`](./oracle-rbac-terraform-application-20260929T055307Z.json),
vinculado à validação pré-apply
[`oracle-rbac-terraform-plan-validation-preapply-20260929T0550Z.json`](./oracle-rbac-terraform-plan-validation-preapply-20260929T0550Z.json).

O lote mínimo seguinte foi separado em uma solicitação de mudança auditável:
as duas criações RBAC, o rótulo passivo, os dois secrets protegidos e a variável
Oracle mantida em `false`. O documento exclui publicação, labels em PR,
workloads e execução cloud, e prevê que o auditor avance para 18/21 controles
estruturais sem tornar uma candidata elegível. A proposta está em
[`oracle-passive-controls-change-request-20260927T002627Z.json`](./oracle-passive-controls-change-request-20260927T002627Z.json)
e continua com `apply_authorized: false` até autorização explícita.

O instalador
[`install-oracle-passive-github-controls.py`](../../scripts/install-oracle-passive-github-controls.py)
materializa somente a parte GitHub dessa proposta. Seu modo padrão é uma
auditoria somente leitura; o modo de aplicação exige confirmação literal e
recibo novo, força a variável para `false` antes dos secrets, recusa PR armado,
preserva secrets existentes e não expõe os valores gerados. O dry-run real
pós-PR #4 confirmou exatamente quatro ações pendentes e nenhum PR aberto com
label de autorização. Nenhuma mutação foi executada. O resultado está em
[`../oracle/oracle-passive-github-controls-readiness-20260927T003254Z.json`](../oracle/oracle-passive-github-controls-readiness-20260927T003254Z.json).

Depois do merge do PR #5, as quatro ações foram aplicadas. O recibo sanitizado
confirma a variável Oracle em `false`, o label passivo sem vínculo a PR, os dois
nomes de secrets presentes e nenhum valor divulgado. A auditoria posterior
retornou zero ações restantes. Os registros estão em
[`../oracle/oracle-passive-github-controls-installation-20260929T054946Z.json`](../oracle/oracle-passive-github-controls-installation-20260929T054946Z.json)
e
[`../oracle/oracle-passive-github-controls-post-install-readiness-20260929T055153Z.json`](../oracle/oracle-passive-github-controls-post-install-readiness-20260929T055153Z.json).

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
o auditor vincula o custo bruto observado como baseline do projeto e comprova
que essa baseline somada ao teto incremental futuro de R$200 permanece abaixo
do orçamento bruto de R$1.751,10. Uma nova revisão é obrigatória ao atingir
R$150 de gasto incremental após a baseline. O snapshot de prontidão, que não
contém custo corrente, é deliberadamente inelegível como substituto.

O Standard usage cost export foi ativado em 29/09/2026 UTC para o dataset
protegido `microservices-demo-tcc.online_boutique_billing`. A verificação
imediata foi somente leitura e encontrou zero tabelas; nenhuma query foi
executada e a revisão financeira permanece bloqueada até a primeira entrega
diária. O recibo está em
[`billing-export-activation-20260929T052504Z.json`](./billing-export-activation-20260929T052504Z.json).

Uma segunda verificação somente leitura confirmou que o dataset está em `US`
e que a identidade oficial
`billing-export-bigquery@system.gserviceaccount.com` possui acesso de escrita.
Assim, a ausência inicial da tabela é estado de entrega pendente, não uma
falha conhecida de localização ou permissão. A evidência está em
[`billing-export-dataset-readiness-20260929T054404Z.json`](./billing-export-dataset-readiness-20260929T054404Z.json).

O elo entre a observação e a revisão canônica agora é automatizado por
[`prepare-financial-review.py`](../../scripts/prepare-financial-review.py). O
modo padrão apenas mede elegibilidade; o modo de aprovação exige confirmação
literal, recusa sobrescrever uma aprovação existente e aceita somente
`experiment/protocol/approvals/cost-review-v1.json` como destino. Dez testes
cobrem adulteração, teto, timestamps, caminho, confirmação e compatibilidade
com o auditor congelado. O preparador sempre grava
`cloud_execution_authorized: false` e não substitui a decisão humana.

O plano do stack isolado foi validado sem aplicação. Com a trava desligada não
há mudança; com a trava ligada aparecem somente a API do BigQuery e o dataset
`US`, sem alterações em GKE, Kubernetes, Artifact Registry, IAM ou orçamento.
A evidência está em
[`billing-export-plan-readiness-20260920T224203Z.json`](./billing-export-plan-readiness-20260920T224203Z.json).
