# Staging tradicional

O staging representa o mecanismo estático de referência. Ele avalia uma
candidata em configuração fixa e produz apenas `PASS` ou `FAIL`.

Os limiares atuais em [`safety-thresholds.json`](./safety-thresholds.json) são
de engenharia. Foram derivados de três repetições de uma candidata segura por
uma regra predeclarada em [`calibration-plan.json`](./calibration-plan.json):
pior percentil observado, margem de 25% e arredondamento conservador. Antes da
coleta comparativa, eles serão revisados sem consultar o corpus de avaliação e
congelados junto ao
[`protocolo revisado`](../protocol/README.md). O runner não consulta snapshots,
métricas ou evidências do ambiente `operational` durante a decisão.

## Critérios

- sucesso HTTP e Locust de pelo menos 99%;
- p95 geral de no máximo 1.200 ms;
- p99 geral de no máximo 1.550 ms;
- p95 e p99 do checkout de no máximo 1.150 ms;
- nenhuma falha nos checkouts válidos ou nos caminhos negativos;
- nenhum deployment indisponível;
- nenhum aumento de reinícios durante a medição.

O perfil `fixed-round-robin-v1` repete, na mesma ordem, a página inicial, um
produto, o carrinho e a troca de moeda. Em paralelo, o load generator fixo usa
10 usuários e taxa 1. A suíte também realiza 10 checkouts válidos e rejeita um
cartão não suportado e um cartão expirado, exigindo HTTP 500, ausência de
confirmação e preservação do carrinho. A carga é deliberadamente fixa e não é
adaptada ao estado operacional.

No protocolo definitivo, staging e PDT receberão as mesmas invariantes
funcionais e os mesmos SLOs. O staging continuará sem sincronização operacional
e sem exploração contrafactual; ele não será artificialmente enfraquecido pela
remoção de asserções que uma validação tradicional razoável poderia executar.

## Execução

```bash
LOCAL_CI_DECISION=<ci-local-decision.json> REPETITION=1 \
  ./experiment/scripts/run-traditional-staging.sh
```

O identificador é lido da decisão local; `CANDIDATE_ID` pode ser informado
apenas como verificação adicional. Para cada serviço afetado, o runner exige
build, SBOM, scan e publicação aprovados e renderiza a referência
`imagem@sha256:...`. Ele bloqueia ausência, substituição ou divergência de
digest antes de tocar o cluster. Por padrão, aplica o bundle derivado de
`infra/kustomize/staging`, acessa o frontend por port-forward, persiste a
decisão local, o binding e o YAML exato, e remove os workloads no final. Use
`KEEP_STAGING=true` somente durante diagnóstico supervisionado.
