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

A geração definitiva v1.2 ocorreu em 24/10/2026 UTC, somente depois da
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

Não existe corpus confirmatório ativo enquanto a v1.3 permanecer em
`pre-registration-candidate`. O próximo `public-corpus.json` só poderá ser
criado depois de nova auditoria 17/17 e congelamento.

Os manifestos e as chaves v1.1 e v1.2 permanecem somente como arquivos
históricos em diretório local privado, com permissões 0600, e nunca podem ser
copiados para este diretório versionado. Nenhuma chave v1.3 existe ainda.
Depois do novo congelamento, o secret protegido
`TCC_ORACLE_BLINDING_KEY_B64` deverá ser substituído exclusivamente pela chave
v1.3 em uma ação remota separada e autorizada.

O mesmo ambiente protegido deve conter:

- `TCC_ORACLE_ARCHIVE_PASSPHRASE`, exclusivo para cifrar as evidências privadas;
- `TCC_ORACLE_EXECUTION_ACKNOWLEDGED=true`, apenas durante uma janela aprovada;
- `TCC_COST_REVIEW_ACKNOWLEDGED=true`, depois da revisão financeira do bloco.

Mesmo com esses valores, o job permanece inelegível sem os labels
`tcc-experiment-cloud`, `tcc-oracle-cloud` e `tcc-cost-reviewed` na revisão
candidata. Cadastrar secrets, habilitar a variável ou aplicar o RBAC são ações
remotas separadas e não são executadas pela simples inclusão deste arquivo.
