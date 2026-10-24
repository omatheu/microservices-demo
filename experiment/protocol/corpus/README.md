# Corpus confirmatório

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

Os manifestos e as chaves v1.1 e v1.2 permanecem somente como arquivos
históricos em diretório local privado. A chave e o manifesto Oracle v1.3 também
permanecem somente no diretório privado ignorado pelo Git, com permissões 0600,
e nunca podem ser copiados para este diretório versionado. O secret protegido
`TCC_ORACLE_BLINDING_KEY_B64` ainda não foi alterado; sua substituição pela
chave v1.3 exige uma ação remota separada e autorizada.

O mesmo ambiente protegido deve conter:

- `TCC_ORACLE_ARCHIVE_PASSPHRASE`, exclusivo para cifrar as evidências privadas;
- `TCC_ORACLE_EXECUTION_ACKNOWLEDGED=true`, apenas durante uma janela aprovada;
- `TCC_COST_REVIEW_ACKNOWLEDGED=true`, depois da revisão financeira do bloco.

Mesmo com esses valores, o job permanece inelegível sem os labels
`tcc-experiment-cloud`, `tcc-oracle-cloud` e `tcc-cost-reviewed` na revisão
candidata. Cadastrar secrets, habilitar a variável ou aplicar o RBAC são ações
remotas separadas e não são executadas pela simples inclusão deste arquivo.
