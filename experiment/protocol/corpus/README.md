# Corpus confirmatório

O corpus confirmatório da v1.1 foi gerado em 12/10/2026 UTC somente depois do
congelamento 17/17. O arquivo público
[`public-corpus.json`](./public-corpus.json) contém 18 candidatas opacas, três
repetições técnicas por candidata e está vinculado ao protocolo congelado de
SHA-256 `38b1270bce29c4aa975f331d7c5b761e2abe89acd2545cdc11030318ceb4dbaf`.
O corpus anterior da v1 foi invalidado antes de qualquer coleta confirmatória e
permanece recuperável no commit `0ee94a90`, vinculado pelo registro
`../amendments/oracle-v1.1-precollection.json`. A prévia em `../preview/` é
histórica e nunca será promovida.

A geração definitiva criou simultaneamente:

- `public-corpus.json`, versionado e visível aos mecanismos;
- `oracle-manifest.json`, não versionado;
- a chave de cegamento, não versionada.

O manifesto e a chave estão em diretório local privado com permissões 0600,
ignorado pelo Git, e não podem ser copiados para este diretório. O secret
protegido `TCC_ORACLE_BLINDING_KEY_B64` ainda contém a geração anterior e deve
ser rotacionado para a nova chave antes de qualquer execução confirmatória. O
job Oracle derivará novamente o manifesto com código do commit-base confiável
e exigirá igualdade exata com o compromisso público
`958073633288781b956c57e753b9c2525894194823ec2bcd2b81acdf890de523`.

O mesmo ambiente protegido deve conter:

- `TCC_ORACLE_ARCHIVE_PASSPHRASE`, exclusivo para cifrar as evidências privadas;
- `TCC_ORACLE_EXECUTION_ACKNOWLEDGED=true`, apenas durante uma janela aprovada;
- `TCC_COST_REVIEW_ACKNOWLEDGED=true`, depois da revisão financeira do bloco.

Mesmo com esses valores, o job permanece inelegível sem os labels
`tcc-experiment-cloud`, `tcc-oracle-cloud` e `tcc-cost-reviewed` na revisão
candidata. Cadastrar secrets, habilitar a variável ou aplicar o RBAC são ações
remotas separadas e não são executadas pela simples inclusão deste arquivo.
