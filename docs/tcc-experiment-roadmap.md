# Roadmap e estado do experimento PDT

> **Documento vivo:** acompanhamento da implementação do experimento definido em
> [`tcc-experiment-plan.md`](./tcc-experiment-plan.md).
>
> **Última verificação:** 20 de setembro de 2026.

## Objetivo do experimento

Construir e avaliar um **Partial Digital Twin preditivo e prescritivo para
suporte semiautônomo à decisão pré-deployment**, medindo o valor incremental de
adicioná-lo a uma esteira convencional completa de CI/CD com staging.

**Objeto geminado pelo PDT:** `checkoutservice`. Os demais serviços, inclusive
`paymentservice`, são contexto executável, dependências observadas ou geradores
de carga; não são objetos do modelo e da política prescritiva. A definição completa está na seção
“Fronteira explícita do gêmeo parcial” do plano principal.

O resultado principal não será somente desempenho. O experimento deve medir a
qualidade das decisões de:

- aprovar uma versão candidata;
- bloquear uma mudança insegura;
- recomendar ou aplicar uma reconfiguração sob supervisão;
- preservar mudanças seguras sem bloqueios desnecessários.

## Critérios obrigatórios para caracterizar o PDT

O protótipo só será considerado um PDT se demonstrar todos estes elementos:

- [x] vínculo explícito com a instância `operational`;
- [x] sincronização de carga, configuração e recursos observados;
- [x] modelo executável para simular versões ou configurações candidatas;
- [x] comparação de duas ou três alternativas contrafactuais;
- [x] previsão de latência, erros e correção funcional;
- [x] decisão prescritiva: aprovar, bloquear ou reconfigurar;
- [ ] execução semiautônoma no pipeline, com confirmação humana;
- [ ] comparação entre previsão e resultado operacional real;
- [ ] registro do erro de previsão para recalibração;
- [ ] avaliação contínua da fidelidade do twin.

Sem esse conjunto, o resultado deve ser descrito como staging adaptativo, e não
como Partial Digital Twin.

## Estado atual

### Concluído

- [x] Projeto Google Cloud `microservices-demo-tcc` configurado.
- [x] Terraform separado da infraestrutura original da demonstração.
- [x] Cluster GKE Autopilot `online-boutique-experiment` em `us-central1`.
- [x] Namespaces cloud `operational`, `staging`, `pdt`, `pdt-system` e `observability`.
- [x] Definição local do namespace isolado `oracle`, sem LoadBalancer e com quota própria; aplicação cloud ainda não autorizada.
- [x] Quotas de CPU, memória, pods e Load Balancers por namespace.
- [x] Orçamento de custo bruto de R$1.751,10.
- [x] Margem de R$10 preservada sobre R$1.761,10 de crédito informado.
- [x] Período do orçamento alinhado à expiração dos créditos em 19/12/2026.
- [x] Alertas financeiros em 25%, 50%, 75%, 90%, 95% e 100%.
- [x] Overlay Kustomize do ambiente operacional.
- [x] Políticas de rede da Online Boutique aplicadas.
- [x] Online Boutique completa no namespace `operational`.
- [x] Doze deployments disponíveis.
- [x] Load generator com dez usuários e taxa configurada em 1.
- [x] Frontend validado externamente com HTTP 200.
- [x] Quotas verificadas com consumo inicial de 1,57 CPU e 1.859 MiB em requests.
- [x] Overlays de staging e PDT preparados sem Load Balancer e sem carga contínua.

### Ainda não concluído

- [x] captura persistente da linha de base operacional;
- [x] plataforma de observabilidade do experimento;
- [x] definição formal dos SLOs e limiares de segurança;
- [ ] esteira convencional completa de CI/CD com staging;
- [x] runner inicial de staging para pilotos de engenharia;
- [x] sincronizador de estado operacional para o PDT;
- [x] executor de alternativas contrafactuais;
- [x] modelo preditivo inicial;
- [x] política prescritiva de seleção de ação;
- [x] namespace isolado `pdt-system` para o plano de controle do twin;
- [x] empacotar a lógica existente como o runtime `checkout-pdt-controller`;
- [ ] executar o controlador sob demanda no namespace `pdt-system`;
- [ ] gate semiautônomo no pipeline;
- [ ] congelar e versionar o protocolo experimental revisado;
- [x] implementar os 13 operadores do corpus candidato e validar todos os seus espaços de parâmetros;
- [x] gerar uma prévia opaca inelegível para a coleta confirmatória;
- [ ] gerar o corpus opaco definitivo, somente após congelamento;
- [x] implementar o oráculo de validação independente;
- [ ] execução pareada e repetida das candidatas do corpus;
- [ ] validação das previsões no ambiente-oráculo isolado;
- [ ] consolidação estatística e análise dos resultados;
- [ ] pacote reproduzível de evidências do TCC.

## Fases restantes

### Fase 1 — Linha de base operacional

Objetivo: representar o comportamento normal da instância operacional.

- [x] definir uma janela de aquecimento;
- [x] capturar taxa de requisições e falhas;
- [x] capturar latências p50, p95 e p99;
- [x] capturar CPU e memória por serviço;
- [x] registrar réplicas, requests, limits e configuração;
- [x] registrar reinícios, indisponibilidades e eventos;
- [x] salvar snapshots com timestamp e identificador da execução;
- [x] executar repetições para estimar variação natural.

**Critério de saída:** baseline reproduzível, com formato versionado e métricas
suficientes para comparar previsão e realidade.

**Estado:** concluído para validação inicial com três repetições, 180 sondas HTTP
e 818 requisições Locust, sem falhas. O relatório está em
[`../experiment/evidence/baseline/README.md`](../experiment/evidence/baseline/README.md).
Também foram validadas 60 transações completas do objeto geminado, sem falhas,
conforme
[`../experiment/evidence/checkout-baseline/README.md`](../experiment/evidence/checkout-baseline/README.md).
As execuções definitivas usarão janelas maiores porque, com 60 amostras por
repetição, o p99 ainda é sensível a valores extremos.

### Fase 2 — Observabilidade e evidências

Objetivo: coletar as mesmas métricas em `operational`, `staging` e `pdt`.

- [x] selecionar Cloud Monitoring gerenciado ou Prometheus controlado;
- [x] definir consultas canônicas para cada métrica;
- [x] criar identificadores de cenário, candidata, alternativa e repetição;
- [x] persistir resultados fora do ciclo de vida dos pods;
- [x] criar exportação em JSON ou CSV para análise;
- [x] registrar custos e duração de cada execução.

**Critério de saída:** uma execução pode ser reconstruída a partir das
evidências armazenadas.

**Estado:** concluído com Cloud Monitoring gerenciado, sem pods adicionais de
observabilidade. O coletor e as consultas canônicas estão em
[`../experiment/observability/`](../experiment/observability/), e a validação
está documentada em
[`../experiment/evidence/observability/README.md`](../experiment/evidence/observability/README.md).
O registro de custo preserva duração e capacidade-tempo; o custo monetário por
janela permanece explicitamente indisponível até existir exportação detalhada
do Cloud Billing.

### Fase 3 — CI/CD convencional completa com staging

Objetivo: implementar um mecanismo de referência compatível com o que uma
equipe razoavelmente madura usaria antes de produção, sem reduzir o controle a
um simples namespace de staging.

- [x] capturar commit, árvore de origem, candidata e artefato no runner local;
- [x] exigir identidade imutável e árvore limpa na execução confirmatória;
- [x] executar lint, compilação e testes unitários do `checkoutservice`;
- [x] selecionar e validar os serviços alterados no caminho de checkout;
- [x] implementar validação de sincronização e compatibilidade do contrato
  protobuf canônico;
- [x] executar análise de segredos, SAST e dependências no escopo inicial;
- [x] vendorizar o ruleset SAST e verificar seu hash;
- [ ] congelar a política completa depois do protocolo e do corpus;
- [x] construir cada imagem afetada, gerar SBOM e analisar vulnerabilidades;
- [x] publicar artefatos aprovados por digest e vinculá-los ao staging;
- [x] renderizar e validar manifests e IaC sem aplicar recursos;
- [x] bloquear configurações Kubernetes privilegiadas e exposição pública com
  política versionada e autoteste adversarial;
- [x] executar contratos semânticos em memória do caminho de checkout/pagamento;
- [ ] executar integração dos serviços reais e contratos no staging;
- [x] implantar a candidata no namespace `staging`;
- [x] aplicar carga fixa e independente do estado operacional;
- [x] executar E2E funcional, caminhos negativos e desempenho predefinidos;
- [x] calibrar limiares de engenharia por regra predeclarada e execução segura;
- [x] produzir `PASS` ou `FAIL`, com justificativa;
- [x] impedir acesso ao snapshot operacional durante a decisão;
- [x] implementar a consolidação da CI local e do staging em decisão auditável;
- [ ] executar a mesma candidata opaca nos gates locais e no staging;
- [ ] orquestrar a esteira em CI com identidade cloud de curta duração;
- [ ] exigir gate humano antes de qualquer implantação operacional.

**Critério de saída:** uma candidata percorre todos os gates convencionais e
produz uma decisão reproduzível de release. O staging é parte dessa esteira e
não o comparador inteiro.

A especificação detalhada está em
[`tcc-ci-cd-baseline.md`](./tcc-ci-cd-baseline.md).

**Estado:** a parte local da esteira está implementada para os serviços do
caminho de checkout. A execução de engenharia
`ci-engineering-artifact-binding-v2-20260920T063313Z` passou nos 20 gates,
construiu, inventariou, analisou e publicou o `checkoutservice` como digest
imutável. A execução anterior `ci-engineering-protobuf-gate-20260920T060133Z`
validou o gate protobuf sem criar recursos cloud. Ambas permanecem
explicitamente inaptas para evidência confirmatória. O runner, a política e os
testes estão em
[`../experiment/ci/`](../experiment/ci/), e o resumo da execução está em
[`../experiment/evidence/ci-cd/README.md`](../experiment/evidence/ci-cd/README.md).

O ruleset SAST está versionado, protegido por SHA-256 e possui um autoteste
adversarial obrigatório. Os contratos usam doubles gRPC em memória para validar valor cobrado, ordem dos
efeitos e fronteiras de falha de carrinho, catálogo, câmbio, cotação, pagamento,
entrega e e-mail. Adaptadores adicionais foram validados separadamente para Go,
Node, .NET e Python. O seletor bloqueia caminhos críticos desconhecidos. O gate
protobuf compila o contrato com uma versão fixada do `protoc`, compara mudanças
com a base Git, verifica os espelhos semânticos, o subconjunto C# do carrinho e
os descriptors e métodos gRPC gerados. O compositor da decisão convencional
também está implementado e testado: ele
só produz `approve` quando CI local e staging aprovam a mesma candidata e sela
as entradas por hash. O staging `staging-engineering-artifact-binding-v2-r4-
20260920T070010Z` executou esse digest com 120/120 requisições do perfil, 10/10
checkouts válidos e 2/2 caminhos negativos, produzindo uma decisão
convencional selada. Ainda faltam os contratos de falha de dependência com
serviços reais, a política completa congelada, candidatas opacas e a
orquestração confirmatória. Os dados atuais continuam classificados apenas
como piloto de engenharia em
[`../experiment/evidence/staging/README.md`](../experiment/evidence/staging/README.md);
esses dados não integrarão a comparação principal.

### Fase 4 — Núcleo do Partial Digital Twin

Objetivo: fechar o ciclo observar, simular, avaliar e decidir.

- [x] construir o coletor de estado da instância `operational`;
- [x] gerar snapshot versionado para cada decisão;
- [x] replicar no PDT carga, configuração e limites relevantes;
- [x] receber uma versão candidata;
- [x] materializar duas ou três alternativas;
- [x] executar as alternativas de maneira isolada;
- [x] estimar latência, erros e correção funcional;
- [x] calcular confiança da previsão;
- [ ] calcular fidelidade após comparação operacional;
- [x] selecionar uma ação segura;
- [x] emitir decisão estruturada e auditável.

Formato mínimo da decisão:

```json
{
  "candidate": "checkoutservice-v2",
  "snapshot_id": "...",
  "alternatives_evaluated": [],
  "decision": "approve|block|reconfigure",
  "recommended_configuration": {},
  "predicted_metrics": {},
  "confidence": 0.0,
  "rationale": []
}
```

**Critério de saída:** uma candidata resulta em decisão prescritiva derivada do
estado operacional e de alternativas contrafactuais.

**Estado:** núcleo inicial concluído para fins de engenharia. O ciclo pareado
`pdt-engineering-artifact-binding-v2-r1-20260920T071314Z` consumiu uma decisão
convencional selada, executou exatamente o mesmo digest e a mesma carga do
staging, avaliou `deploy-as-is`, `capacity-safe` e `block`, e aprovou
`deploy-as-is`. O piloto anterior `pdt-current-20260920T033029Z` continua útil
apenas como validação estrutural. Evidências e limitações estão em
[`../experiment/evidence/pdt-cycles/README.md`](../experiment/evidence/pdt-cycles/README.md).
Os pilotos não serão usados como evidência da comparação principal, pois as
candidatas e hipóteses eram conhecidas durante a construção. Fidelidade ainda
depende do oráculo controlado na Fase 7.

O runner agora também prepara e executa o `checkout-pdt-controller` como Job
efêmero no namespace `pdt-system`, compara o plano emitido pelo container com o
preflight e exige uma imagem imutável. A identidade GitHub possui um papel
dedicado que permite apenas os recursos necessários a esse Job. O item
“executar o controlador sob demanda” permanece pendente até a publicação por
digest e um piloto cloud explicitamente autorizado comprovarem esse caminho.

### Fase 5 — Gate PDT incremental e semiautônomo

Objetivo: acrescentar a previsão à esteira convencional e orientar uma ação
real, sob supervisão, sem remover nenhum gate preexistente.

- [x] integrar a decisão convencional consolidada e a decisão PDT no software do gate;
- [x] bloquear progressão quando o PDT decidir `block`;
- [x] preparar configuração isolada quando decidir `reconfigure`;
- [ ] solicitar confirmação humana antes do ambiente operacional;
- [ ] aplicar a ação aprovada no ambiente controlado;
- [x] preparar rollback por remoção e verificação do runtime efêmero;
- [x] registrar decisões e estado da intervenção humana;

**Critério de saída:** o pipeline executa a decisão até o gate humano sem
alteração autônoma de produção.

**Estado:** o gate foi refatorado para aceitar somente a decisão convencional
selada; uma decisão isolada de staging é rejeitada. Ele também verifica que o
controle e o PDT executaram os mesmos artefatos imutáveis. Testes automatizados
cobrem aprovação, bloqueios, reconfiguração, identidade de candidata, selo e
substituição de artefato. O piloto pareado chegou a
`awaiting-human-confirmation` sem mutação operacional. O registro histórico
está resumido no
[`README de evidências do gate`](../experiment/evidence/pipeline/README.md) e
continua sendo apenas evidência de piloto. Uma execução completa com candidata
opaca, o caminho real de confirmação humana, a aplicação controlada e o
rollback continuam pendentes.

O pipeline agora também prepara `deployment-action.json` para decisões
`approve` ou `reconfigure`. O arquivo restringe mudanças à fronteira do
`checkoutservice`, vincula candidata, snapshot e decisões por hash e inclui
rollback obrigatório no namespace efêmero `oracle`. Um recibo humano separado
pode aprovar ou rejeitar essa validação, mas não autoriza custo cloud nem
mutação do ambiente operacional. A comprovação de aplicação e cleanup numa
execução autorizada ainda permanece pendente.

### Fase 6 — Protocolo e corpus de avaliação

Objetivo: avaliar os mecanismos em candidatas cujo rótulo não esteja disponível
durante a decisão.

- [ ] congelar requisitos funcionais, SLOs e invariantes comuns;
- [x] definir operadores de mutação sem consultar resultados de avaliação;
- [x] incluir candidatas seguras para medir bloqueios desnecessários;
- [x] incluir falhas funcionais controladas no checkout/pagamento;
- [x] incluir falhas não funcionais de latência, disponibilidade e recursos;
- [x] estratificar casos independentes e dependentes do estado operacional;
- [x] definir tamanho do corpus por viabilidade e custo antes de observar resultados;
- [x] validar geração de identificadores opacos e separação do manifesto em uma prévia inelegível;
- [ ] congelar sementes, repetições, ordem e regra de parada;
- [x] propor teto de duração, custo incremental e capacidade-tempo por decisão;
- [ ] vedar o conjunto de avaliação contra calibração do PDT.

Os operadores candidatos e os controles estão catalogados em
[`tcc-candidate-scenarios.md`](./tcc-candidate-scenarios.md).

**Estado:** existe uma pré-inscrição executável em
[`../experiment/protocol/protocol-v1.json`](../experiment/protocol/protocol-v1.json)
com 18 candidatas propostas, três repetições, seis blocos, regra de agregação,
plano pareado e limites operacionais. O gerador HMAC criou uma prévia pública
com IDs opacos e compromisso do manifesto reservado; operador, parâmetros e
rótulo permanecem fora da árvore versionada. A prévia está marcada como
`confirmatory_eligible: false`. O protocolo permanece em
`pre-registration-candidate` até as políticas, os SLOs, os runtimes imutáveis,
a revisão financeira e a aprovação do pesquisador serem validados; portanto,
nenhum checkbox de congelamento é antecipado por essa prévia.

Os 13 operadores definidos no protocolo agora possuem materialização
determinística e cobertura de todas as combinações de parâmetros. O controle
`INF-REPLICA-01` foi deliberadamente redesenhado como falha óbvia que um
staging competente deve bloquear; `DEP-CURRENCY-01` passou a produzir uma
alteração semântica condicional real. Isso impede contar um no-op ou uma
mutação equivalente como evidência favorável ao PDT. A validação de execução
das imagens materializadas, a publicação imutável dos runtimes e uma execução
cloud do oráculo ainda são pré-requisitos para congelar o protocolo; a
implementação independente do oráculo já está concluída.

Cada candidata será avaliada de forma pareada por staging e PDT. Os dois usam
as mesmas invariantes e SLOs. Primeiro é selada a decisão da CI/CD convencional
com staging; candidatas aprovadas então alcançam o gate PDT, que recebe o
snapshot operacional e pode explorar alternativas contrafactuais. A ordem das
candidatas será randomizada, sem execução simultânea.

A entrada operacional da esteira agora está versionada como dois workflows do
GitHub Actions. O primeiro é disparado automaticamente pelo pull request e não
possui credencial cloud. O segundo é encadeado após sucesso, mas só acessa o GCP
para PR do próprio repositório com candidata opaca, dois rótulos explícitos,
aprovação do ambiente protegido e trava financeira. Ainda falta aplicar essa
configuração no repositório GitHub e validar uma execução cloud de engenharia
por PR. O workflow sem cloud já foi validado no PR #1: seus 22 gates passaram,
a evidência foi publicada e os workflows herdados sem proteção foram
aposentados.

A prontidão para o congelamento agora possui auditoria executável em
`experiment/scripts/audit-protocol-freeze.py`. Ela mantém a coleta bloqueada e
expõe de forma objetiva as pendências de políticas/SLOs, imagens do oráculo,
revisão financeira e aprovação explícita do pesquisador.

O `checkout-pdt-controller` agora existe como aplicação e imagem reproduzível,
gera o plano vinculado aos inputs selados e produz a decisão prescritiva. Um
gerador prepara sua execução como Job isolado, sem token da API e sem rede, no
namespace `pdt-system`. A publicação do digest e a primeira execução do Job
continuam pendentes e não foram antecipadas sem autorização financeira.

O mecanismo de custo por bloco também está preparado, mas não aplicado. Uma
stack Terraform isolada e desligada por padrão cria somente a API do BigQuery e
o dataset protegido `online_boutique_billing`; a consulta versionada limita cada
leitura a 100 MB. A exportação padrão do Cloud Billing continua desabilitada e
depende de autorização explícita, portanto ainda não existe evidência de custo
monetário corrente apta à revisão financeira do protocolo.

**Critério de saída:** protocolo versionado antes da coleta e corpus contendo
controles seguros, mutações funcionais e não funcionais, sem rótulos acessíveis
aos mecanismos.

### Fase 7 — Oráculo, validação e recalibração

Objetivo: obter o ground truth de forma independente e medir a fidelidade do
PDT, não apenas sua decisão.

- [x] implementar a barreira que exige decisões seladas antes de liberar o item privado do oráculo;
- [x] implementar a regra automática de adjudicação por repetição e candidata;
- [x] preparar overlay e quota do namespace `oracle`, sem aplicar no GCP;
- [x] implementar harness funcional independente com doubles e proxies gRPC;
- [x] implementar matriz funcional de 35 casos e nove asserções independentes;
- [x] implementar perfis não funcionais e compositor da observação do oráculo;
- [x] gerar runtime Kubernetes mínimo, privado e vinculado aos artefatos selados;
- [x] implementar o runner do ciclo do oráculo com cleanup obrigatório e trava financeira;
- [ ] validar o runner em execução de engenharia no namespace `oracle`;
- [x] implementar adjudicação independente das candidatas bloqueadas antes de existir artefato implantável;
- [ ] validar essa adjudicação nas candidatas pré-artefato materializadas e seladas;
- [ ] persistir as duas decisões antes de revelar o rótulo em uma execução completa;
- [ ] executar cada candidata em ambiente-oráculo efêmero e sem exposição pública;
- [ ] aplicar matriz de testes mais ampla que a usada pelos mecanismos;
- [ ] combinar manifesto da mutação, asserções e observação de execução;
- [ ] classificar a segurança de `deploy-as-is` e das alternativas permitidas;
- [ ] comparar métricas previstas e observadas no oráculo;
- [ ] calcular erro absoluto e relativo;
- [ ] registrar divergências por serviço e cenário;
- [ ] recalibrar apenas com conjunto de calibração separado;
- [ ] avaliar se a fidelidade melhora ao longo das execuções.

**Critério de saída:** evidência quantitativa da relação entre fidelidade da
previsão e qualidade da decisão.

**Estado:** a suíte funcional, o gerador de carga, o compositor de observação,
o runtime mínimo e o runner Kubernetes único estão implementados e cobertos por
testes locais. O verificador pré-artefato também está implementado e confere
commit, árvore, patch e decisões seladas antes de reproduzir a propriedade
violada sem usar o rótulo pretendido. Uma execução de engenharia validou a
matriz funcional contra o `checkoutservice`, mas não integra a análise
principal. Ainda faltam validar os dois caminhos com candidatas materializadas,
validar todas as imagens e realizar a execução cega posterior às decisões
seladas.

### Fase 8 — Análise final

- [x] implementar analisador confirmatório fail-closed no nível da candidata;
- [ ] construir matriz de confusão para aprovar e bloquear;
- [ ] calcular taxa de aprovação insegura;
- [ ] calcular sensibilidade e especificidade;
- [ ] calcular acurácia balanceada;
- [ ] calcular regressões evitadas;
- [ ] calcular bloqueios desnecessários;
- [ ] calcular oportunidades preservadas;
- [ ] calcular qualidade da alternativa selecionada;
- [ ] calcular cobertura contrafactual;
- [ ] calcular tempo até a decisão;
- [ ] calcular erro de previsão;
- [ ] registrar grau de autonomia;
- [ ] comparar custo computacional de staging e PDT;
- [ ] analisar pares discordantes no nível da candidata;
- [ ] calcular intervalos de confiança no nível da candidata;
- [ ] documentar ameaças à validade.

**Critério de saída:** resultados suficientes para responder à questão de
pesquisa e sustentar ou rejeitar as hipóteses.

**Estado:** o analisador reproduzível está implementado e protegido por hash no
protocolo. Ele calcula intervalos binomiais exatos, diferença pareada de risco,
teste exato de McNemar, matrizes de confusão, utilidade incremental, qualidade
prescritiva e resumos contínuos. O modo normal falha enquanto o protocolo não
estiver congelado; o modo de autoteste produz saída explicitamente inelegível.
Os valores experimentais e sua interpretação continuam pendentes da coleta
confirmatória e do oráculo.

## Métricas e fórmulas a registrar

| Métrica | Definição operacional |
| --- | --- |
| Aprovação insegura | candidata prejudicial aprovada / candidatas prejudiciais |
| Sensibilidade | candidatas prejudiciais bloqueadas / candidatas prejudiciais |
| Especificidade | candidatas seguras aprovadas / candidatas seguras |
| Acurácia balanceada | (sensibilidade + especificidade) / 2 |
| Escape convencional | candidata prejudicial aprovada por CI/CD e staging |
| Detecção incremental do PDT | escape convencional bloqueado ou reconfigurado com segurança pelo PDT |
| Bloqueio incremental do PDT | candidata segura aprovada pelo controle e bloqueada pelo PDT |
| Regressões evitadas | bloqueios em candidatas que causariam regressão |
| Bloqueios desnecessários | bloqueios em candidatas operacionalmente seguras |
| Oportunidades preservadas | aprovações de candidatas seguras |
| Erro de previsão | diferença entre métrica prevista e observada |
| Cobertura contrafactual | alternativas avaliadas por decisão |
| Tempo até decisão | instante da decisão − instante do snapshot |
| Grau de autonomia | etapas automáticas / etapas totais do ciclo |

Para métricas contínuas, devem ser registradas média, mediana, dispersão e
intervalo de confiança quando o número de repetições permitir.

## Controles metodológicos

- [ ] usar as mesmas candidatas na esteira convencional e na esteira acrescida do PDT;
- [ ] congelar protocolo, corpus, sementes e regra de parada antes da coleta;
- [x] usar sementes ou perfis de carga reproduzíveis nos pilotos;
- [x] separar aquecimento e medição;
- [ ] randomizar a ordem das candidatas;
- [x] registrar versão de imagens, manifests e ferramentas;
- [ ] evitar execução simultânea que cause interferência não controlada;
- [x] manter staging sem acesso ao snapshot operacional;
- [ ] fornecer as mesmas invariantes e SLOs aos dois mecanismos;
- [ ] ocultar rótulo e operador de mutação durante as decisões;
- [ ] incluir controles seguros para medir falsos positivos;
- [ ] impedir que dados da validação vazem para a previsão avaliada;
- [ ] executar número equivalente de repetições;
- [ ] tratar candidata, e não repetição, como unidade estatística;
- [ ] documentar falhas, exclusões e dados ausentes.

## Controles financeiros e operacionais

- [x] orçamento bruto acumulado de R$1.751,10;
- [x] alertas de 25% a 100%;
- [x] quotas por namespace;
- [x] somente um Load Balancer permitido;
- [x] staging e PDT sem exposição pública;
- [x] preparar stack isolada e consulta limitada para exportação de faturamento;
- [ ] criar o dataset e habilitar o Standard usage cost export após autorização;
- [ ] exportar e conferir custo diariamente durante execuções;
- [x] definir rotina de desligamento ao final de cada janela;
- [x] remover workloads ociosos;
- [ ] excluir o cluster ao concluir a coleta;
- [ ] verificar faturamento final após o atraso de contabilização.

O orçamento do Google Cloud gera alertas, mas não constitui um limite rígido de
gastos. As quotas, a execução sequencial dos ambientes e a destruição dos
recursos são as contenções efetivas.

## Definição de experimento completo

O experimento estará completo quando:

1. uma esteira convencional completa, incluindo staging, estiver implementada;
2. o protocolo e o corpus tiverem sido congelados antes da coleta principal;
3. houver controles seguros e falhas funcionais e não funcionais;
4. a condição de tratamento preservar todos os gates do controle e acrescentar o PDT;
5. o PDT usar estado observado e comparar alternativas;
6. a decisão convencional for selada antes da decisão PDT;
7. o oráculo independente classificar candidatas e ações;
8. escapes convencionais e detecções incrementais forem calculados;
9. previsões e resultados observados forem comparados;
10. as métricas pareadas forem calculadas no nível da candidata;
11. fidelidade, custo, viés residual e limitações forem documentados;
12. o processo puder ser reproduzido a partir do repositório;
13. os recursos cloud forem removidos e o custo final conferido.
