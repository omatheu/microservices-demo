# Evidências da Fase 3 — staging tradicional

## Piloto pareado com artefato imutável

O run `staging-engineering-artifact-binding-v2-r4-20260920T070010Z` executou o
mesmo digest publicado pela CI local, após três repetições de calibração de
engenharia predeclaradas. Resultado:

- 120/120 requisições do perfil fixo;
- p95 geral de 719,925 ms e p99 de 923,593 ms;
- 10/10 checkouts válidos, p95/p99 de 629,476 ms;
- 2/2 caminhos negativos corretamente rejeitados;
- 351/352 requisições Locust bem-sucedidas, taxa de 99,716%;
- zero indisponibilidade e zero aumento de reinícios do `checkoutservice`;
- decisão `PASS` e decisão convencional selada como `approve`.

Os limiares foram calibrados apenas com as repetições r1–r3 da candidata
segura; r4 foi a execução independente do piloto. O tamanho de 10 checkouts faz
p95 e p99 coincidirem com o maior valor e deverá ser justificado ou ampliado
antes do protocolo confirmatório. O resultado valida a mecânica, não a hipótese
do TCC.

## Validação inicial

A candidata de referência `current` foi executada em 20 de setembro de 2026:

- execução: `staging-current-r1-20260920T023854Z`;
- 11 deployments implantados sem Load Balancer público;
- 60 segundos de aquecimento e 120 requisições no perfil fixo;
- 120 respostas bem-sucedidas;
- p50 de 608,099 ms, p95 de 811,166 ms e p99 de 1.120,635 ms;
- aumento de três reinícios durante a janela;
- decisão: `FAIL`;
- razões: `latency_p95_above_threshold` e
  `restart_increase_above_threshold`.

A decisão é válida mesmo com 100% de sucesso HTTP: o mecanismo avalia também
latência e saúde dos workloads. Durante a execução, o `emailservice` apresentou
falhas de liveness e reinícios. Não houve consulta ao snapshot operacional.

Depois da coleta, todos os recursos do namespace `staging` foram removidos e os
contadores da quota retornaram a zero.

Esta é uma validação inicial do mecanismo, não uma observação da comparação
principal. As candidatas de avaliação serão opacas e seguirão o
[`protocolo revisado`](../../protocol/README.md). A versão definitiva dos
limiares será congelada antes da geração dos resultados, sem consultar os
rótulos ou o desempenho do corpus.
