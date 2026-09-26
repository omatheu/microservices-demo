# Corpus confirmatório

Este diretório receberá somente `public-corpus.json`, depois que o protocolo,
o runtime PDT e a suíte independente do Oracle estiverem congelados. A prévia
em `../preview/` é histórica, usa outra chave e nunca será promovida.

A geração definitiva deve criar uma chave aleatória nova de pelo menos 32
bytes e produzir simultaneamente:

- `public-corpus.json`, versionado e visível aos mecanismos;
- `oracle-manifest.json`, não versionado;
- a chave de cegamento, não versionada.

O manifesto e a chave não podem ser copiados para este diretório. A chave será
registrada como secret protegido `TCC_ORACLE_BLINDING_KEY_B64` somente depois
de a geração local ser validada. O job Oracle deriva novamente o manifesto com
código do commit-base confiável e exige igualdade exata com o compromisso do
corpus público.

O mesmo ambiente protegido deve conter:

- `TCC_ORACLE_ARCHIVE_PASSPHRASE`, exclusivo para cifrar as evidências privadas;
- `TCC_ORACLE_EXECUTION_ACKNOWLEDGED=true`, apenas durante uma janela aprovada;
- `TCC_COST_REVIEW_ACKNOWLEDGED=true`, depois da revisão financeira do bloco.

Mesmo com esses valores, o job permanece inelegível sem os labels
`tcc-experiment-cloud`, `tcc-oracle-cloud` e `tcc-cost-reviewed` na revisão
candidata. Cadastrar secrets, habilitar a variável ou aplicar o RBAC são ações
remotas separadas e não são executadas pela simples inclusão deste arquivo.
