# Evidências do gate combinado

Cada execução pareada registra a decisão convencional selada, a decisão PDT,
o estado do gate humano e os logs de orquestração. Diretórios timestampados são
deliberadamente ignorados pelo Git e enviados como artefatos de retenção curta
pelos workflows do GitHub.

O piloto local `gate-current-20260920T034300Z` terminou em
`awaiting-human-confirmation` e registrou
`operational_mutation_performed: false`. Ele validou o encadeamento técnico,
mas não integra a análise confirmatória porque a candidata era conhecida e as
políticas ainda não estavam congeladas.

Em 21/09/2026 foi preparado o gate humano protegido do GitHub. O workflow
somente cria um recibo depois de o ambiente `tcc-deployment-approval` ser
aprovado; a identidade do revisor e o comentário são lidos do endpoint oficial
de histórico de aprovações e selados junto dos hashes de `gate.json` e
`deployment-action.json`. O job não possui `id-token`, não recebe secrets do GCP
e não executa a ação. A evidência runtime continua pendente até o workflow ser
incorporado à branch `main` e executado em um piloto autorizado.
