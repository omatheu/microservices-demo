# Análise confirmatória pareada

`analyze-confirmatory-results.py` implementa o plano estatístico pré-registrado
sem depender de bibliotecas externas. A unidade de análise é a candidata depois
da agregação das repetições pelo oráculo.

`compose-analysis-dataset.py` precede o analisador. Ele exige um manifesto de
coleta completo, confere o conjunto de IDs do corpus público e valida por
SHA-256 cada decisão convencional, decisão PDT, gate e adjudicação do oráculo.
Candidatas bloqueadas pelo controle herdam corretamente o bloqueio no
tratamento sem fabricar uma execução PDT.

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

A fidelidade preditiva é produzida antes dessa composição pelo par
`calculate-pdt-fidelity.py` e `aggregate-pdt-fidelity.py`. O primeiro compara
uma previsão e uma observação seladas da mesma alternativa/repetição; o segundo
exige cobertura completa das alternativas e repetições e somente então gera o
agregado no nível da candidata. Esse artefato preserva a unidade experimental
e será incorporado ao manifesto da coleta final, em vez de contabilizar cada
repetição como amostra independente.

## Travas metodológicas

Por padrão, a execução exige protocolo `frozen`, coleta confirmatória habilitada,
hash exato do protocolo, quantidade declarada de candidatas, identificadores
opacos, coleção marcada como completa e adjudicações elegíveis do oráculo.
Candidatas inconclusivas ou excluídas são relatadas e não substituídas.

`--allow-draft` existe somente para autotestes e pilotos de engenharia. Sua saída
é marcada como `engineering-dry-run` e `confirmatory_eligible: false`.

Uso após o congelamento e a coleta completa:

```bash
./experiment/scripts/compose-analysis-dataset.py \
  --repo-root . \
  --protocol experiment/protocol/protocol-v1.json \
  --public-corpus <public-corpus.json> \
  --collection-manifest <collection-manifest.json> \
  --output <candidate-level-dataset.json>

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

No manifesto de coleta, cada evidência é declarada como
`{"path":"caminho/relativo.json","sha256":"..."}`. Caminhos absolutos,
travessia com `..`, hashes divergentes, candidatos ausentes ou evidência PDT
para uma candidata já bloqueada pelo controle são recusados.
