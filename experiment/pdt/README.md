# Partial Digital Twin

O objeto geminado é explicitamente o `checkoutservice`. Os demais
microserviços, inclusive o `paymentservice`, são executados como dependências,
contexto e carga, mas não fazem parte da fronteira decisória do modelo.

## Identidade do componente

O componente de software do twin se chama **`checkout-pdt-controller`** e
pertence ao namespace **`pdt-system`**. Ele não é uma ferramenta de
observabilidade: consome telemetria como entrada, mantém a representação do
estado, coordena contrafactuais, executa o modelo e emite ações prescritivas.

Separação dos planos:

| Namespace | Responsabilidade |
| --- | --- |
| `observability` | obter e persistir telemetria/evidências; não decide |
| `pdt-system` | controlar o twin, prever, selecionar e auditar decisões |
| `pdt` | executar workloads contrafactuais efêmeros |
| `staging` | validação tradicional estática de referência |
| `oracle` | observar resultados depois que controle e tratamento forem selados; não decide o deploy |
| `operational` | instância observada e validação real controlada |

Essa separação é parte da hipótese arquitetural: observabilidade descreve o que
aconteceu ou está acontecendo; o PDT usa essa descrição para manter estado,
simular o que poderia acontecer e prescrever uma ação.

## Estado de implementação

O namespace `pdt-system` já existe no cluster, com quota própria e nenhum pod
permanente. A captura de estado, a execução contrafactual, o modelo e a decisão
prescritiva são coordenados pela aplicação
[`controller/checkout_pdt_controller.py`](./controller/checkout_pdt_controller.py).
O runtime possui Dockerfile reprodutível e gerador de Job isolado sob demanda;
a imagem ainda não foi publicada e o Job ainda não foi aplicado no cluster.
Até essa validação, ele deve ser descrito como controlador batch empacotado,
não como serviço permanentemente implantado.

O vínculo da instância física/digital é declarado em
[`source-binding.json`](./source-binding.json). O namespace `operational` é a
fonte observada e `pdt` é o ambiente isolado onde alternativas serão
materializadas.

Crie um snapshot com:

```bash
./experiment/scripts/capture-pdt-source-state.sh
```

O snapshot contém identificadores reais do cluster e namespace, versões dos
recursos, imagens, réplicas, requests/limits, variáveis de ambiente, perfil do
load generator, quotas, eventos e uma janela do Cloud Monitoring. O arquivo
`pdt-input-state.json` é a entrada versionada para as etapas de materialização,
previsão e decisão; elas não devem consultar novamente o operacional durante a
avaliação de uma mesma candidata.

Execute o ciclo somente depois de selar a decisão convencional:

```bash
CONVENTIONAL_DECISION=<conventional-decision.json> \
  CANDIDATE_FILE=<candidate.json> \
  ./experiment/scripts/run-pdt-cycle.sh
```

O controlador exige que o controle tenha aprovado a mesma candidata. Em cada
alternativa, primeiro sincroniza o estado operacional, depois aplica a
configuração contrafactual e, por último, fixa novamente os mesmos digests que
o staging executou. A decisão PDT registra o hash da decisão convencional e as
referências imutáveis; assim, o código testado não pode ser trocado por uma
configuração alternativa ou pelo snapshot operacional.

O runner lê aquecimento, quantidade e intervalo das amostras do mesmo arquivo
de limiares usado pelo staging. Ele repete também os checkouts válidos, os dois
caminhos negativos e o tráfego Locust, e aplica a mesma política de sucesso,
latência, disponibilidade e reinícios. Essa simetria impede atribuir ao PDT uma
vantagem causada simplesmente por receber uma suíte de testes melhor.

## Fidelidade pós-decisão

A previsão não é tratada como verdadeira apenas porque o PDT produziu uma
decisão. Depois de a decisão ficar selada, o oráculo isolado produz uma
observação para cada alternativa e repetição. O utilitário
[`../scripts/calculate-pdt-fidelity.py`](../scripts/calculate-pdt-fidelity.py)
compara essa observação com a entrada correspondente de
`alternatives_evaluated`, exigindo a mesma candidata, alternativa, repetição e
modo de execução.

A política [`fidelity-policy.json`](./fidelity-policy.json) fixa as métricas e
as fórmulas antes da coleta: erro assinado, absoluto e relativo para taxa de
sucesso, p95/p99 do checkout, indisponibilidade e reinícios, além da
concordância de classificação. O rótulo pretendido da mutação não é usado. O
resultado é somente pós-decisão e registra
`model_mutation_performed: false` e `recalibration_allowed: false`; dados
confirmatórios jamais podem retroagir sobre o modelo avaliado. A evidência
quantitativa continua pendente das execuções autorizadas do oráculo.

Após as três repetições de todas as alternativas implantáveis, agregue sem
abrir espaço para seleção manual de resultados:

```bash
python3 experiment/scripts/aggregate-pdt-fidelity.py \
  --protocol experiment/protocol/protocol-v1.json \
  --policy experiment/pdt/fidelity-policy.json \
  --candidate-definition <candidate-definition.json> \
  --report <alternativa-a-r1/pdt-fidelity.json> \
  --report <alternativa-a-r2/pdt-fidelity.json> \
  --report <alternativa-a-r3/pdt-fidelity.json> \
  --report <alternativa-b-r1/pdt-fidelity.json> \
  --report <alternativa-b-r2/pdt-fidelity.json> \
  --report <alternativa-b-r3/pdt-fidelity.json> \
  --output <candidate-fidelity.json>
```

O comando normal exige desenho congelado. `--allow-draft` existe somente para
pilotos de engenharia e nunca produz evidência confirmatória elegível.
O arquivo resultante entra no manifesto de coleta como `pdt_fidelity`; o
compositor e o analisador confirmatório recusam cobertura parcial, identidade
divergente ou tentativa de tratar suas repetições como amostras independentes.
