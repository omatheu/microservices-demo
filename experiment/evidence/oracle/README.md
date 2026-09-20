# Evidências do oráculo

Este diretório contém somente execuções posteriores à separação entre os
mecanismos de decisão e o oráculo. Pilotos com `evidence_classification` igual
a `engineering-only` validam a infraestrutura e a suíte, mas não podem entrar
na comparação principal.

## Piloto funcional v1

[`oracle-functional-harness-v1-20260920T173602Z/`](./oracle-functional-harness-v1-20260920T173602Z/)
registra a primeira execução integrada local do harness contra o
`checkoutservice` compilado da árvore de engenharia:

- 30 combinações de moeda, quantidade de itens e quantidade por item;
- cartão não aceito, expirado e número inválido;
- indisponibilidade controlada de pagamento e frete;
- 35 resultados brutos com hash individual;
- nove asserções funcionais aprovadas.

A execução não usou GKE, não publicou imagem, não consultou o manifesto cego e
não gerou custo cloud. Como a árvore estava suja, o protocolo e a política não
estavam congelados e o candidato era conhecido, ela é exclusivamente uma
evidência de engenharia.
