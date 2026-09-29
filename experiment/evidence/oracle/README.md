# Evidências do oráculo

O snapshot somente leitura mais recente
[`oracle-execution-readiness-post-passive-20260929T055153Z.json`](./oracle-execution-readiness-post-passive-20260929T055153Z.json)
registra o estado posterior ao lote passivo: 18/22 checks passaram, equivalentes
a 18/21 controles estruturais e 0/1 controle de candidata. Role, RoleBinding,
label, variável desabilitada e nomes dos dois secrets foram confirmados; o
namespace permaneceu vazio e nenhuma execução foi autorizada.

O recibo de instalação dos controles GitHub está em
[`oracle-passive-github-controls-installation-20260929T054946Z.json`](./oracle-passive-github-controls-installation-20260929T054946Z.json),
e a releitura idempotente está em
[`oracle-passive-github-controls-post-install-readiness-20260929T055153Z.json`](./oracle-passive-github-controls-post-install-readiness-20260929T055153Z.json).
Ambos omitem valores secretos e confirmam o kill switch em `false`.

O snapshot
[`oracle-execution-readiness-preinstall-20260926T163506Z.json`](./oracle-execution-readiness-preinstall-20260926T163506Z.json)
preserva o estado anterior à instalação: 12/22 checks passaram, nenhuma falha
de coleta ocorreu e nenhuma execução foi autorizada. O snapshot anterior
permanece como trilha da revisão que revelou a normalização
`namespace: default` do sujeito Kubernetes.

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
