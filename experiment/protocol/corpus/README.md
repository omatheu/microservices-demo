# Corpus confirmatório

Este diretório está intencionalmente sem um `public-corpus.json` ativo durante
a preparação da emenda Oracle v1.1. O corpus congelado em 04/10/2026 foi
invalidado antes de qualquer coleta confirmatória e permanece recuperável no
commit `0ee94a90`, vinculado pelo registro
`../amendments/oracle-v1.1-precollection.json`. A prévia em `../preview/` é
histórica e nunca será promovida.

A próxima geração definitiva, somente depois do novo congelamento 17/17,
criará uma chave aleatória nova e produzirá simultaneamente:

- `public-corpus.json`, versionado e visível aos mecanismos;
- `oracle-manifest.json`, não versionado;
- a chave de cegamento, não versionada.

O manifesto e a chave não podem ser copiados para este diretório. O secret
protegido `TCC_ORACLE_BLINDING_KEY_B64` ainda contém a geração anterior e deve
ser rotacionado, nunca reutilizado, quando o novo corpus for criado. O job
Oracle derivará novamente o manifesto com código do commit-base confiável e
exigirá igualdade exata com o novo compromisso público.

O mesmo ambiente protegido deve conter:

- `TCC_ORACLE_ARCHIVE_PASSPHRASE`, exclusivo para cifrar as evidências privadas;
- `TCC_ORACLE_EXECUTION_ACKNOWLEDGED=true`, apenas durante uma janela aprovada;
- `TCC_COST_REVIEW_ACKNOWLEDGED=true`, depois da revisão financeira do bloco.

Mesmo com esses valores, o job permanece inelegível sem os labels
`tcc-experiment-cloud`, `tcc-oracle-cloud` e `tcc-cost-reviewed` na revisão
candidata. Cadastrar secrets, habilitar a variável ou aplicar o RBAC são ações
remotas separadas e não são executadas pela simples inclusão deste arquivo.
