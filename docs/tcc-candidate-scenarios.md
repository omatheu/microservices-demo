# Catálogo de cenários candidatos — CI/CD convencional e PDT

> **Status:** catálogo de desenho, ainda não congelado.
>
> Nenhum item desta lista é evidência de que o PDT será superior. O corpus será
> gerado por regras e sementes predefinidas; o primeiro gate que detectar cada
> candidata fará parte do resultado.

## Princípio de seleção

Não serão escolhidas somente candidatas que já se sabe que escapam de staging.
O corpus precisa conter:

- mudanças seguras, para medir bloqueios desnecessários;
- falhas óbvias que uma CI/CD competente deve detectar;
- falhas funcionais e não funcionais plausíveis;
- efeitos independentes do contexto e efeitos dependentes de estado/carga;
- mudanças no serviço geminado, nas dependências do caminho de checkout e na
  infraestrutura que condiciona esse caminho.

O PDT continua parcial: ele representa o `checkoutservice`. Uma candidata pode
alterar `paymentservice`, `currencyservice`, `cartservice`, `shippingservice` ou
a infraestrutura, desde que o resultado avaliado seja o impacto observado e
previsto sobre o checkout.

## O que cada cenário realmente compara

O comparador não é o namespace `staging` isoladamente. Para toda candidata, a
condição de controle é a **esteira CI/CD convencional completa**, e staging é
apenas um de seus gates. A condição de tratamento reutiliza integralmente essa
decisão e acrescenta o PDT:

```text
candidata opaca e artefato imutável
  -> fonte, unidade, segurança, dependências, build, SBOM e scan
  -> manifests, IaC, políticas, integração e contratos
  -> staging efêmero: readiness, smoke, E2E, negativos e carga fixa
  -> decisão convencional selada (controle)
       -> se aprovada: snapshot + modelo + contrafactuais + decisão PDT
  -> decisões seladas
  -> oráculo independente e mais amplo
```

Consequentemente, nenhum cenário será chamado antecipadamente de “falha que
passa em staging”. Isso só pode ser afirmado depois da execução. Antes dela,
existe apenas uma **lacuna plausível de cobertura**. O primeiro gate que
detectar a candidata é parte do dado experimental, inclusive quando for lint,
SAST, testes unitários, contrato ou staging.

| Etapa | O que deve detectar | Papel na comparação |
| --- | --- | --- |
| CI de fonte e segurança | compilação, unidade, segredo sintético, SAST e dependência vulnerável | demonstra que o controle convencional é real e não foi enfraquecido |
| Artefato, configuração e IaC | imagem, SBOM, vulnerabilidades, schema e políticas de infraestrutura | detecta candidatas inválidas antes de consumir staging |
| Integração e contratos | incompatibilidades e invariantes semânticas conhecidas | oferece ao controle as mesmas regras públicas de correção |
| Staging | comportamento da candidata sob E2E, falhas negativas e carga fixa congelada | observa execução real sem conhecer o estado operacional atual |
| PDT | comportamento condicionado ao snapshot permitido e a alternativas contrafactuais | mede a utilidade incremental do modelo, do estado e da prescrição |
| Oráculo | matriz oculta mais ampla depois que as decisões estiverem seladas | determina o resultado observado; não é um terceiro mecanismo de deploy |

## Seleção dos cenários sem favorecer o PDT

Cada operadora é definida por três eixos antes da coleta:

1. **camada alterada:** código/regra de negócio, dependência, configuração ou
   infraestrutura;
2. **condição de ativação:** independente, classe de entrada, concorrência,
   cauda de latência, duração ou coexistência de versões;
3. **oportunidade plausível de detecção:** CI estática, contratos, staging,
   contexto operacional do PDT ou mais de uma delas.

O terceiro eixo serve para balancear o corpus, não para determinar o resultado.
Uma candidata não pode ser removida porque a CI/CD a bloqueou, nem incluída
porque um piloto mostrou que somente o PDT a detecta. Parâmetros e ordem serão
derivados por semente, os mecanismos verão apenas IDs opacos e o rótulo final
virá da observação do oráculo, não da intenção da mutação.

## Controles

| ID | Candidata | Resultado esperado do desenho |
| --- | --- | --- |
| `CTRL-SAFE-01` | refatoração equivalente ou alteração apenas de mensagem de log | deve ser aprovada; mede falso positivo de cada gate |
| `CTRL-SAFE-OUTSIDE-01` | refatoração equivalente no `recommendationservice`, fora da fronteira decisória do twin | deve ser aprovada; mede se o PDT extrapola indevidamente sua fronteira |
| `CTRL-CI-01` | erro de compilação, teste unitário quebrado ou manifest inválido | deve ser bloqueada antes de staging; confirma que a CI não é decorativa |
| `CTRL-SEC-01` | fixture sintética detectável por SAST, scanner de dependência ou política Kubernetes | deve ser bloqueada pela segurança convencional; não se espera vantagem do PDT |

## Infraestrutura e configuração

| ID | Alteração candidata | Lacuna plausível a exercitar, sem garantia de escape | Hipótese específica do PDT | Verificação do oráculo |
| --- | --- | --- | --- | --- |
| `INF-CPU-01` | reduzir `resources.limits.cpu` do `checkoutservice` dentro de valores válidos | build, policy e uma carga curta podem passar | o snapshot de carga e a exploração de picos podem prever throttling e cauda de latência | matriz de carga com p95/p99, throttling, erros e disponibilidade |
| `INF-MEM-01` | reduzir memória ou introduzir retenção limitada por requisição | a janela curta pode terminar antes da pressão acumulada | o modelo pode avaliar duração/carga compatíveis com o estado observado | carga prolongada, working set, OOM e reinícios |
| `INF-REPLICA-01` | escalar o `checkoutservice` para zero réplicas, mantendo manifest válido | não deve passar por um staging competente; funciona como controle positivo da capacidade do comparador | o PDT não precisa produzir ganho incremental neste caso | indisponibilidade determinística do checkout; restauração para uma réplica |
| `INF-PROBE-01` | tornar liveness/readiness excessivamente agressivos | dependências estáveis no staging não excedem o timeout | o PDT pode combinar a política com a distribuição observada de latência | injeção controlada de cauda, reinícios e indisponibilidade |
| `INF-TIMEOUT-01` | reduzir timeout ou orçamento de retry para pagamento/frete | chamadas saudáveis e rápidas passam | o estado das dependências pode indicar que a configuração falhará na cauda | perfis de latência e erro, sucesso funcional e duplicidade |
| `INF-ROLLOUT-01` | alterar `maxUnavailable`, `maxSurge` ou compatibilidade durante rollout | um deploy limpo só observa a versão final | o PDT pode materializar coexistência entre versões e perda temporária de capacidade | rollout controlado, disponibilidade e compatibilidade old/new |
| `INF-CONCURRENCY-01` | reduzir pool ou concorrência interna do checkout | smoke sequencial não satura o limite | o PDT pode usar a concorrência observada para prever fila e timeout | carga concorrente em degraus e saturação |

## Regras funcionais do checkout e pagamento

| ID | Alteração candidata | Lacuna plausível a exercitar, sem garantia de escape | Hipótese específica do PDT | Verificação do oráculo |
| --- | --- | --- | --- | --- |
| `FUNC-AMOUNT-01` | omitir frete, quantidade ou nanos do valor cobrado em uma classe de entrada | uma combinação fixa de carrinho/moeda pode não ativar a falha | estado e distribuição de entradas podem orientar casos contrafactuais relevantes | spy de pagamento e cálculo independente para múltiplos itens/moedas |
| `FUNC-PAYMENT-01` | retornar sucesso sem uma cobrança válida sob condição controlada | E2E que verifica apenas a página de sucesso não observa o efeito financeiro | o modelo de estado pode exigir a transição `pedido → cobrança → envio` | correlação entre pedido, valor, transação e resposta ao usuário |
| `FUNC-RETRY-01` | duplicar cobrança quando ocorre timeout/retry | caminho feliz sem timeout executa uma vez | latência observada pode levar o PDT a simular retry e testar idempotência | contagem de cobranças por pedido sob falhas transitórias |
| `FUNC-ERROR-01` | engolir falha do pagamento e continuar o checkout | staging sem fault injection não alcança o ramo | o PDT pode avaliar falhas de dependência coerentes com o estado observado | falha determinística do pagamento; nenhuma confirmação/envio permitido |
| `FUNC-SIDEFX-01` | esvaziar carrinho ou confirmar pedido antes da conclusão exigida | o caminho feliz preserva a aparência de sucesso | o modelo de transições pode identificar ordem inválida de efeitos | auditoria da ordem de cobrança, envio, carrinho e confirmação |
| `FUNC-COND-01` | lógica adversarial ativada por moeda, tamanho de carrinho ou outra faixa predefinida | a suíte fixa pode não conter o gatilho | a geração orientada pelo snapshot pode priorizar faixas operacionalmente relevantes | matriz independente de entradas; gatilho definido antes do snapshot |
| `FUNC-DEGRADE-01` | adicionar trabalho computacional limitado somente acima de uma faixa de carrinho ou concorrência | unidade e caminho feliz continuam corretos; uma carga média curta pode não saturar | o PDT pode explorar faixas coerentes com o snapshot e comparar capacidade/replicação | degraus independentes de carga, CPU, throttling e latência de cauda |
| `FUNC-AVAIL-01` | rejeitar deterministicamente uma fração pequena de checkouts a partir de um hash opaco da entrada | poucas amostras podem não atingir a classe afetada | contrafactuais gerados sobre a distribuição observada podem aumentar a cobertura da classe | conjunto independente e predeclarado de entradas, taxa de sucesso e correção financeira |

## Dependências e contratos

| ID | Alteração candidata | Lacuna plausível a exercitar, sem garantia de escape | Hipótese específica do PDT | Verificação do oráculo |
| --- | --- | --- | --- | --- |
| `DEP-PAYMENT-SEM-01` | resposta de pagamento continua válida no protobuf, mas muda uma semântica usada pelo checkout | validação estrutural de contrato passa | o modelo funcional pode verificar a relação entre resposta e estado da compra | contrato semântico e transação ponta a ponta |
| `DEP-CURRENCY-01` | alterar arredondamento/conversão em combinações raras | amostras usuais continuam corretas | distribuição observada de moedas pode orientar contrafactuais | cálculo independente de totais e arredondamento |
| `DEP-TAIL-01` | nova versão da dependência aumenta apenas a latência de cauda sob concorrência | médias e smoke tests permanecem aceitáveis | o PDT usa perfil observado e compara timeout/recursos/replicação | p95/p99 por concorrência e taxa de timeout |
| `DEP-MIXED-01` | mudança compatível isoladamente, mas incompatível com versões coexistentes | staging troca todos os componentes de uma vez | o PDT materializa combinações de versão durante rollout | matriz consumidor/provedor old/new |

## Segurança e limites do PDT

Alguns cenários devem demonstrar que o PDT não substitui ferramentas
tradicionais. Segredo em código, dependência vulnerável conhecida, imagem sem
proveniência ou RBAC excessivo devem ser detectados pelos gates de segurança e
política. Se o PDT for o primeiro a apontá-los, a esteira de controle está
subdimensionada.

Os cenários adversariais são sintéticos e confinados. Não podem exfiltrar dados,
usar credenciais reais, obter persistência, ampliar privilégios nem acessar
alvos externos.

## Escopo confirmatório v1 atualmente proposto

O protocolo candidato contém 18 candidatas. Todas as 13 operadoras abaixo já
possuem materialização determinística, mas ainda precisam ser validadas de
ponta a ponta antes do congelamento:

| Grupo | Operadoras | Candidatas propostas | Função metodológica |
| --- | --- | ---: | --- |
| mudanças seguras | `CTRL-SAFE-01`, `CTRL-SAFE-OUTSIDE-01` | 4 | medir bloqueios desnecessários e respeito à fronteira do twin |
| falhas que a CI convencional deve detectar | `CTRL-CI-01`, `CTRL-SEC-01` | 4 | comprovar força dos gates de fonte, segurança e política |
| infraestrutura/configuração | `INF-CPU-01`, `INF-REPLICA-01`, `INF-TIMEOUT-01` | 4 | cobrir capacidade, disponibilidade óbvia e cauda de dependência |
| regra de negócio e comportamento | `FUNC-AMOUNT-01`, `FUNC-ERROR-01`, `FUNC-COND-01`, `FUNC-DEGRADE-01` | 4 | cobrir valor, erro, classe de entrada e degradação sob concorrência |
| dependências | `DEP-CURRENCY-01`, `DEP-TAIL-01` | 2 | cobrir semântica financeira e latência de cauda |

`INF-MEM-01`, `INF-PROBE-01`, `INF-ROLLOUT-01`, `INF-CONCURRENCY-01`,
`FUNC-PAYMENT-01`, `FUNC-RETRY-01`, `FUNC-SIDEFX-01`, `FUNC-AVAIL-01`,
`DEP-PAYMENT-SEM-01` e `DEP-MIXED-01` permanecem como backlog de extensão. Eles
não podem ser acrescentados à coleta v1 depois de resultados serem vistos; sua
inclusão exige congelá-los antes da geração do corpus ou criar um novo protocolo.

No cenário de CPU, `100m` significa um limite equivalente a um décimo de CPU,
e não “um pod com 0,1 vCPU física dedicada”. Kubernetes aplica quota de tempo
de CPU e pode causar throttling. A alteração será avaliada tanto pela esteira
convencional quanto pelo PDT; se a carga fixa do staging detectar a regressão,
ela não conta como ganho incremental do PDT.

## Estratificação contra viés de seleção

O corpus deve ser sorteado por blocos definidos antes dos resultados. Não se
deve descartar uma candidata porque staging a detectou, nem escolher apenas
gatilhos que o PDT já demonstrou alcançar.

| Bloco | Papel na comparação | Exemplos |
| --- | --- | --- |
| segura | medir bloqueios desnecessários | `CTRL-SAFE-01`, aumento seguro de recursos, refatoração equivalente |
| detectável na CI | comprovar força do comparador | `CTRL-CI-01`, `CTRL-SEC-01`, quebra protobuf |
| detectável no staging | medir E2E/carga convencional | erro funcional comum, latência sustentada e indisponibilidade evidente |
| potencialmente dependente de contexto | medir utilidade incremental sem pressupor superioridade | `INF-TIMEOUT-01`, `DEP-TAIL-01`, `FUNC-COND-01` |
| limite do PDT | medir falsos positivos e limitações | mudança segura fora da fronteira do twin ou cenário sem ganho do snapshot |

O manifesto com operador, parâmetros, semente e rótulo esperado pertence ao
oráculo e fica inacessível à CI, ao staging e ao PDT até que as duas decisões
sejam persistidas. As invariantes públicas e os requisitos são iguais para os
dois mecanismos; o PDT difere apenas por consumir o snapshot permitido,
manter um modelo do `checkoutservice` e explorar alternativas contrafactuais.

O piloto já executado com limite de CPU menor confirma a viabilidade técnica do
operador `INF-CPU-01`, mas não pode ser reutilizado como amostra. A avaliação
principal precisa de novas instâncias opacas, com parâmetros gerados pelo
protocolo congelado.

## Classificação dos resultados

Para cada candidata, registrar:

- primeiro gate que a bloqueou;
- decisão final da CI/CD convencional;
- decisão final da mesma CI/CD acrescida do PDT;
- rótulo e melhor ação determinados pelo oráculo;
- requisito violado;
- duração e custo de cada etapa.

Uma candidata é um **escape convencional** quando CI/CD e staging aprovam, mas
o oráculo a classifica como prejudicial. Ela é uma **detecção incremental do
PDT** quando esse escape é bloqueado ou reconfigurado de forma segura pelo PDT.
Uma candidata segura aprovada pela esteira e bloqueada pelo PDT é um **bloqueio
incremental desnecessário**.
