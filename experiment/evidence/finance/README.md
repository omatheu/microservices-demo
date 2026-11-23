# Evidências financeiras do experimento

Este diretório registra somente observações necessárias à governança do
protocolo. Um orçamento do Cloud Billing é um alerta, não um limite rígido, e
não substitui a revisão do custo incremental entre blocos.

Após a tentativa incompleta v1.9 `45101639286`, a emenda v1.10 aplicou
localmente o bundle de componentes em `2026-11-23T03:23:36Z`. O Billing final
passou a cobrir a exclusão do cluster: R$1.841,771556 brutos e envelope máximo
de R$156,496903 até o teto absoluto de R$1.998,268459. A consulta foi limitada
a 100 MB e a elegibilidade financeira passou sem gerar aprovação. O protocolo
permanece `pre-registration-candidate`, a coleta está desabilitada e os 52
inputs vinculados foram validados. A auditoria passa 15/17; faltam a aprovação
financeira humana e a aprovação do pesquisador. Nenhum recurso cloud foi
criado ou alterado. A observação e a elegibilidade estão em
[`cost-window-20260919-20261123-v1.9-run45101639286-postdelete-final.json`](./cost-window-20260919-20261123-v1.9-run45101639286-postdelete-final.json)
e
[`pre-freeze-financial-review-eligibility-v1.10-20261123T104516Z.json`](./pre-freeze-financial-review-eligibility-v1.10-20261123T104516Z.json).
O bundle e a auditoria regenerados sobre a evidência final estão em
[`protocol-freeze-candidate-v1.10-finalbilling-20261123T104516Z.json`](./protocol-freeze-candidate-v1.10-finalbilling-20261123T104516Z.json)
e
[`pre-freeze-audit-v1.10-finalbilling-20261123T104516Z.json`](./pre-freeze-audit-v1.10-finalbilling-20261123T104516Z.json).
Os recibos iniciais, anteriores à completude do Billing, permanecem em
[`protocol-freeze-candidate-v1.10-20261123T032336Z.json`](./protocol-freeze-candidate-v1.10-20261123T032336Z.json)
e
[`pre-freeze-audit-v1.10-components-20261123T032336Z.json`](./pre-freeze-audit-v1.10-components-20261123T032336Z.json).

Antes do bloco 1 da coleta v1.9, a candidata opaca
`cand-iyzzv33o2ar3bjbq` foi publicada no PR #30 sem labels de execução. Os
cinco checks públicos passaram. O preflight convencional de engenharia selou
decisão `block` no gate `kubernetes-policy`; confirmatório, staging, PDT e
Oracle não executaram. Uma consulta Billing real limitada a 100 MB observou
R$1.841,690664 brutos, R$0,476482 acima da baseline pós-exclusão. A margem até
o teto absoluto caiu de R$157,054277 para R$156,577795. A revisão permite
solicitar uma autorização confirmatória separada somente com esse envelope
reduzido e uma atualização Billing imediatamente antes de qualquer recriação
do cluster. Ela não autoriza merge da candidata, GKE, staging, PDT ou Oracle.
A observação e a revisão estão em
[`cost-window-20260919-20261123-v1.9-preblock1.json`](./cost-window-20260919-20261123-v1.9-preblock1.json)
e
[`pre-block-1-financial-review-v1.9-20261123.json`](./pre-block-1-financial-review-v1.9-20261123.json).

Em `2026-11-23T01:06:47Z`, o guard incremental foi realinhado para a baseline
final de R$1.841,214182 e o envelope de R$157,054277. O plano aplicado alterou
somente um budget existente, sem criar ou destruir recursos; o plano posterior
ficou sem diferenças e o inventário confirmou zero clusters. O recibo está em
[`budget-guard-v1.9-final-realignment-20261123.json`](./budget-guard-v1.9-final-realignment-20261123.json).
Em seguida, o bundle de componentes v1.9 congelou cinco políticas e dois
manifests, manteve o protocolo e a coleta bloqueados e elevou a auditoria para
15/17. A candidata exata e a auditoria estão em
[`protocol-freeze-candidate-v1.9-20261123T010718Z.json`](./protocol-freeze-candidate-v1.9-20261123T010718Z.json)
e
[`pre-freeze-audit-v1.9-components-20261123T010718Z.json`](./pre-freeze-audit-v1.9-components-20261123T010718Z.json).
A aprovação financeira humana canônica foi vinculada à candidata exata sem
autorizar cloud. A auditoria passou a 16/17 e a elegibilidade da aprovação
final do pesquisador está registrada em
[`researcher-approval-eligibility-v1.9-20261123T011230Z.json`](./researcher-approval-eligibility-v1.9-20261123T011230Z.json).
Após a confirmação explícita do pesquisador sobre a coleta parcial, a auditoria
passou 17/17 e o finalizador promoveu a v1.9 para `frozen` em
`2026-11-23T01:15:54Z`. O protocolo congelado possui SHA-256
`7bc2c7f10a66152b7d7ec50aafe64cb59ab69ad15a4f8571b4d85485295893ae`.
Os recibos estão em
[`pre-freeze-audit-v1.9-ready-20261123T011554Z.json`](./pre-freeze-audit-v1.9-ready-20261123T011554Z.json)
e
[`protocol-freeze-finalization-v1.9-20261123T011554Z.json`](./protocol-freeze-finalization-v1.9-20261123T011554Z.json).
O congelamento mantém `cloud_execution_authorized=false`; nenhum corpus v1.9
foi gerado nesta etapa.

Após a tentativa inválida `45020108835`, o cluster foi excluído em
`2026-11-22T12:22:08Z`. A consulta final somente leitura, limitada a 100 MB,
agora cobre uso encerrado às `2026-11-22T14:00:00Z`, com
`billing_data_as_of=2026-11-22T17:09:01Z`. O custo bruto observado é
R$1.841,214182 e restam R$157,054277 até o teto absoluto inalterado de
R$1.998,268459. A revisão local confirmou elegibilidade para uma nova
aprovação financeira humana, sem gerar aprovação, autorização cloud ou
mutação em GCP/GitHub. A observação e a elegibilidade estão em
[`cost-window-20260919-20261122-v1.8-run45020108835-postdelete-final.json`](./cost-window-20260919-20261122-v1.8-run45020108835-postdelete-final.json)
e
[`pre-freeze-financial-review-eligibility-v1.9-20261122.json`](./pre-freeze-financial-review-eligibility-v1.9-20261122.json).

Depois do bloco 1 da coleta v1.8, o cluster foi excluído aproximadamente às
`2026-11-20T16:21:00Z`. A consulta Billing limitada a 100 MB passou a cobrir
uso encerrado às `2026-11-20T20:00:00Z`, com
`billing_data_as_of=2026-11-20T23:44:58Z`. O custo bruto observado é
R$1.836,283045, aumento de R$1,312602 sobre a baseline pré-bloco, e restam
R$161,985414 até o teto absoluto de R$1.998,268459. Reutilizar integralmente o
envelope pré-bloco de R$163,298016 projetaria R$1.999,581061 e excederia o teto
em R$1,312602. Por isso, a etapa Oracle permanece inelegível até a adoção de um
envelope reduzido de no máximo R$161,985414, a confirmação financeira humana e
uma autorização Oracle separada. Nenhuma aprovação ou autorização cloud foi
gerada. A observação, a elegibilidade fail-closed e a revisão estão em
[`cost-window-20260919-20261121-v1.8-postblock1.json`](./cost-window-20260919-20261121-v1.8-postblock1.json),
[`post-block-1-financial-review-eligibility-v1.8-20261121.json`](./post-block-1-financial-review-eligibility-v1.8-20261121.json)
e
[`post-block-1-financial-review-v1.8-20261121.json`](./post-block-1-financial-review-v1.8-20261121.json).
Em 21/11/2026, o pesquisador aprovou explicitamente o envelope reduzido de
R$161,985414, sem elevar o teto absoluto, e autorizou separadamente a
recriação temporária do cluster e somente a execução Oracle da candidata 1.
Staging e PDT não foram autorizados a repetir. Os registros vinculados estão em
[`post-block-1-financial-approval-v1.8-20261121.json`](./post-block-1-financial-approval-v1.8-20261121.json)
e
[`oracle-block-1-cloud-authorization-v1.8-20261121.json`](./oracle-block-1-cloud-authorization-v1.8-20261121.json).
Uma atualização Billing imediatamente anterior à janela Oracle confirmou o
mesmo custo bruto, sem consumo adicional desde a revisão pós-bloco. A etapa
ficou financeiramente elegível dentro do envelope reduzido, mas continua
bloqueada até a confirmação do ambiente protegido. A evidência e a revisão
estão em
[`cost-window-20260919-20261121-v1.8-preoracle1.json`](./cost-window-20260919-20261121-v1.8-preoracle1.json)
e
[`pre-oracle-1-financial-review-v1.8-20261121.json`](./pre-oracle-1-financial-review-v1.8-20261121.json).
Como o run `44763951607` foi armado sem o rótulo Oracle, ele permanece
preservado como tentativa incompleta sem Oracle. O pesquisador autorizou uma
reexecução controlada de staging e PDT da mesma candidata exclusivamente para
rearmar o gate Oracle no workflow congelado. O teto absoluto e o envelope
restante não mudaram, e a exclusão do cluster continua obrigatória em falha,
pausa ou conclusão. A exceção operacional está vinculada em
[`paired-rerun-cloud-authorization-v1.8-20261121.json`](./paired-rerun-cloud-authorization-v1.8-20261121.json).
O run rearmado `44864048460` concluiu CI e três repetições válidas de staging,
mas falhou antes do PDT porque o baseline `operational` não havia sido aplicado
após a recriação temporária do cluster. A tentativa foi classificada como
`infrastructure-invalid-before-pdt`, não revelou o rótulo Oracle e não integra
o corpus confirmatório. O workflow limpou os workloads, os gates do GitHub
foram desarmados e o cluster foi excluído às
`2026-11-21T09:48:53.293223964Z`, preservando Billing, budgets, Artifact
Registry, IAM e GitHub. A evidência está em
[`paired-rerun-pr25-run44864048460-infrastructure-invalid.json`](../ci-cd/paired-rerun-pr25-run44864048460-infrastructure-invalid.json).
A leitura Billing pós-exclusão ainda cobre uso somente até `05:00Z`, registra
R$1.836,749562 brutos e R$161,518897 de margem observada; portanto, o fechamento
financeiro e qualquer retry permanecem bloqueados até o export cobrir a
exclusão. A observação pendente está em
[`cost-window-20260919-20261121-v1.8-run44864048460-postdelete-pending.json`](./cost-window-20260919-20261121-v1.8-run44864048460-postdelete-pending.json).

Antes do bloco 1 da coleta v1.8, a candidata opaca
`cand-2aeweofqphemins4` foi publicada no PR #25 sem labels de execução. A CI
convencional pré-staging passou, mas staging, PDT e Oracle não executaram. Uma
consulta real limitada a 100 MB confirmou custo bruto de R$1.834,970443,
inalterado em relação à baseline do congelamento, com R$163,298016 de margem
bruta até o teto absoluto. O inventário do GKE confirmou zero clusters. A
revisão torna o bloco 1 apenas elegível para uma autorização cloud posterior e
separada, sujeita a uma atualização Billing imediatamente antes de recriar o
cluster por causa do atraso do export. Ela não autoriza merge da candidata,
recriação do cluster ou execução de staging, PDT ou Oracle. A observação e a
revisão estão em
[`cost-window-20260919-20261120-v1.8-preblock1.json`](./cost-window-20260919-20261120-v1.8-preblock1.json)
e
[`pre-block-1-financial-review-v1.8-20261120.json`](./pre-block-1-financial-review-v1.8-20261120.json).

Na revisão pré-publicação v1.8 de 19/11/2026, a consulta somente leitura
limitada a 100 MB observou R$1.834,970435 brutos, R$-1.834,976634 em créditos e
R$-0,006199 líquidos, com dados exportados até `2026-11-19T22:58:54Z`. O
aumento bruto desde a revisão v1.7 foi R$1,017903. A baseline candidata passou
ao valor observado e o teto incremental foi reduzido para R$163,298024, sem
elevar o orçamento absoluto de R$1.998,268459. A consulta está em
[`cost-window-20260919-20261120-v1.8-prepublication.json`](./cost-window-20260919-20261120-v1.8-prepublication.json).
A elegibilidade foi confirmada sem gerar aprovação em
[`pre-publication-financial-review-eligibility-v1.8-20261120.json`](./pre-publication-financial-review-eligibility-v1.8-20261120.json).
A revisão é somente de elegibilidade: não aprova o congelamento, não publica
runtimes e não autoriza cloud.

A publicação isolada posterior passou na auditoria de prontidão 13/13 e usou a
identidade sem chave que tem Writer somente no repositório Artifact Registry.
O tamanho observado antes era 132,228 MB; o limite superior conservador depois
das três imagens era 367,624 MB, e o tamanho observado após a publicação ficou
em 184,406 MB. O run `44667362567` não obteve credenciais GKE, não recriou
cluster e ignorou staging, PDT e Oracle. A autorização, os controles e o
desarmamento estão em
[`runtime-publication-financial-review-v1.8-20261120.json`](./runtime-publication-financial-review-v1.8-20261120.json),
e a auditoria somente leitura em
[`runtime-publication-readiness-v1.8-20261120.json`](./runtime-publication-readiness-v1.8-20261120.json).

O bundle de componentes v1.8 foi aplicado em `2026-11-20T04:57:03Z`. As cinco
políticas, o runtime PDT e a suíte Oracle foram congelados e a auditoria passou
15/17 controles, deixando somente `financial-review` e
`researcher-approval`. O protocolo candidato resultante tem SHA-256
`a403824878fc40ed94c3c977c062e465f7ac0d10c2eef79ec56376b6170b94d5`.
Os recibos estão em
[`protocol-freeze-candidate-v1.8-20261120T045703Z.json`](./protocol-freeze-candidate-v1.8-20261120T045703Z.json)
e
[`pre-freeze-audit-v1.8-components-20261120T045703Z.json`](./pre-freeze-audit-v1.8-components-20261120T045703Z.json).
Nenhum deles autoriza execução cloud.

A consulta pós-publicação v1.8 limitada a 100 MB passou a cobrir uso encerrado
às `2026-11-20T06:00:00Z`, posterior à publicação das imagens às `03:26:02Z`,
com `billing_data_as_of=2026-11-20T09:55:43Z`. Ela observou
R$1.834,970443 brutos, R$-1.834,976644 em créditos e R$-0,006201 líquidos. O
aumento de R$0,000008 reduziu mecanicamente o teto incremental para
R$163,298016, mantendo o orçamento absoluto de R$1.998,268459 e a regra de
reserva promocional. A observação está em
[`cost-window-20260919-20261120-v1.8-freeze.json`](./cost-window-20260919-20261120-v1.8-freeze.json).
A elegibilidade para aprovação humana, sem gerar aprovação, está em
[`pre-freeze-financial-review-eligibility-v1.8-20261120.json`](./pre-freeze-financial-review-eligibility-v1.8-20261120.json).
A candidata de protocolo vinculável pela futura aprovação financeira tem
SHA-256 `01cdeeb72a301ce599715371e1a4ccecf4fe5f59ab5ddfba19e1ff32b73e4492`.
Após a confirmação literal, a aprovação financeira canônica foi gerada em
[`../../protocol/approvals/cost-review-v1.json`](../../protocol/approvals/cost-review-v1.json),
mantendo `cloud_execution_authorized=false`. A auditoria passou a 16/17; a
elegibilidade da aprovação final do pesquisador está em
[`researcher-approval-eligibility-v1.8-20261120.json`](./researcher-approval-eligibility-v1.8-20261120.json).
Depois da confirmação específica do pesquisador sobre a coleta parcial, a
auditoria passou 17/17 e o finalizador congelou o protocolo v1.8 com SHA-256
`c55d9a8d85c2ed3e0d1709e5bb15244723e8b60d1714e29e7d73c79a7438ab86`.
Os recibos estão em
[`pre-freeze-audit-v1.8-ready-20261120T142507Z.json`](./pre-freeze-audit-v1.8-ready-20261120T142507Z.json)
e
[`protocol-freeze-finalization-v1.8-20261120T142507Z.json`](./protocol-freeze-finalization-v1.8-20261120T142507Z.json).
O corpus foi rotacionado, mas nenhuma execução cloud foi autorizada.

Após a tentativa incompleta v1.6, o cluster foi excluído em 18/11/2026. A
consulta final limitada a 100 MB agora cobre com segurança essa exclusão:
`last_usage_end_time=2026-11-19T00:00:00Z` e
`billing_data_as_of=2026-11-19T03:47:09Z`. Ela observou R$1.833,952532
brutos, R$-1.833,958731 em créditos e R$-0,006199 líquidos. Restam
R$164,315927 até o orçamento absoluto de R$1.998,268459; o teto não foi
aumentado.

A observação está em
[`cost-window-20260919-20261119-v1.7-freeze.json`](./cost-window-20260919-20261119-v1.7-freeze.json)
e sua verificação em
[`pre-freeze-financial-review-eligibility-v1.7-20261119T044808Z.json`](./pre-freeze-financial-review-eligibility-v1.7-20261119T044808Z.json).
A revisão financeira foi aprovada pelo pesquisador em 19/11/2026 e vinculada
ao protocolo v1.7 exato, mantendo `cloud_execution_authorized: false`. A
elegibilidade da aprovação final foi registrada em
[`researcher-approval-eligibility-v1.7-20261119T164932Z.json`](./researcher-approval-eligibility-v1.7-20261119T164932Z.json).
Depois da confirmação humana específica para a coleta parcial, a auditoria
passou 17/17 e o finalizador congelou o protocolo com SHA-256
`9ae5ed8fb37d4421ad5327a47f3b65631b43a577d6c3b42a96fb031e620c77c4`.
Os recibos estão em
[`pre-freeze-audit-v1.7-ready-20261119T171802Z.json`](./pre-freeze-audit-v1.7-ready-20261119T171802Z.json)
e
[`protocol-freeze-finalization-v1.7-20261119T171802Z.json`](./protocol-freeze-finalization-v1.7-20261119T171802Z.json).
Nenhuma execução cloud foi autorizada.

Antes de qualquer execução v1.7, o gate de segurança do PR #24 encontrou
`CVE-2026-97054` e a emenda pré-execução v1.8 invalidou o congelamento, as
aprovações e o corpus v1.7 para uso confirmatório. A observação Billing e seus
recibos permanecem como baseline histórica verificável, mas uma revisão
financeira e uma aprovação do pesquisador renovadas só poderão vincular o
estado v1.8 depois da publicação e do binding dos runtimes corrigidos. A
remediação local não tocou GCP nem autorizou execução cloud.

O bundle de componentes v1.7 foi preparado e aplicado localmente em
`2026-11-18T23:09:29Z`. A auditoria resultante passou 15/17 controles e mantém
como bloqueios apenas `financial-review` e `researcher-approval`. Os recibos
estão em
[`protocol-freeze-candidate-v1.7-20261118T230929Z.json`](./protocol-freeze-candidate-v1.7-20261118T230929Z.json)
e
[`pre-freeze-audit-v1.7-components-20261118T230929Z.json`](./pre-freeze-audit-v1.7-components-20261118T230929Z.json).
Nenhum dos dois autoriza execução cloud.

Para o congelamento v1.6, a consulta real limitada a 100 MB observou custo
bruto de R$1.798,268472, créditos de R$-1.798,274571 e custo líquido de
R$-0,006099, com dados exportados até `2026-11-17T18:08:10Z`. A diferença de
R$0,000013 em relação à baseline v1.5 não foi arredondada: a baseline foi
movida para o valor observado e o teto incremental caiu para R$199,999987,
mantendo o orçamento absoluto de R$1.998,268459. As aprovações levaram a
auditoria a 17/17 e o protocolo foi congelado com SHA-256
`b407d318c6ff793a0c41f01035022af4f749ecdf189862b7ebd8aea7fc509e1d`.
A observação e os recibos estão em
[`cost-window-20260919-20261117-v1.6-freeze.json`](./cost-window-20260919-20261117-v1.6-freeze.json),
[`pre-freeze-audit-v1.6-ready-20261117T225254Z.json`](./pre-freeze-audit-v1.6-ready-20261117T225254Z.json)
e
[`protocol-freeze-finalization-v1.6-20261117T225254Z.json`](./protocol-freeze-finalization-v1.6-20261117T225254Z.json).
Esses atos não autorizam execução cloud.

Antes do bloco 1 da coleta v1.5, a candidata opaca
`cand-ipshd3h2j7ngflva` foi publicada no PR #17 sem labels de execução. Uma
consulta real limitada a 100 MB confirmou custo bruto de R$1.798,268459,
inalterado em relação à baseline financeira, com R$200 de margem bruta até o
orçamento do projeto. O inventário do GKE confirmou zero clusters. A revisão
torna o bloco 1 apenas elegível para uma autorização cloud posterior e
separada: não autoriza recriar o cluster, executar staging/PDT/Oracle nem
incorporar a candidata. A observação e a revisão estão em
[`cost-window-20260919-20261110-v1.5-preblock1.json`](./cost-window-20260919-20261110-v1.5-preblock1.json)
e
[`pre-block-1-financial-review-v1.5-20261111.json`](./pre-block-1-financial-review-v1.5-20261111.json).

Antes da publicação isolada dos runtimes v1.5, a consulta real limitada a
100 MB confirmou em 11/11/2026 UTC que o custo bruto permanece em
R$1.798,268459, sem consumo incremental desde a baseline v1.4. O inventário
local do Artifact Registry soma 147.420.233 bytes. Mesmo adicionando os
227.013.942 bytes descomprimidos das três imagens como limite superior
conservador, a projeção fica em 0,348719 GiB, abaixo da franquia de 0,5 GiB.
O scanner pago do Artifact Registry está desativado; a política de retenção
remove versões antigas e mantém duas por pacote. A observação e a revisão estão
em
[`cost-window-20260919-20261111-v1.5-prepublication.json`](./cost-window-20260919-20261111-v1.5-prepublication.json)
e
[`runtime-publication-financial-review-v1.5-20261111.json`](./runtime-publication-financial-review-v1.5-20261111.json).
Essa autorização cobre somente publicação; não cobre GKE, coleta, congelamento
ou merge.

A publicação protegida terminou em 11/11/2026 UTC no run `42944299918`. O
inventário passou a dez versões e 219.862.888 bytes listados, ainda abaixo da
projeção conservadora e da franquia de 0,5 GiB. A variável exclusiva e os dois
labels temporários foram desarmados imediatamente depois do job.

Para o congelamento v1.5, uma consulta real adicional limitada a 100 MB usou
uma janela encerrada às 23:00 UTC, anterior ao instante de consolidação do
export. O custo bruto permaneceu em R$1.798,268459, os créditos em
R$-1.798,274554 e o líquido em R$-0,006095. A aprovação financeira canônica e
a aprovação do pesquisador levaram a auditoria a 17/17; o protocolo foi
congelado com SHA-256
`331f90ac8b8dde08b96a90e29aaa40f500774f44d3e957b78ba44007cea2fd8a`.
A observação e os recibos estão em
[`cost-window-20260919-20261110-v1.5-freeze.json`](./cost-window-20260919-20261110-v1.5-freeze.json),
[`pre-freeze-audit-v1.5-ready-20261111T022648Z.json`](./pre-freeze-audit-v1.5-ready-20261111T022648Z.json)
e
[`protocol-freeze-finalization-v1.5-20261111T022648Z.json`](./protocol-freeze-finalization-v1.5-20261111T022648Z.json).
Esses atos não autorizam execução cloud.

Em 09/11/2026 UTC, depois da pausa financeira e da exclusão do cluster, uma
consulta nova limitada a 100 MB observou R$1.798,268459 brutos,
R$-1.798,274554 em créditos e R$-0,006095 líquidos. O Console registrava
R$711,37 de crédito promocional remanescente. A emenda v1.4 fixa R$200 como
teto absoluto adicional, R$1.998,268459 como orçamento bruto contábil e R$10
como reserva promocional mínima. A auditoria passou 17/17 e o protocolo foi
congelado em 10/11/2026 UTC com SHA-256
`2e6949ca79db0f3be49ab127256a7bcfa1ff7d94e94ed34f6e00ec55a1ea91ed`.
Os recibos estão em
[`pre-freeze-audit-v1.4-ready-20261110T030338Z.json`](./pre-freeze-audit-v1.4-ready-20261110T030338Z.json)
e
[`protocol-freeze-finalization-v1.4-20261110T030338Z.json`](./protocol-freeze-finalization-v1.4-20261110T030338Z.json).
Nenhum desses atos autoriza execução cloud.

O snapshot anterior, consultado em 24/10/2026 UTC para a emenda v1.3,
confirma que o Standard usage cost export alcançou a janela encerrada às
16:00 UTC do mesmo dia. A consulta versionada e limitada a 100 MB observou
R$1.354,686907 de custo bruto, R$-1.354,691494 em créditos e R$-0,004587 de
custo líquido desde 19/09, com
`billing_data_as_of=2026-10-24T16:11:22Z`. O protocolo usa o custo bruto, e não
o líquido coberto pelos créditos, para decidir se pode prosseguir.

Reservar o teto incremental conservador de R$200 para os seis blocos projeta
R$1.554,686907, abaixo do orçamento de R$1.751,10, com R$196,413093 de margem.
Essa reserva equivale a uma envoltória média de R$33,333333 por bloco, não a
uma previsão de preço por bloco. O custo deve ser consultado depois de cada
bloco, há revisão obrigatória ao atingir R$150 incrementais e a coleta é
interrompida se o Billing ficar indisponível. A observação e sua verificação de
elegibilidade estão em
[`cost-window-20260919-20261024-v1.3-review.json`](./cost-window-20260919-20261024-v1.3-review.json)
e
[`financial-review-eligibility-v1.3-20261024.json`](./financial-review-eligibility-v1.3-20261024.json).
O agregado não isola contabilmente o custo de cada workload.

A confirmação literal do pesquisador financeiro gerou a revisão canônica da
v1.3 vinculada a essa evidência. A decisão aprova somente seu uso no
congelamento do protocolo e mantém `cloud_execution_authorized: false`.

Depois da aprovação do pesquisador específica para a coleta parcial, a
auditoria pré-freeze passou 17/17 e o finalizador promoveu a v1.3 para `frozen`
em 24/10/2026 UTC. O hash final do protocolo é
`3c6612fc93e1ec5e6e4267d533bdfac0d985fe813420351da3b9648c1afb7b32`.
Os recibos estão em
[`pre-freeze-audit-v1.3-ready-20261024T174044Z.json`](./pre-freeze-audit-v1.3-ready-20261024T174044Z.json)
e
[`protocol-freeze-finalization-v1.3-20261024T174044Z.json`](./protocol-freeze-finalization-v1.3-20261024T174044Z.json).
O congelamento e as aprovações mantêm `cloud_execution_authorized: false`.

O snapshot anterior da v1.2 permanece em
[`cost-window-20260919-20261022-v1.2-review.json`](./cost-window-20260919-20261022-v1.2-review.json).

A publicação protegida v1.2 ocorreu no workflow `40108005657`, vinculada ao
commit `6a39f7f77206c229144dd593560536cdad607825`, depois de a CI convencional e
o gate das três imagens passarem. A identidade usada tinha somente escrita no
Artifact Registry; staging, PDT, gate humano e Oracle foram ignorados. A janela
foi desarmada imediatamente após o job. O resumo versionado está em
[`runtime-publication-pr12-20261024T154243Z.json`](../ci-cd/runtime-publication-pr12-20261024T154243Z.json),
e o bundle de congelamento em
[`protocol-freeze-candidate-v1.2-20261024T154436Z.json`](./protocol-freeze-candidate-v1.2-20261024T154436Z.json).
A elegibilidade 16/17, sem gerar aprovação, está em
[`researcher-approval-eligibility-v1.2-20261024T154520Z.json`](./researcher-approval-eligibility-v1.2-20261024T154520Z.json).
Essa autorização não alcança coleta confirmatória nem workloads no cluster.

Depois da aprovação explícita do pesquisador, a auditoria pré-freeze passou
17/17 e o finalizador promoveu a v1.2 para `frozen` em 24/10/2026 UTC. O hash
final do protocolo é
`8a34f553287d688b2cf38dfa2db6b29caa078bd191ce7d04a03fb5e707870c51`.
Os recibos estão em
[`pre-freeze-audit-v1.2-ready-20261024T160124Z.json`](./pre-freeze-audit-v1.2-ready-20261024T160124Z.json)
e
[`protocol-freeze-finalization-v1.2-20261024T160124Z.json`](./protocol-freeze-finalization-v1.2-20261024T160124Z.json).
O congelamento e a aprovação mantêm `cloud_execution_authorized: false`.

A aprovação financeira canônica da v1.1 foi registrada em 12/10/2026 UTC após
confirmação humana literal. Ela vinculou a evidência pelo SHA-256, aprovou
somente o uso da baseline no congelamento e manteve
`cloud_execution_authorized: false`. A emenda de segurança v1.2 invalidou essa
aprovação antes da coleta; o arquivo anterior permanece recuperável no commit
`32da279a`, e a revisão v1.2 agora ocupa o caminho canônico.
O preflight anterior permanece em
[`financial-review-eligibility-v1.1-20261006T234330Z.json`](./financial-review-eligibility-v1.1-20261006T234330Z.json),
e o registro da emenda está em
[`../../protocol/amendments/security-v1.2-precollection.json`](../../protocol/amendments/security-v1.2-precollection.json).

O bundle determinístico da emenda congelou as cinco políticas e os dois
manifests. Depois da revisão financeira e da aprovação do pesquisador, a
auditoria pré-freeze passou 17/17 controles e o finalizador promoveu o protocolo
v1.1 para `frozen` em 12/10/2026 UTC. O hash final é
`38b1270bce29c4aa975f331d7c5b761e2abe89acd2545cdc11030318ceb4dbaf`.
Os recibos finais estão em
[`pre-freeze-audit-v1.1-ready-20261012T212014Z.json`](./pre-freeze-audit-v1.1-ready-20261012T212014Z.json)
e
[`protocol-freeze-finalization-v1.1-20261012T212014Z.json`](./protocol-freeze-finalization-v1.1-20261012T212014Z.json).
Esse congelamento não autorizou execução cloud e agora é histórico. A v1.2
repetiu publicação, revisão financeira, aprovação, congelamento e geração do
corpus sem antecipar a autorização financeira por bloco.

A validação curta do Oracle v1.1 foi consultada novamente após o cleanup. A
exportação ainda informava a mesma posição — R$588,369730 bruto e
R$-0,001987 líquido — com `billing_data_as_of` anterior à execução; portanto,
o valor não pode ser atribuído ao run. A consulta limitada a 100 MB está em
[`cost-window-20260919-20261005-post-oracle-v1.1-engineering-query.json`](./cost-window-20260919-20261005-post-oracle-v1.1-engineering-query.json).

Os recibos históricos de ativação permanecem em
[`billing-export-activation-20260929T052504Z.json`](./billing-export-activation-20260929T052504Z.json)
e
[`billing-export-dataset-readiness-20260929T054404Z.json`](./billing-export-dataset-readiness-20260929T054404Z.json).

O snapshot consolidado anterior, de 27/09/2026 UTC, está em
[`pre-freeze-readiness-post-pr4-20260927T002039Z.json`](./pre-freeze-readiness-post-pr4-20260927T002039Z.json).
Ele registra o protocolo em 6/17 controles, a infraestrutura de
publicação em 12/12, a prontidão estrutural então em 13/21, 12/12
deployments e pods operacionais disponíveis, os cinco namespaces auxiliares
vazios e apenas a imagem de engenharia anterior do `checkoutservice` no
Artifact Registry. O PR #4 foi incorporado sem rótulos de autorização; nenhuma
publicação ou execução cloud foi habilitada. O snapshot anterior permanece em
[`pre-freeze-readiness-post-pr2-20260926T004340Z.json`](./pre-freeze-readiness-post-pr2-20260926T004340Z.json),
e o registro inicial permanece em
[`protocol-freeze-readiness-20260922T013315Z.json`](./protocol-freeze-readiness-20260922T013315Z.json).

## Plano de publicação dos runtimes

O artefato `experiment-runtime-images-*` produzido pela CI registra o commit, a
árvore Git, o pull request, a plataforma, os IDs locais, os tamanhos, o SBOM e o
resultado da análise de vulnerabilidades das três imagens experimentais. Antes
de qualquer publicação, ele pode ser convertido em um plano verificável com:

```bash
python3 experiment/scripts/prepare-runtime-publication-plan.py \
  --summary <artifact>/summary.json \
  --expected-commit <sha-completo-validado> \
  --existing-repository-bytes <bytes-observados-no-registro> \
  --registry-prefix us-central1-docker.pkg.dev/microservices-demo-tcc/online-boutique-experiment
```

O tamanho não comprimido é tratado como limite superior conservador para o
armazenamento adicional. O resultado distingue a capacidade potencial do
repositório da franquia compartilhada na conta de faturamento. Sem o consumo
total da conta e o custo corrente detalhado, ele permanece como
`review-required-no-publication-authorized`: o plano nunca autoriza escrita no
GCP, aprovação financeira ou execução cloud.

Depois de uma publicação explicitamente autorizada, os digests ainda precisam
passar por `bind-runtime-publication.py`. O binder gera propostas de manifests
com a mesma proveniência de commit, árvore, workflow protegido, SBOM e scan;
ele não publica, congela nem autoriza execução.

A identidade de publicação foi desacoplada da identidade que executa workloads.
O plano somente leitura em
[`runtime-publication-identity-plan-20260922T025300Z.json`](./runtime-publication-identity-plan-20260922T025300Z.json)
contém três adições: Service Account sem chave, vínculo OIDC e Writer apenas no
repositório Artifact Registry. Não há IAM de projeto, RBAC Kubernetes, mudança
ou destruição de recurso existente. Esse arquivo preserva o estado anterior ao
apply; a instalação controlada posterior aplicou exatamente as três adições e
continua sem autorizar armazenamento de imagens ou execução de workloads.

O plano binário foi regenerado em 22/09/2026 UTC e conferido diretamente por
[`validate-runtime-publication-terraform-plan.py`](../../scripts/validate-runtime-publication-terraform-plan.py).
Os 9/9 controles passaram: somente as três criações previstas aparecem, todas
são `create`, o principal OIDC é o repositório imutável esperado, o Writer está
limitado ao repositório, o grafo referencia a identidade exclusiva e não existe
chave, compute, storage ou rede nova. O relatório sanitizado, vinculado ao
SHA-256 do plano binário, está em
[`runtime-publication-terraform-plan-validation-20260922T033401Z.json`](./runtime-publication-terraform-plan-validation-20260922T033401Z.json).
O plano binário não é versionado porque contém o estado integral da
infraestrutura. O relatório preserva a validação pré-apply e declara
explicitamente que ele próprio não executou mutação, publicação ou autorização
de custo.

O plano separado do RBAC Oracle foi gerado em 26/09/2026 UTC com refresh
desligado e sem `apply`. O validador selado passou em 10/10 controles: somente
`kubernetes_role_v1.github_experiment_oracle_runner[0]` e sua RoleBinding seriam
criadas; há 0 alterações, 0 destruições e nenhum recurso de compute, storage,
rede ou faturamento contínuo. A evidência sanitizada está em
[`oracle-rbac-terraform-plan-validation-20260926T163444Z.json`](./oracle-rbac-terraform-plan-validation-20260926T163444Z.json).
O plano binário contém estado e não é versionado; o relatório vincula seu
SHA-256 e não autoriza `apply`, custo ou execução Oracle.

Depois do merge do PR #4, o plano foi regenerado com refresh real do estado
remoto. O resultado continuou limitado às mesmas duas criações, com 0
alterações, 0 destruições e 10/10 controles aprovados. A evidência atualizada
está em
[`oracle-rbac-terraform-plan-validation-post-pr4-20260927T002511Z.json`](./oracle-rbac-terraform-plan-validation-post-pr4-20260927T002511Z.json).
Esse plano histórico permaneceu fora do Git e não foi aplicado naquele
momento. Em 29/09/2026 UTC, um plano fresco passou novamente em 10/10 e o mesmo
binário foi aplicado: duas adições, zero alterações e zero destruições. A
auditoria Oracle confirmou Role e RoleBinding exatas, o namespace vazio e
18/21 controles estruturais. O recibo de aplicação está em
[`oracle-rbac-terraform-application-20260929T055307Z.json`](./oracle-rbac-terraform-application-20260929T055307Z.json),
vinculado à validação pré-apply
[`oracle-rbac-terraform-plan-validation-preapply-20260929T0550Z.json`](./oracle-rbac-terraform-plan-validation-preapply-20260929T0550Z.json).

O lote mínimo seguinte foi separado em uma solicitação de mudança auditável:
as duas criações RBAC, o rótulo passivo, os dois secrets protegidos e a variável
Oracle mantida em `false`. O documento exclui publicação, labels em PR,
workloads e execução cloud, e prevê que o auditor avance para 18/21 controles
estruturais sem tornar uma candidata elegível. A proposta está em
[`oracle-passive-controls-change-request-20260927T002627Z.json`](./oracle-passive-controls-change-request-20260927T002627Z.json)
e continua com `apply_authorized: false` até autorização explícita.

O instalador
[`install-oracle-passive-github-controls.py`](../../scripts/install-oracle-passive-github-controls.py)
materializa somente a parte GitHub dessa proposta. Seu modo padrão é uma
auditoria somente leitura; o modo de aplicação exige confirmação literal e
recibo novo, força a variável para `false` antes dos secrets, recusa PR armado,
preserva secrets existentes e não expõe os valores gerados. O dry-run real
pós-PR #4 confirmou exatamente quatro ações pendentes e nenhum PR aberto com
label de autorização. Nenhuma mutação foi executada. O resultado está em
[`../oracle/oracle-passive-github-controls-readiness-20260927T003254Z.json`](../oracle/oracle-passive-github-controls-readiness-20260927T003254Z.json).

Depois do merge do PR #5, as quatro ações foram aplicadas. O recibo sanitizado
confirma a variável Oracle em `false`, o label passivo sem vínculo a PR, os dois
nomes de secrets presentes e nenhum valor divulgado. A auditoria posterior
retornou zero ações restantes. Os registros estão em
[`../oracle/oracle-passive-github-controls-installation-20260929T054946Z.json`](../oracle/oracle-passive-github-controls-installation-20260929T054946Z.json)
e
[`../oracle/oracle-passive-github-controls-post-install-readiness-20260929T055153Z.json`](../oracle/oracle-passive-github-controls-post-install-readiness-20260929T055153Z.json).

O auditor somente leitura
[`audit-runtime-publication-readiness.py`](../../scripts/audit-runtime-publication-readiness.py)
transforma essas pendências em 13 controles verificáveis. A leitura de
22/09/2026 UTC aprovou 5/13: `main`, revisor obrigatório `omatheu`, política de
branch restrita a `main`, PR #1 aberto e desarmado e ausência de papel de projeto
na identidade proposta. Os oito bloqueios restantes são o workflow ainda fora
de `main`, o rótulo, o secret, a variável financeira exclusiva e a identidade
publisher com seus vínculos mínimos. O relatório está em
[`runtime-publication-readiness-20260922T031427Z.json`](./runtime-publication-readiness-20260922T031427Z.json).
Ele registra `read_only: true`, nenhuma mutação GitHub/GCP pelo auditor e nenhuma
autorização de publicação. Uma nova conferência fail-closed pode ser executada
com:

```bash
python3 experiment/scripts/audit-runtime-publication-readiness.py \
  --pull-request 1 \
  --require-ready
```

Após autorização, o plano binário vinculado foi aplicado com **3 adições, 0
alterações e 0 destruições**. Em seguida foram cadastrados o secret da identidade
publisher, a variável exclusiva com valor `false` e o rótulo passivo, sem
anexá-lo ao PR #1. O plano Terraform pós-apply retornou `No changes`. O recibo
está em
[`runtime-publication-controls-installation-20260922T033857Z.json`](./runtime-publication-controls-installation-20260922T033857Z.json).

A auditoria somente leitura pós-instalação passou em 12/13 controles. Ela
confirmou zero chaves, Writer somente no repositório, nenhum papel de projeto,
principal OIDC exato, variáveis financeiras desligadas e PR desarmado. O único
bloqueio restante é o workflow revisado ainda não existir na `main`. A evidência
está em
[`runtime-publication-readiness-20260922T033857Z.json`](./runtime-publication-readiness-20260922T033857Z.json).
O campo `cloud_mutation_performed: false` desse arquivo descreve o auditor
somente leitura; o recibo separado registra as mutações de instalação que o
precederam.

Depois do merge do PR #1, o workflow revisado passou a existir em `main` e o
auditor foi refinado para separar prontidão estrutural de prontidão da
candidata. A leitura de 24/09/2026 UTC comprova **12/12 controles de
infraestrutura prontos** e **0/1 controle de candidata**, porque o PR #1 está
corretamente fechado após o merge. O resultado geral permanece 12/13 e não
autoriza publicação. A evidência está em
[`runtime-publication-readiness-post-merge-20260924T223256Z.json`](./runtime-publication-readiness-post-merge-20260924T223256Z.json).
O próximo 13/13 depende de um novo PR candidato aberto, do próprio repositório,
não draft e inicialmente sem qualquer rótulo de autorização.

Uma leitura posterior da conta de faturamento retornou somente o projeto
`microservices-demo-tcc` e somente o repositório Docker do experimento, com
7.843.495 bytes. A projeção conservadora após as três imagens é 236.019.643
bytes, abaixo dos 500.000.000 bytes considerados para a franquia. A evidência
está em
[`artifact-registry-storage-readiness-20260920T222357Z.json`](./artifact-registry-storage-readiness-20260920T222357Z.json).
Isso resolve a incerteza de armazenamento visível na conta, mas não substitui a
exportação do custo corrente: publicação e execução continuam bloqueadas.

Após a criação e ativação explicitamente autorizadas do Standard usage cost
export, uma janela pode ser conferida com:

```bash
START_TIME=2026-09-19T00:00:00Z \
END_TIME=<fim-exclusivo-em-UTC> \
OUTPUT_FILE=experiment/evidence/finance/cost-window.json \
./experiment/scripts/query-billing-cost-window.sh
```

A consulta é limitada a 100 MB, usa cache, exige exatamente uma tabela padrão,
filtra `microservices-demo-tcc` e falha se não houver uma observação completa em
BRL. O valor é uma estimativa exportada, não uma fatura finalizada. O arquivo de
revisão financeira deve referenciar essa saída por caminho relativo e SHA-256;
o auditor vincula o custo bruto observado como baseline do projeto e comprova
que essa baseline somada ao teto incremental futuro de R$200 permanece abaixo
do orçamento bruto de R$1.751,10. Uma nova revisão é obrigatória ao atingir
R$150 de gasto incremental após a baseline. O snapshot de prontidão, que não
contém custo corrente, é deliberadamente inelegível como substituto.

O Standard usage cost export foi ativado em 29/09/2026 UTC para o dataset
protegido `microservices-demo-tcc.online_boutique_billing`. A verificação
imediata foi somente leitura e encontrou zero tabelas; nenhuma query foi
executada e a revisão financeira permanece bloqueada até a primeira entrega
diária. O recibo está em
[`billing-export-activation-20260929T052504Z.json`](./billing-export-activation-20260929T052504Z.json).

Uma segunda verificação somente leitura confirmou que o dataset está em `US`
e que a identidade oficial
`billing-export-bigquery@system.gserviceaccount.com` possui acesso de escrita.
Assim, a ausência inicial da tabela é estado de entrega pendente, não uma
falha conhecida de localização ou permissão. A evidência está em
[`billing-export-dataset-readiness-20260929T054404Z.json`](./billing-export-dataset-readiness-20260929T054404Z.json).

O elo entre a observação e a revisão canônica agora é automatizado por
[`prepare-financial-review.py`](../../scripts/prepare-financial-review.py). O
modo padrão apenas mede elegibilidade; o modo de aprovação exige confirmação
literal, recusa sobrescrever uma aprovação existente e aceita somente
`experiment/protocol/approvals/cost-review-v1.json` como destino. Dez testes
cobrem adulteração, teto, timestamps, caminho, confirmação e compatibilidade
com o auditor congelado. O preparador sempre grava
`cloud_execution_authorized: false` e não substitui a decisão humana.

O plano do stack isolado foi validado sem aplicação. Com a trava desligada não
há mudança; com a trava ligada aparecem somente a API do BigQuery e o dataset
`US`, sem alterações em GKE, Kubernetes, Artifact Registry, IAM ou orçamento.
A evidência está em
[`billing-export-plan-readiness-20260920T224203Z.json`](./billing-export-plan-readiness-20260920T224203Z.json).

## Fechamento pós-tentativa pareada v1.8

O export posterior ao run `44864048460` passou a cobrir a exclusão do cluster
concluída em `2026-11-21T09:48:53.293223964Z`. A observação limitada a 100 MB
registra R$1.840,812983 de custo bruto, R$4,529938 acima da baseline
pré-reexecução e R$157,455476 de margem até o teto absoluto de
R$1.998,268459. O snapshot está em
[`cost-window-20260919-20261121-v1.8-run44864048460-postdelete-final.json`](./cost-window-20260919-20261121-v1.8-run44864048460-postdelete-final.json).

A revisão
[`post-paired-rerun-financial-review-v1.8-20261121.json`](./post-paired-rerun-financial-review-v1.8-20261121.json)
não cria aprovação nem autorização cloud. Ela somente confirma elegibilidade
financeira para solicitar uma nova decisão humana com envelope máximo reduzido
para R$157,455476. Como a autorização consumida excluía explicitamente o
deployment operacional, a próxima autorização precisa incluir a instalação do
baseline congelado e o preflight de `deployment/loadgenerator` antes de armar o
workflow. Nenhuma mudança de protocolo ou republicação de runtime é necessária.
