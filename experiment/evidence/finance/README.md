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
