# Roadmap e estado do experimento PDT

> **Documento vivo:** acompanhamento da implementação do experimento definido em
> [`tcc-experiment-plan.md`](./tcc-experiment-plan.md).
>
> **Última verificação:** 24 de setembro de 2026.

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
- [x] Namespaces cloud `operational`, `staging`, `pdt`, `pdt-system`, `oracle` e `observability`.
- [x] Namespace isolado `oracle` aplicado, sem LoadBalancer e com quota própria.
- [x] Quotas de CPU, memória, pods e Load Balancers por namespace.
- [x] Orçamento de custo bruto de R$1.751,10.
- [x] Margem de R$10 preservada sobre R$1.761,10 de crédito informado.
- [x] Período do orçamento alinhado à expiração dos créditos em 19/12/2026.
- [x] Alertas financeiros em 25%, 50%, 75%, 90%, 95% e 100%.
- [x] Orçamento operacional adicional de R$200, com alertas em R$50, R$100, R$150, R$180 e R$200.
- [x] Identidade federada GitHub/GCP sem chave e com privilégio mínimo.
- [x] Ambiente GitHub `tcc-experiment`, secrets, trava financeira e rótulos configurados sem disparar execução cloud.
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
Um auditor fail-closed recalculou as amostras, os agregados e a completude dos
artefatos; seu relatório vincula as evidências brutas por SHA-256 e foi selado
como input do protocolo.
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
- [x] implementar a agregação candidata-nível de três repetições do staging;
- [ ] executar a mesma candidata opaca nos gates locais e no staging;
- [x] implementar a orquestração sequencial das três repetições de staging e PDT;
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
convencional selada. Naquele piloto ainda não existia o novo probe de serviços
reais. Para concluir a fase faltam comprovar esse probe no cluster, congelar a
política, usar candidatas opacas e executar a orquestração confirmatória. Os
dados atuais continuam classificados apenas como piloto de engenharia em
[`../experiment/evidence/staging/README.md`](../experiment/evidence/staging/README.md);
esses dados não integrarão a comparação principal.

O contrato de integração real já está implementado e ligado ao `PASS/FAIL` do
staging: um pedido válido deve concluir e esvaziar o carrinho, enquanto um
pagamento expirado deve falhar e preservar o item. Ele usa as instâncias reais
de `cartservice` e `checkoutservice`, que por sua vez exercitam catálogo,
câmbio, entrega e pagamento. O checkbox permanece aberto até uma execução
cloud autorizada comprovar esses casos contra uma candidata implantada.

A decisão convencional confirmatória também deixou de depender de uma única
janela: `aggregate-conventional-repetitions.py` exige o plano das três
repetições predeclaradas, o mesmo artefato imutável e a mesma definição de
candidata, e aplica a regra majoritária 2/3. Uma repetição só pode faltar quando
um ledger pré-rótulo comprova que a tentativa original e a única substituta
falharam por infraestrutura; duas repetições seguras ainda são necessárias para
aprovar. CI local continua executada uma vez por candidata por ser
determinística. O agregador está testado e selado como input do protocolo, mas
ainda não foi conectado ao workflow: isso só ocorrerá junto da agregação
simétrica do PDT, para evitar executar condições com números de repetições
diferentes.

O orquestrador confirmatório também está implementado localmente. Ele executa a
CI determinística uma vez, tenta cada repetição de staging no máximo duas vezes,
sela a decisão convencional agregada e somente então inicia as repetições PDT
com os mesmos artefatos. Cada tentativa termina em cleanup verificado. Uma
falha de infraestrutura persistente gera ledger antes do rótulo; se ela ocorrer
depois do controle já selado e impedir uma comparação pareada, a candidata é
excluída em vez de alterar retrospectivamente a decisão do controle. O caminho
permanece sem evidência cloud até uma execução explicitamente autorizada.

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
- [x] implementar a agregação candidata-nível das repetições PDT;
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

O contrato de fidelidade pós-decisão também está implementado localmente. Para
cada alternativa e repetição, ele exige identidade e hashes selados, compara a
previsão do PDT com o perfil basal observado pelo oráculo e registra erro
assinado, absoluto e relativo, sem usar o rótulo pretendido. O checkbox de
fidelidade permanece aberto até existirem observações cloud válidas.

O agregador candidata-nível do PDT aplica a mesma maioria 2/3 do controle para
cada alternativa. `deploy-as-is` só é aprovado com dois votos seguros; caso
contrário, uma alternativa reconfigurada precisa alcançar a mesma maioria e é
selecionada por menor custo e depois menor mediana de p95. A confiança agregada
é o mínimo observado e a ação fica ligada ao snapshot da última repetição
válida. O mesmo ledger pré-rótulo é obrigatório para uma repetição inválida.
Essa lógica está testada e selada, mas ainda aguarda o orquestrador sequencial
antes de qualquer execução confirmatória.

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

O caminho do gate humano real também está implementado no workflow: depois da
decisão pareada, um job sem identidade GCP aguarda o ambiente protegido
`tcc-deployment-approval`, consulta o histórico oficial de aprovações do run e
registra o revisor em um recibo ligado por hash ao gate e à ação. O ambiente foi
criado no GitHub com `omatheu` como revisor obrigatório e somente a branch
`main` permitida, e o workflow já foi incorporado à branch padrão pelo PR #1.
O item permanece aberto até uma nova execução de engenharia comprovar a pausa e
a retomada; a aprovação continua sem autorizar execução cloud ou mutação
operacional.

O job pós-decisão do Oracle também está definido localmente no mesmo workflow,
mas permanece desarmado. Ele só se torna elegível com o label adicional
`tcc-oracle-cloud`, protocolo congelado, revisão financeira e uma confirmação
específica de execução do Oracle. Scripts e protocolo são carregados do
commit-base confiável da `main`; a candidata não recebe os secrets. A evidência
privada é cifrada antes de upload e o cleanup é restrito ao namespace `oracle`.
O RBAC mínimo desse namespace está declarado no Terraform, separado das
permissões gerais de staging/PDT, porém ainda não foi aplicado ao cluster.

Um auditor Oracle somente leitura também está implementado e selado no
protocolo. Ele verifica 22 controles antes de qualquer habilitação: conteúdo do
workflow em `main`, proteção do ambiente, labels/secrets/variáveis, PR
desarmado, identidade e provider OIDC exatos, papéis mínimos, Role/RoleBinding
do namespace, ausência de workloads e congelamento de protocolo, runtimes e
corpus. A leitura real de 26/09/2026 UTC passou em 12/22: os dez bloqueios
restantes correspondem exatamente ao workflow ainda local, configuração
Oracle ainda não instalada, artefatos metodológicos ainda não congelados e
ausência de PR aberto. A auditoria não realizou mutação nem autorizou execução.
A evidência pré-instalação está em
[`../experiment/evidence/oracle/oracle-execution-readiness-preinstall-20260926T163506Z.json`](../experiment/evidence/oracle/oracle-execution-readiness-preinstall-20260926T163506Z.json).

O plano binário do RBAC foi gerado com refresh desligado e validado em 10/10
controles. Ele contém somente a Role e a RoleBinding Oracle como criações, 0
alterações, 0 destruições e nenhum recurso faturável. O relatório sanitizado,
que não autoriza `apply`, está em
[`../experiment/evidence/finance/oracle-rbac-terraform-plan-validation-20260926T163444Z.json`](../experiment/evidence/finance/oracle-rbac-terraform-plan-validation-20260926T163444Z.json).

O runner do oráculo agora também consome esse recibo de forma fail-closed para
candidatas aprovadas pelo controle: recompõe os hashes de candidata, snapshot,
decisão convencional, decisão PDT, gate, ação e histórico bruto do GitHub, e
recusa qualquer divergência antes de chamar `kubectl`. Assim, a confirmação
humana deixou de ser somente evidência produzida e passou a ser uma precondição
executável da validação isolada. A execução real continua pendente.

A barreira que libera o item privado do oráculo aplica a mesma regra antes de
revelar operador e parâmetros. `approve` e `reconfigure` exigem revisão humana
protegida; `block` não inventa uma ação para aprovação, mas exige decisão PDT e
gate bloqueado coerentes. Isso preserva a distinção entre supervisão de uma
ação prescritiva e a coleta posterior de ground truth.

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
aprovação do ambiente protegido e trava financeira. A identidade federada, o
ambiente protegido, os secrets, a variável financeira inicialmente `false`, os
rótulos e a proteção de `main` já foram aplicados. Nenhum rótulo foi anexado ao
PR #1. Os dois workflows foram incorporados à branch padrão pelo merge desse
PR. O workflow sem cloud foi validado nele: seus 22 gates passaram, a evidência
foi publicada e os workflows herdados sem proteção foram aposentados. Resta
validar uma execução cloud de engenharia por um novo PR explicitamente
autorizado.

A prontidão para o congelamento agora possui auditoria executável em
`experiment/scripts/audit-protocol-freeze.py`. Ela mantém a coleta bloqueada e
expõe de forma objetiva as pendências de políticas/SLOs, imagens do oráculo,
revisão financeira e aprovação explícita do pesquisador.

O caminho de publicação até os manifests também está fechado localmente:
`bind-runtime-publication.py` valida a evidência das três imagens contra o
commit, a árvore, o registry aprovado, SBOM/scan e as travas do ambiente
protegido, e produz propostas PDT/oráculo com uma única proveniência. O binder
está integrado ao workflow, mas não foi executado porque nenhuma publicação
cloud nova foi autorizada. Ele não congela o protocolo nem altera o GCP.

O preflight local das três imagens foi repetido em 22/09/2026 para o commit
`6ecffab7`: os três builds, SBOMs e scans HIGH/CRITICAL passaram, sem push ou
acesso ao GCP, e a projeção conservadora de armazenamento permaneceu abaixo da
franquia considerada. A comparação com o artefato anterior mostrou que os
rebuilds não são bit-a-bit idênticos apesar de os inputs materiais serem os
mesmos. O caminho de publicação foi então endurecido: o resumo protegido passa
a vincular os SHA-256 dos relatórios brutos, e o binder revalida conteúdo, tag,
image ID e ausência de achados antes de aceitar os digests remotos. O registro
local é inelegível para publicação ou coleta confirmatória.

O contrato publisher → binder também foi exercitado ponta a ponta sem cloud:
os scripts reais produziram e consumiram o mesmo pacote com Docker e `gcloud`
simulados, e cada trava de autorização foi desligada isoladamente para provar
falha anterior à criação de qualquer artefato. Isso valida o encaixe do caminho
de publicação sem converter a simulação em evidência de publicação.

Para não pagar uma execução completa apenas para obter os digests exigidos
pelo congelamento, o workflow protegido agora separa `runtime-publication` do
job pareado. O novo caminho exige rótulo próprio, rótulo financeiro, variável
financeira e aprovação do ambiente; os rótulos de publicação e experimento são
mutuamente exclusivos. Sua identidade proposta possui somente
`roles/artifactregistry.writer` no repositório e nenhum IAM/RBAC de GKE. O plano
Terraform validado continha 3 adições IAM, 0 alterações e 0 destruições. Ele foi
aplicado após autorização: a Service Account sem chave, o vínculo OIDC e o
Writer restrito ao repositório agora existem. O secret, a variável financeira
exclusiva em `false` e o rótulo passivo também foram cadastrados no GitHub; o
PR #1 continua sem rótulos de autorização.
As janelas também usam variáveis financeiras distintas: habilitar uma
publicação não habilita a execução pareada.
Um auditor somente leitura e fail-closed verificou o estado remoto em
22/09/2026 UTC: 5/13 controles estão prontos e oito permanecem bloqueados. Ele
confere o conteúdo exato do workflow em `main`, o revisor e a branch do ambiente,
o PR desarmado, secrets, variáveis financeiras, ausência de chaves persistentes
e o privilégio mínimo da identidade publisher. A evidência está em
[`../experiment/evidence/finance/runtime-publication-readiness-20260922T031427Z.json`](../experiment/evidence/finance/runtime-publication-readiness-20260922T031427Z.json).
Essa leitura não modificou GitHub ou GCP e não autorizou publicação.
O plano Terraform binário correspondente também foi regenerado e passou em
9/9 controles de escopo: exatamente três criações IAM, referências vinculadas
à identidade publisher, nenhuma chave, papel de projeto, alteração, destruição
ou recurso de compute/storage/rede. O relatório vinculado ao SHA-256 do plano
está em
[`../experiment/evidence/finance/runtime-publication-terraform-plan-validation-20260922T033401Z.json`](../experiment/evidence/finance/runtime-publication-terraform-plan-validation-20260922T033401Z.json).
O relatório de 9/9 preserva a validação pré-apply e não constitui autorização
por si só. O apply posterior criou exatamente os três recursos, e um novo plano
confirmou zero drift. O recibo está em
[`../experiment/evidence/finance/runtime-publication-controls-installation-20260922T033857Z.json`](../experiment/evidence/finance/runtime-publication-controls-installation-20260922T033857Z.json).
Na auditoria pós-instalação anterior ao merge, 12/13 controles passaram e
restava somente incorporar o workflow revisado à `main`. Nenhuma imagem foi
publicada e as duas travas financeiras permaneceram desligadas.

O PR #1 foi posteriormente mesclado em `main` no commit `895473c0`, depois de
os três checks do head `269c9fbe` passarem. O workflow protegido agora está
instalado, e uma auditoria pós-merge separou as dimensões: 12/12 controles de
infraestrutura prontos e 0/1 controle de candidata, pois o PR já foi encerrado.
Isso não é falha de infraestrutura nem autorização implícita: o próximo 13/13
exige um novo PR candidato aberto e desarmado. Nenhum workflow cloud foi
executado. A evidência está em
[`../experiment/evidence/finance/runtime-publication-readiness-post-merge-20260924T223256Z.json`](../experiment/evidence/finance/runtime-publication-readiness-post-merge-20260924T223256Z.json).

O PR #2 foi mesclado em `main` no commit `182c7dff`, depois de os três checks
do pull request passarem. Ele incorporou a agregação simétrica das três
repetições, o cleanup fail-closed e o orquestrador confirmatório sequencial. O
CI de `main` também passou. O workflow protegido executou apenas a autorização:
publicação, staging/PDT e gate humano foram `skipped`, porque o PR não recebeu
rótulos cloud e as travas financeiras permaneceram desligadas.

O passo seguinte também está automatizado localmente:
`prepare-protocol-freeze-candidate.py` recebe os manifests vinculados e gera um
bundle único com cinco políticas, dois manifests e o protocolo candidato, já
com todos os hashes dependentes recalculados. A ferramenta recusa proveniências
divergentes, mudanças escondidas e hashes atuais inconsistentes; não aplica o
bundle, não habilita a coleta e não autoriza cloud. Assim, o futuro
pré-congelamento pode ser revisado e aplicado sem edições manuais parciais.

A transição seguinte também está implementada de forma fail-closed:
`finalize-protocol-freeze.py` só gera uma proposta de protocolo `frozen` quando
o auditor selado comprova 17/17 checks, as aprovações financeira e do
pesquisador vinculam o mesmo candidato e todos os timestamps são coerentes. A
saída inclui a auditoria e um recibo com os hashes do candidato, do protocolo
final e das aprovações. O finalizador não aplica a proposta, não modifica o GCP
e preserva `cloud_execution_authorized: false`; congelar o desenho continua
separado de autorizar uma execução paga.

O `checkout-pdt-controller` agora existe como aplicação e imagem reproduzível,
gera o plano vinculado aos inputs selados e produz a decisão prescritiva. Um
gerador prepara sua execução como Job isolado, sem token da API e sem rede, no
namespace `pdt-system`. A publicação do digest e a primeira execução do Job
continuam pendentes e não foram antecipadas sem autorização financeira.

O mecanismo de custo por bloco está parcialmente aplicado. A API do BigQuery e
o dataset protegido `online_boutique_billing` já existem; a consulta versionada
limita cada leitura a 100 MB. A exportação padrão do Cloud Billing continua
sem produzir dados: a verificação somente leitura de 26/09/2026 UTC encontrou
zero tabelas no dataset e, por isso, não executou query faturável. O cluster continua
`RUNNING`, com 12/12 deployments e pods operacionais disponíveis; staging,
PDT, plano de controle, oráculo e observabilidade permanecem vazios. O registro
está em
[`../experiment/evidence/finance/pre-freeze-readiness-post-pr2-20260926T004340Z.json`](../experiment/evidence/finance/pre-freeze-readiness-post-pr2-20260926T004340Z.json).
Essa mesma auditoria registrou 6/17 requisitos do congelamento e 12/12 controles
estruturais da publicação. Não existe PR aberto elegível, os três runtimes
confirmatórios ainda não foram publicados e nenhuma autorização cloud foi
concedida.
Ainda não existe evidência de custo monetário corrente apta à revisão
financeira do protocolo.

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
- [x] implementar a orquestração candidata-nível da matriz de alternativas e repetições;
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
testes locais. Para decisões aprovadas pelo controle, o runner exige uma cadeia
íntegra até a aprovação do ambiente protegido do GitHub antes de acessar o
cluster; o recibo humano não substitui as três travas financeiras/cloud. O
verificador pré-artefato também está implementado e confere
commit, árvore, patch e decisões seladas antes de reproduzir a propriedade
violada sem usar o rótulo pretendido. Uma execução de engenharia validou a
matriz funcional contra o `checkoutservice`, mas não integra a análise
principal. Ainda faltam validar os dois caminhos com candidatas materializadas,
validar todas as imagens e realizar a execução cega posterior às decisões
seladas.

O runner agora permite ao oráculo percorrer todas as alternativas implantáveis
que a definição candidata e a decisão PDT selada têm em comum, mesmo quando o
gate humano aprovou apenas a ação recomendada. Essa ampliação vale somente no
namespace isolado `oracle` e é necessária para adjudicar a melhor ação; não
autoriza mutação operacional. Quando existe previsão PDT para a alternativa, o
runner persiste ainda `pdt-fidelity.json`, vinculado por hash, com erro por
métrica e concordância de classificação. A implementação está coberta
localmente. Um agregador adicional exige a matriz completa de alternativas por
três repetições e produz o resumo candidata-nível previsto no protocolo. O
compositor e o analisador final já exigem e consomem esse agregado sem tratar
repetições técnicas como amostras independentes. Os itens quantitativos
continuam pendentes de execução real.

O orquestrador candidata-nível também está implementado localmente. Ele libera
o item privado somente depois das decisões e, quando aplicável, da aprovação
humana; executa a matriz de forma sequencial; adjudica o ground truth; agrega a
fidelidade apenas sobre repetições PDT válidas; e separa fisicamente evidência
pública de resultados privados. A esteira pareada foi alinhada à regra
pré-registrada de duas repetições válidas: uma repetição PDT que permaneça
inválida após a única substituição não exclui mais automaticamente a candidata
quando ainda existem duas válidas e um ledger pré-rótulo completo. A exclusão
continua obrigatória abaixo desse mínimo. Os runners também persistem um
`oracle-binding-snapshot.json` canônico antes da abertura do rótulo, inclusive
quando o controle bloqueia depois de staging. A integração desse orquestrador
ao workflow protegido e sua execução no cluster continuam pendentes.

O caminho pré-artefato agora também possui preparação reprodutível: patch e
work order privados são reconstruídos apenas do commit, árvore e base selados
pela CI e do manifesto do Oracle. O rótulo pretendido não entra nesses
artefatos. A definição do workflow já encadeia esse caminho e o caminho
Kubernetes, deriva o manifesto com código da base confiável, cifra toda
evidência privada e persiste publicamente somente hashes e recibos sem rótulo.
Ainda faltam cadastrar os dois secrets protegidos, aplicar o RBAC declarativo,
gerar o corpus confirmatório e executar a validação real autorizada.

### Fase 8 — Análise final

- [x] implementar composição do dataset a partir de evidências seladas;
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
- [x] documentar ameaças à validade e regras de tratamento pré-coleta;
- [ ] atualizar ameaças materializadas e risco residual após a coleta.

**Critério de saída:** resultados suficientes para responder à questão de
pesquisa e sustentar ou rejeitar as hipóteses.

**Estado:** o compositor do dataset e o analisador reproduzível estão
implementados e protegidos por hash no protocolo. O compositor confere o
conjunto completo de IDs opacos e os hashes das decisões convencionais, PDT,
gate e oráculo. O analisador calcula intervalos binomiais exatos, diferença
pareada de risco, teste exato de McNemar, matrizes de confusão, utilidade
incremental, qualidade prescritiva, resumos contínuos e fidelidade preditiva no
nível da candidata. O agregado de fidelidade só é aceito com cobertura completa
das alternativas e repetições, identidade e hashes do protocolo, índice sem
duplicatas e travas contra recalibração confirmatória. O modo normal falha
enquanto o protocolo não estiver congelado; o modo de autoteste produz saída
explicitamente inelegível. Os valores experimentais e sua interpretação
continuam pendentes da coleta confirmatória e do oráculo.
O registro pré-coleta de validade está em
[`tcc-validity-threats.md`](./tcc-validity-threats.md) e fixa direção de viés,
mitigação, evidência e regras de exclusão antes dos resultados. A avaliação
residual pós-coleta permanece aberta.

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
- [x] documentar falhas, exclusões e dados ausentes no fluxo completo por candidata, com ledger pré-rótulo e sem imputação.

## Controles financeiros e operacionais

- [x] orçamento bruto acumulado de R$1.751,10;
- [x] alertas de 25% a 100%;
- [x] quotas por namespace;
- [x] somente um Load Balancer permitido;
- [x] staging e PDT sem exposição pública;
- [x] preparar stack isolada e consulta limitada para exportação de faturamento;
- [x] criar o dataset protegido `online_boutique_billing` e habilitar a API do BigQuery;
- [ ] habilitar o Standard usage cost export no Console do Cloud Billing;
- [ ] exportar e conferir custo diariamente durante execuções;
- [x] definir rotina de desligamento ao final de cada janela;
- [x] exigir cleanup final fail-closed dos workloads de `staging`, `pdt` e
  `pdt-system` no workflow;
- [x] remover workloads ociosos;
- [ ] excluir o cluster ao concluir a coleta;
- [ ] verificar faturamento final após o atraso de contabilização.

O orçamento do Google Cloud gera alertas, mas não constitui um limite rígido de
gastos. As quotas, a execução sequencial dos ambientes e a destruição dos
recursos são as contenções efetivas.

O workflow protegido agora reserva uma janela própria após a execução pareada
para um cleanup independente dos runners internos. O script valida o contexto
exato do cluster, restringe a mutação aos controladores de `staging`, `pdt` e
`pdt-system`, não remove volumes e falha se qualquer pod ativo permanecer. Essa
proteção foi implementada e testada localmente, mas ainda não foi exercitada no
cluster porque nenhuma nova execução cloud foi autorizada.

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
