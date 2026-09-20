# Análise confirmatória pareada

`analyze-confirmatory-results.py` implementa o plano estatístico pré-registrado
sem depender de bibliotecas externas. A unidade de análise é a candidata depois
da agregação das repetições pelo oráculo.

O analisador calcula:

- taxa de aprovação insegura do controle e do tratamento;
- intervalos binomiais exatos bilaterais de 95%;
- diferença pareada de risco e redução absoluta de risco;
- teste exato bilateral de McNemar sobre os pares discordantes;
- sensibilidade, especificidade, acurácia balanceada e matrizes de confusão;
- escapes convencionais prevenidos ou introduzidos pelo PDT;
- bloqueios e reconfigurações desnecessários em candidatas seguras;
- concordância da ação com o oráculo e diferença de custo da ação;
- mediana, quartis inclusivos, intervalo interquartil e amplitude das métricas
  contínuas fornecidas.

## Travas metodológicas

Por padrão, a execução exige protocolo `frozen`, coleta confirmatória habilitada,
hash exato do protocolo, quantidade declarada de candidatas, identificadores
opacos, coleção marcada como completa e adjudicações elegíveis do oráculo.
Candidatas inconclusivas ou excluídas são relatadas e não substituídas.

`--allow-draft` existe somente para autotestes e pilotos de engenharia. Sua saída
é marcada como `engineering-dry-run` e `confirmatory_eligible: false`.

Uso após o congelamento e a coleta completa:

```bash
./experiment/scripts/analyze-confirmatory-results.py \
  --protocol experiment/protocol/protocol-v1.json \
  --dataset <candidate-level-dataset.json> \
  --output <confirmatory-analysis.json>
```

O dataset contém `protocol_id`, `protocol_sha256`, `collection_complete: true`
e exatamente uma entrada por candidata declarada. Cada entrada reúne as
decisões de controle e tratamento e a adjudicação do oráculo; métricas contínuas
opcionais ficam em `control.continuous_metrics` e
`treatment.continuous_metrics`.
