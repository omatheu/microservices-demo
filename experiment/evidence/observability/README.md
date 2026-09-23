# Evidências da Fase 2 — observabilidade

Validação executada em 20 de setembro de 2026 com o coletor versionado em
[`../../scripts/export-observability-window.sh`](../../scripts/export-observability-window.sh).

| Execução | Ambiente | Janela | Pontos | Resultado |
| --- | --- | ---: | ---: | --- |
| `obs-baseline-current-as-is-r1-20260920T023342Z` | operational | 15 min | 1.368 | concluída; validação inicial |
| `obs-collector-validation-current-empty-namespace-r1-20260920T023441Z` | pdt | 5 min | 0 | concluída; namespace deliberadamente vazio |
| `obs-baseline-current-as-is-r2-20260920T023502Z` | operational | 5 min | 384 | concluída; orçamento vinculado |

A execução operacional de 15 minutos coletou utilização de CPU, memória,
reinícios e uptime. Ela registrou 0,3925 CPU-request-hora e aproximadamente
0,454 GiB-request-hora. A segunda execução operacional confirmou o vínculo com
o orçamento **Online Boutique TCC - gross cost guard**, de R$1.751,10.

Cada diretório contém manifesto, status, CSV normalizado, respostas brutas da
API, recursos Kubernetes, eventos e registro de duração/capacidade. Os IDs de
cenário, candidata, alternativa e repetição fazem parte do manifesto e do nome
da execução.

## Limitação financeira conhecida

O Cloud Billing ainda não possui uma exportação detalhada associada a estas
janelas. Por isso, o custo bruto monetário de cada execução é registrado como
`null`, com o estado `billing-export-not-configured`. Capacidade-tempo e
orçamento são registrados sem converter preços de tabela em custo observado.
Essa escolha evita apresentar uma estimativa como se fosse uma cobrança real.
