# Corpus confirmatório

O corpus confirmatório ativo v1.9 foi gerado em 23/11/2026 UTC somente depois
da revisão financeira, aprovação do pesquisador, auditoria pré-freeze 17/17 e
congelamento do protocolo. O corpus `corpus-2p6gcipdrzgxg` contém 18
identificadores opacos, três repetições por candidata e seis blocos de três. Ele
está vinculado ao protocolo congelado de SHA-256
`7bc2c7f10a66152b7d7ec50aafe64cb59ab69ad15a4f8571b4d85485295893ae`,
tem SHA-256
`a6f125cadfe807aff0f45717e8f69e9d3ecbe572202815b6e99c571eae18bac3`
e compromisso Oracle
`3936c0b850c01fc5fea67214bacf9dd1f22d8ea0a5c68179d11fcd95d999c32c`.
A chave e o manifesto Oracle permanecem privados com permissão `0600`; somente
a chave codificada foi instalada no secret protegido. O corpus não autoriza
execução cloud por si só. O recibo sanitizado da rotação está em
[`../../evidence/oracle/corpus-rotation-v1.9-20261123T015519Z.json`](../../evidence/oracle/corpus-rotation-v1.9-20261123T015519Z.json).

A emenda operacional v1.9 retirou o corpus v1.8 da área ativa depois das
tentativas de infraestrutura, sem revelar rótulos Oracle. O arquivo continua
verificável no congelamento histórico abaixo e no commit
`6419521c6a0cd4f90b8d000959dc252f259ab263`.

O corpus confirmatório histórico v1.8 foi gerado em 20/11/2026 UTC somente depois
da auditoria pré-freeze 17/17 e do congelamento do protocolo. O corpus
`corpus-zkf5mounepuhq` contém 18 identificadores opacos, três repetições por
candidata e seis blocos de três. Ele está vinculado ao protocolo congelado de
SHA-256 `c55d9a8d85c2ed3e0d1709e5bb15244723e8b60d1714e29e7d73c79a7438ab86`,
tem SHA-256
`53ab1e6fa4e47d462d5b56556a04c29a4693d00367275208bd214cb5cf909d6f` e
compromisso Oracle
`1a4ab57b897327bd929675a391a04b441b47477883ad0ee219a95213f2de207f`.
A chave e o manifesto Oracle v1.8 permanecem privados com permissão `0600`; não
podem ser reutilizados pela v1.9. O congelamento histórico não autoriza execução cloud.

O corpus confirmatório v1.7 foi gerado em 19/11/2026 UTC somente depois da
auditoria pré-freeze 17/17 e do congelamento do protocolo. O corpus
`corpus-dk3zrooqiepv4` contém 18 identificadores opacos, três repetições por
candidata e seis blocos de três. Ele está vinculado ao protocolo congelado de
SHA-256 `9ae5ed8fb37d4421ad5327a47f3b65631b43a577d6c3b42a96fb031e620c77c4`,
tem SHA-256
`4aa233af1a7a914f532c7dc60dc231b599ed93905ec4631528620ffe4b0c8605` e
compromisso Oracle
`cf770742a0c5458ddc609845580851f1b6dfcb67c06ac625571be57c4747f102`.
A chave e o manifesto Oracle permanecem privados com permissão `0600`. Antes
de qualquer execução v1.7, a emenda de segurança v1.8 invalidou esse corpus
para uso confirmatório sem abrir rótulos. O corpus v1.8 acima o substitui sem
reutilizar candidatas nem revelar rótulos. Nenhum desses passos autoriza
execução cloud por si só.

O corpus confirmatório da v1.1 foi gerado em 12/10/2026 UTC somente depois do
congelamento 17/17, mas foi invalidado antes de qualquer coleta pela emenda de
segurança v1.2. O arquivo público foi retirado da área ativa; a versão anterior
continua verificável no commit `32da279a`, vinculada ao protocolo congelado de
SHA-256 `38b1270bce29c4aa975f331d7c5b761e2abe89acd2545cdc11030318ceb4dbaf`.
O corpus anterior da v1 foi invalidado antes de qualquer coleta confirmatória e
permanece recuperável no commit `0ee94a90`, vinculado pelo registro
`../amendments/oracle-v1.1-precollection.json`. A prévia em `../preview/` é
histórica e nunca será promovida.

A geração v1.2 ocorreu em 24/10/2026 UTC, somente depois da
auditoria pré-freeze 17/17 e do congelamento do protocolo. Ela criou
simultaneamente:

- `public-corpus.json`, versionado e visível aos mecanismos;
- `oracle-manifest.json`, não versionado;
- a chave de cegamento, não versionada.

O corpus `corpus-2ohyzpel2lonq` continha 18 identificadores opacos e três
repetições por candidata e estava vinculado ao protocolo congelado de SHA-256
`8a34f553287d688b2cf38dfa2db6b29caa078bd191ce7d04a03fb5e707870c51`.
Seu compromisso Oracle é
`a49190a3fa83def64b5c0e23321873fe7116c31f4386782a4fe65924b1c60d69`.

Em 24/10/2026, a primeira candidata v1.2 produziu uma decisão convencional
`block` válida e selada, mas um defeito terminal de orquestração impediu o
caminho Oracle pré-artefato. Não houve staging, PDT, execução cloud,
adjudicação Oracle nem abertura do rótulo. A decisão permanece preservada como
fluxo incompleto e não será repetida ou reinterpretada. A emenda autorizada
[`orchestration-v1.3-partial-collection.json`](../amendments/orchestration-v1.3-partial-collection.json)
retirou o corpus v1.2 da área ativa e exige protocolo v1.3, nova chave e novo
corpus antes de retomar a coleta.

Depois da revisão financeira e da aprovação do pesquisador específica para a
coleta parcial, a auditoria v1.3 passou 17/17 e o protocolo foi congelado em
24/10/2026 UTC. Uma chave nova gerou o corpus confirmatório ativo
`corpus-hlwmpwybztcm4`, com 18 identificadores opacos, três repetições por
candidata e seis blocos de três. O arquivo público está vinculado ao protocolo
congelado de SHA-256
`3c6612fc93e1ec5e6e4267d533bdfac0d985fe813420351da3b9648c1afb7b32`
e tem SHA-256
`89bd95cf40e223e3f82b9f70edcf44f4c5a0dd88b080e84121a2daaeb825c760`.
Seu compromisso Oracle é
`f43197555700b8bbdfc0d49395c225107d6806a9d9f53ffa1488510a334c1f49`.

Em 2 de novembro de 2026, a coleta foi pausada porque o cluster ocioso excedeu
os limites financeiros v1.3. A emenda financeira v1.4, autorizada em 9 de
novembro, retirou o corpus v1.3 da área ativa sem abrir rótulos Oracle. Em 10 de
novembro, a auditoria v1.4 passou 17/17, o protocolo foi congelado e uma chave
nova gerou o corpus `corpus-vrvpwrdnmt4hw`. Ele continha 18 identificadores
opacos, três repetições por candidata e seis blocos de três, está vinculado ao
protocolo de SHA-256
`2e6949ca79db0f3be49ab127256a7bcfa1ff7d94e94ed34f6e00ec55a1ea91ed`
e tem SHA-256
`615f5c6dca276d2a4acb93f3fc8110f5bc903c30f1be36b830603946687c2cdd`.
Seu compromisso Oracle é
`5ac57c1540e7a477136db010950dca3b59e9aa4dc1e6375536b34ae1bf95b61c`.

Antes de qualquer execução v1.4, o gate de segurança do PR #16 encontrou CVEs
HIGH corrigíveis. A emenda
[`security-v1.5-preexecution.json`](../amendments/security-v1.5-preexecution.json)
retirou o corpus v1.4 da área ativa e preservou seu hash no registro histórico.
Depois da publicação e dos novos bindings, a revisão financeira e a aprovação
do pesquisador levaram a auditoria v1.5 a 17/17. O protocolo foi congelado e
uma chave nova gerou o corpus `corpus-hojv3asxirypc`. Ele continha 18
identificadores opacos, três repetições por candidata e seis blocos de três,
está vinculado ao protocolo de SHA-256
`331f90ac8b8dde08b96a90e29aaa40f500774f44d3e957b78ba44007cea2fd8a`
e tem SHA-256
`0176797ac596a5df29434dff0faa930c32740271f7ad31f57a1db44fd837116d`.
Seu compromisso Oracle é
`c26c3dbea41f863b397a6d2910c91978f5b6f2284de153776dc4e7fbfbe2bab6`.

Em 17/11/2026, a primeira tentativa v1.5 foi interrompida antes de staging,
PDT e Oracle porque o secret scan pós-autenticação examinou estado temporário
do runner. Nenhum rótulo Oracle foi revelado. A emenda v1.6 preservou a
tentativa como fluxo incompleto, corrigiu o escopo para a árvore Git selada e
exigiu chave e corpus novos. Após auditoria 17/17, o corpus confirmatório ativo
passou a ser `corpus-ajlvmvtukmkia`, com 18 identificadores opacos, três
repetições e seis blocos. Ele está vinculado ao protocolo de SHA-256
`b407d318c6ff793a0c41f01035022af4f749ecdf189862b7ebd8aea7fc509e1d`,
tem SHA-256
`9030a51ababb14b06e08d54e2c5cd0768eacddac45030793d36050a5b5083f72`
e compromisso Oracle
`df6b4e4cc1be28329d88afe01590224a837ab217caea74ac2d6e49b30f1e615a`.

Na primeira candidata v1.6, a esteira preservou uma aprovação convencional
selada depois de três repetições de staging, mas um contrato de precisão de
timestamp interrompeu o PDT antes dos contrafactuais. Não houve decisão PDT,
gate humano, Oracle ou abertura de rótulo. A emenda
[`orchestration-v1.7-controller-timestamp.json`](../amendments/orchestration-v1.7-controller-timestamp.json)
retira o corpus v1.6 da área confirmatória ativa sem reutilizar sua candidata.
O corpus v1.7 descrito no início deste documento foi gerado com chave nova
depois do congelamento 17/17 e da revisão financeira pós-exclusão, e depois
invalidado antes de qualquer execução pela emenda
[`security-v1.8-preexecution.json`](../amendments/security-v1.8-preexecution.json).

Os manifestos e as chaves v1.1 e v1.2 permanecem somente como arquivos
históricos em diretório local privado. As chaves e os manifestos Oracle v1.3,
v1.4, v1.5 e v1.6 também permanecem nos diretórios privados ignorados pelo Git, com
permissões 0600, e nunca podem ser copiados para este diretório versionado. O
secret protegido
`TCC_ORACLE_BLINDING_KEY_B64` contém a chave v1.9 correspondente ao corpus
ativo. O valor permanece oculto e só é disponibilizado ao job Oracle do
ambiente protegido; os kill switches permanecem desarmados.

O mesmo ambiente protegido deve conter:

- `TCC_ORACLE_ARCHIVE_PASSPHRASE`, exclusivo para cifrar as evidências privadas;
- `TCC_ORACLE_EXECUTION_ACKNOWLEDGED=true`, apenas durante uma janela aprovada;
- `TCC_COST_REVIEW_ACKNOWLEDGED=true`, depois da revisão financeira do bloco.

Mesmo com esses valores, o job permanece inelegível sem os labels
`tcc-experiment-cloud`, `tcc-oracle-cloud` e `tcc-cost-reviewed` na revisão
candidata. Cadastrar secrets, habilitar a variável ou aplicar o RBAC são ações
remotas separadas e não são executadas pela simples inclusão deste arquivo.
