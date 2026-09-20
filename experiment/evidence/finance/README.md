# Evidências financeiras do experimento

Este diretório registra somente observações necessárias à governança do
protocolo. Um orçamento do Cloud Billing é um alerta, não um limite rígido, e
não substitui a revisão do custo incremental entre blocos.

O snapshot de prontidão de 20/09/2026 confirma que o orçamento bruto está
configurado, mas que não há exportação detalhada de faturamento consultável no
projeto. Por isso, a revisão financeira exigida para congelar o protocolo ainda
não pode ser aprovada e a coleta confirmatória permanece bloqueada.

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
BRL. O valor é uma estimativa exportada, não uma fatura finalizada.

O plano do stack isolado foi validado sem aplicação. Com a trava desligada não
há mudança; com a trava ligada aparecem somente a API do BigQuery e o dataset
`US`, sem alterações em GKE, Kubernetes, Artifact Registry, IAM ou orçamento.
A evidência está em
[`billing-export-plan-readiness-20260920T224203Z.json`](./billing-export-plan-readiness-20260920T224203Z.json).
