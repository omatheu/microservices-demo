# Evidências de ciclos PDT

## Piloto pareado com a CI/CD convencional

`pdt-engineering-artifact-binding-v2-r1-20260920T071314Z` é o primeiro ciclo de
engenharia que consumiu uma decisão convencional selada e executou exatamente o
mesmo digest do staging. As duas alternativas implantáveis usaram a mesma
carga: 60 segundos de aquecimento, 120 amostras determinísticas, 10 checkouts
válidos, 2 caminhos negativos e o load generator fixo.

| Alternativa | Perfil | Checkout | Negativos | Locust | p95/p99 geral | p95/p99 checkout | Decisão |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `deploy-as-is` | 120/120 | 10/10 | 2/2 | 363/363 | 744,811/1.334,267 ms | 1.084,001/1.084,001 ms | segura |
| `capacity-safe` | 120/120 | 10/10 | 2/2 | 348/348 | 717,389/904,618 ms | 776,844/776,844 ms | segura |

Como `deploy-as-is` satisfez todos os limiares, a política escolheu a ação de
menor custo e emitiu `approve`, confiança 0,9. O gate combinado ficou em
`awaiting-human-confirmation`, com `operational_mutation_performed: false`. O
namespace `pdt` foi limpo e o deployment operacional não foi alterado.

Esse piloto testa comparabilidade e encadeamento, não utilidade incremental: a
candidata era segura e conhecida durante a implementação, os limiares ainda
são de engenharia e não houve oráculo independente.

## Rodada exploratória do executor

`pdt-current-20260920T025910Z` validou tecnicamente a execução serial de três
alternativas, a carga sincronizada, a coleta e a política prescritiva. Ela
produziu `block`, pois as alternativas implantáveis excederam o p95 congelado.

Essa rodada ocorreu antes da explicitação final de que o objeto geminado é o
`checkoutservice`. Sua alternativa `capacity-safe` alterava `frontend` e
`emailservice`; portanto, ela é mantida como **evidência exploratória da
infraestrutura**, mas não conta como execução experimental definitiva do PDT.

As próximas rodadas devem modificar e recomendar ações somente para o
`checkoutservice`. Dependências podem ser observadas ou receber injeções de
falha para estimular o objeto geminado, mas não são tratadas como objetos do
twin.

## Primeiro ciclo estruturalmente válido do PDT (piloto)

`pdt-current-20260920T033029Z` consumiu o snapshot
`operational-state-20260920T031819Z`, que declara `checkoutservice` como
`twin_object`, e avaliou três alternativas:

| Alternativa | Checkout correto | Checkout p95 | Checkout saudável | Resultado |
| --- | ---: | ---: | ---: | --- |
| `deploy-as-is` | 10/10 | 2.218,288 ms | sim | insegura |
| `capacity-safe` | 10/10 | 763,924 ms | sim | insegura |
| `block` | não aplicável | não aplicável | não aplicável | selecionada |

`capacity-safe` aumentou somente o `checkoutservice` para duas réplicas, CPU de
200m/400m e memória de 128Mi/256Mi. Ela melhorou a latência, mas ainda excedeu
os SLOs congelados de checkout p95 ≤ 600 ms e p99 ≤ 700 ms. O modelo
`empirical-counterfactual-v1` emitiu a decisão prescritiva `block`, com
confirmação humana obrigatória.

Esse ciclo comprova que o mecanismo técnico fecha o fluxo observar, simular e
decidir, mas não estima a vantagem do PDT sobre staging. A candidata, os SLOs e
as alternativas eram conhecidos durante a implementação. Por isso, conforme o
[`protocolo revisado`](../../protocol/README.md), ele é evidência de engenharia
e calibração, não evidência confirmatória da comparação.

As dependências apresentaram instabilidade contextual, mas a política usou
indisponibilidade e reinícios somente do objeto geminado. Os dois ambientes de
implantação foram executados sequencialmente e o namespace `pdt` retornou a
consumo zero ao final.
