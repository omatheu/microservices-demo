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
prescritiva já existem como scripts executáveis do experimento. Eles ainda não
estão empacotados como um runtime Kubernetes autônomo: esse artefato será o
`checkout-pdt-controller`, executado sob demanda para não manter capacidade
ociosa. Até esse empacotamento, a implementação deve ser descrita como o motor
batch do PDT, e não como um serviço já implantado.

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
