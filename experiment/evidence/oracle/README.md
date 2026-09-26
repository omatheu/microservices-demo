# Evidências do oráculo

O snapshot somente leitura mais recente
[`oracle-execution-readiness-preinstall-20260926T163506Z.json`](./oracle-execution-readiness-preinstall-20260926T163506Z.json)
registra o estado anterior à instalação dos controles Oracle: 12/22 checks
passaram, nenhuma falha de coleta ocorreu, o namespace estava vazio e nenhuma
execução foi autorizada. Ele deve ser preservado para comparação com a futura
auditoria pós-instalação. O snapshot anterior permanece como trilha da revisão
que revelou a normalização `namespace: default` do sujeito Kubernetes.

Este diretório contém somente execuções posteriores à separação entre os
mecanismos de decisão e o oráculo. Pilotos com `evidence_classification` igual
a `engineering-only` validam a infraestrutura e a suíte, mas não podem entrar
na comparação principal.

## Validação pré-artefato de 26/09/2026

[`preartifact-engineering-validation-20260926T170744Z.json`](./preartifact-engineering-validation-20260926T170744Z.json)
registra uma execução local de todas as quatro candidatas pré-artefato de um
corpus de engenharia recém-gerado para o protocolo atual. As quatro decisões
convencionais foram bloqueadas e seladas antes da abertura do item privado; as
quatro verificações independentes foram válidas, observaram dano e concordaram
com o rótulo reservado.

Foram exercitados os três verificadores: `go test` independente em duas
instâncias de regressão unitária, busca redigida do canário de segredo e
inspeção do manifesto renderizado com privilégio proibido. O registro contém
somente hashes e resultados sanitizados. Chave, manifesto privado, patches,
work orders, itens privados e logs brutos foram temporários. Não houve staging,
PDT, acesso ao GCP, publicação de imagem ou mutação operacional. O corpus era
rascunho e nenhuma observação é elegível para a análise principal.

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
