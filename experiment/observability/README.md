# Observabilidade do experimento

A coleta usa o Cloud Monitoring gerenciado que já acompanha o GKE Autopilot.
Não há uma segunda instalação de Prometheus ou Grafana e, portanto, não são
criados pods adicionais somente para observabilidade.

As métricas canônicas estão em [`canonical-metrics.json`](./canonical-metrics.json).
O script [`export-observability-window.sh`](../scripts/export-observability-window.sh)
consulta a API, preserva as respostas brutas, cria um CSV normalizado e salva
snapshots do Kubernetes. O diretório de cada execução fica fora dos pods, em
`experiment/evidence/observability/<run-id>`.

## Uso

```bash
SCENARIO_ID=baseline \
CANDIDATE_ID=current \
ALTERNATIVE_ID=as-is \
REPETITION=1 \
ENVIRONMENT=operational \
NAMESPACE=operational \
LOOKBACK_MINUTES=15 \
./experiment/scripts/export-observability-window.sh
```

Também é possível informar `START_TIME` e `END_TIME` em UTC no formato RFC
3339. Os mesmos campos e consultas são usados para `operational`, `staging` e
`pdt`.

## Custos

Cada execução registra duração, CPU-request-hora, memória-request-GiB-hora e o
orçamento do experimento. O custo monetário atribuível à janela permanece
`null` enquanto não existir uma exportação detalhada do Cloud Billing. Isso é
deliberado: o relatório não transforma preço de tabela em custo observado.
Uma exportação de faturamento pode ser associada posteriormente pelo projeto,
intervalo e identificadores da execução.
