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
