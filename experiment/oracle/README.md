# Oráculo independente do experimento

O oráculo não é parte do PDT e não participa da decisão pré-deployment. Sua
função é produzir o resultado observado usado para avaliar, depois do fato,
tanto a esteira convencional quanto a mesma esteira acrescida do PDT.

## Ordem obrigatória

```text
CI/CD convencional + staging -> decisão de controle selada
                             -> PDT -> decisão de tratamento selada
                                    -> gate sem mutação operacional
                                           -> liberação do item privado
                                                  -> execução no oracle
                                                         -> relatório de fidelidade
                                                                -> adjudicação
```

Se o controle bloquear a candidata, o tratamento herda o bloqueio e o PDT não
é executado. A liberação ainda ocorre somente depois de a decisão convencional
estar selada. Se o controle aprovar, a liberação exige a decisão PDT, o gate
terminal e identidade exata de artefato e configuração entre as condições. Se
o PDT selecionar `approve` ou `reconfigure`, a barreira também exige o recibo
do ambiente protegido, a ação preparada e o histórico bruto de aprovação do
GitHub. Se o PDT selecionar `block`, nenhuma ação deployável existe para ser
aprovada; o gate deve estar terminalmente bloqueado e o oráculo segue apenas
com as travas financeiras da avaliação.

Um bloqueio anterior ao build não elimina a candidata do corpus. Como não há
imagem que possa ser implantada, ele segue um caminho de oráculo pré-artefato:
o commit candidato, a árvore Git, o patch privado e as decisões já seladas são
conferidos por hash; em seguida, uma verificação independente reproduz a
propriedade violada. O tratamento herda o bloqueio convencional, portanto esse
caso mede se a esteira básica detecta o que deveria detectar — não um ganho do
PDT.

O script `unlock-oracle-candidate.py` implementa essa barreira. O recibo
público não contém operador, parâmetros ou rótulo. O item privado tem permissão
`0600` e só pode ser usado pelo executor do oráculo depois do fechamento das
decisões. Para ações deployáveis ele reutiliza o mesmo validador fail-closed do
runner, de modo que o manifesto privado não é revelado antes da aprovação
humana protegida.

## Ambiente

O overlay [`../../infra/kustomize/oracle/`](../../infra/kustomize/oracle/)
renderiza a Online Boutique em um namespace próprio, sem `LoadBalancer` e sem
carga contínua. A configuração Terraform atribui quota máxima de 3 vCPU de
requests, 6 GiB de memória de requests e 20 pods; são limites, não reservas.
O namespace e a quota já foram aplicados ao cluster; permanecem vazios até uma
janela explicitamente autorizada.

Cada repetição deve:

1. limpar o namespace;
2. implantar exatamente os mesmos digests e a mesma definição candidata
   selados pelo controle;
3. executar a matriz funcional independente e os três perfis definidos em
   `policy-v1.json`;
4. coletar disponibilidade, reinícios e duplicidade de efeitos;
5. persistir uma observação por alternativa e repetição;
6. comparar a observação com a previsão PDT já selada, quando ela existir;
7. limpar todos os workloads antes da execução seguinte.

O runner [`../scripts/run-oracle-repetition.sh`](../scripts/run-oracle-repetition.sh)
implementa esse ciclo para uma alternativa implantável. Isso inclui candidatas
aprovadas pelo controle e candidatas bloqueadas somente depois de staging,
desde que estas ainda possuam os artefatos imutáveis selados. Ele verifica a identidade da candidata, a
permissão `0600` do item privado, o hash da definição, os digests imutáveis, o
snapshot do cluster e o namespace vazio antes de aplicar o runtime mínimo.
Quando o controle aprovou e o PDT selecionou uma ação, o runner também exige a
decisão PDT, o gate, a ação, o recibo humano e o histórico bruto de aprovação
do GitHub. `validate-human-gate-receipt.py` recompõe todos os hashes e exige
uma aprovação do ambiente protegido antes de qualquer chamada ao Kubernetes.
Essa aprovação continua vinculada à ação escolhida, mas não restringe a matriz
de avaliação independente: depois do selo, o oráculo pode executar qualquer
alternativa implantável que já conste da definição candidata e da lista de
contrafactuais efetivamente avaliados pelo PDT. Isso é necessário para
classificar `deploy-as-is`, verificar reconfigurações e determinar a melhor
ação sem alterar a decisão histórica.
Uma candidata bloqueada pelo controle não possui ação PDT para aprovar e segue
o caminho independente de adjudicação/oráculo já selado.
Falhas funcionais da candidata não encerram o runner: o harness permanece
disponível e as transforma em observações. Falhas do harness ou da referência
independente invalidam a execução.

O orquestrador candidata-nível
[`../scripts/run-oracle-candidate.py`](../scripts/run-oracle-candidate.py)
executa esse runner sequencialmente para o produto cartesiano de todas as
alternativas implantáveis e das três repetições. Antes de liberar o item
privado, ele confere o término da esteira pareada, o snapshot canônico
`oracle-binding-snapshot.json`, os hashes das previsões por repetição, o ledger
pré-rótulo e, quando aplicável, a cadeia do gate humano. Depois da matriz, ele
encadeia adjudicação e agregação de fidelidade. Os artefatos que contêm
operador, parâmetros, rótulo pretendido ou resultado adjudicado ficam em
`private/` com permissões restritivas; `public/summary.json` contém apenas
identidades opacas, contagens e hashes e é recusado se qualquer chave privada
aparecer em qualquer profundidade.

As esteiras pareadas de uma e de três repetições agora persistem o mesmo nome
canônico de snapshot. Quando staging bloqueia depois do build, esse snapshot é
capturado depois do selo da decisão e antes da liberação do rótulo. Quando o
controle aprova, ele é exatamente o snapshot da última repetição PDT válida
que alimenta a ação agregada. Assim, ambos os caminhos permanecem vinculados à
mesma instância operacional sem depender de caminhos temporários do runner.

Para bloqueios anteriores ao build,
[`../scripts/prepare-sealed-preartifact-inputs.py`](../scripts/prepare-sealed-preartifact-inputs.py)
reconstrói o patch e o work order privados a partir do único commit candidato,
da árvore e do commit-base que a CI já selou. O preparador usa operador e
parâmetros do manifesto privado, mas nunca copia o rótulo pretendido para o
work order. Isso permite repetir a verificação independente sem versionar
metadados do Oracle e sem executar scripts da revisão candidata com acesso à
chave de cegamento.

O workflow protegido contém um job Oracle separado, desarmado por padrão. Ele
exige simultaneamente o label `tcc-oracle-cloud`, protocolo congelado, revisão
financeira e a variável `TCC_ORACLE_EXECUTION_ACKNOWLEDGED=true`. Os scripts são
carregados do commit-base confiável da `main`; a revisão candidata é tratada
somente como fonte selada de dados e imagem. A chave HMAC aparece apenas no
passo que deriva o manifesto privado e é removida em seguida. Evidência com
operador, parâmetros, observações e adjudicação é cifrada com GnuPG antes de
ser persistida; somente recibo, índices e hashes sem rótulo são enviados como
artefato público. Um cleanup explícito e limitado ao namespace `oracle` é
executado mesmo quando a coleta falha.

Antes de habilitar qualquer uma dessas travas, o auditor somente leitura
[`../scripts/audit-oracle-execution-readiness.py`](../scripts/audit-oracle-execution-readiness.py)
deve aprovar 22 controles. Ele confere o workflow exato em `main`, ambiente
protegido, labels, nomes de secrets, kill switches desligados, PR próprio e
desarmado, identidade OIDC sem chave, papéis de projeto exatos, provider
restrito, Role/RoleBinding mínimo no namespace `oracle`, namespace sem workload,
protocolo e runtimes congelados e corpus confirmatório ligado pelo hash do
protocolo. O auditor não lê valores de secrets, não altera GitHub/GCP/Kubernetes
e nunca autoriza a execução.

```bash
python3 experiment/scripts/audit-oracle-execution-readiness.py \
  --pull-request <numero-do-pr> \
  --repo-root . \
  --require-ready
```

Em 26/09/2026 UTC, a primeira leitura real passou em 12 dos 22 controles após
distinguir ausências confirmadas de falhas de coleta. Os bloqueios são
deliberados: workflow Oracle ainda local, label e secrets ainda ausentes, kill
switch Oracle ainda não cadastrado, RBAC ainda não aplicado, protocolo/runtimes
ainda não congelados, corpus final ainda inexistente e nenhum PR aberto. A
identidade sem chave, os três papéis mínimos, o provider OIDC, a proteção do
ambiente, o namespace correto e sua ausência de workloads foram confirmados.
A evidência está em
[`../evidence/oracle/oracle-execution-readiness-preinstall-20260926T162843Z.json`](../evidence/oracle/oracle-execution-readiness-preinstall-20260926T162843Z.json).

Exemplo de invocação, somente depois do congelamento e da revisão financeira:

```bash
MODE=confirmatory \
CANDIDATE_ID=cand-exemplo \
CANDIDATE_DEFINITION=/caminho/candidate-definition.json \
CONVENTIONAL_DECISION=/caminho/conventional-decision.json \
PDT_DECISION=/caminho/pdt-decision.json \
PDT_PREDICTION_DECISION=/caminho/pdt-decision-repeticao-1.json \
DEPLOYMENT_GATE=/caminho/gate.json \
DEPLOYMENT_ACTION=/caminho/deployment-action.json \
HUMAN_GATE_DECISION=/caminho/human-gate-decision.json \
GITHUB_APPROVAL_HISTORY=/caminho/github-environment-approvals.json \
PRIVATE_WORK_ITEM=/caminho/private-work-item.json \
SNAPSHOT_FILE=/caminho/pdt-input-state.json \
ALTERNATIVE_ID=deploy-as-is REPETITION=1 \
ORACLE_HARNESS_IMAGE='REGISTRY/oracle-harness@sha256:DIGEST' \
CURRENCY_REFERENCE_IMAGE='REGISTRY/currency-reference@sha256:DIGEST' \
ALLOW_EXPERIMENTAL_CLOUD_EXECUTION=true \
COST_REVIEW_ACKNOWLEDGED=true \
ALLOW_ORACLE_CLOUD_EXECUTION=true \
  ./experiment/scripts/run-oracle-repetition.sh
```

As três travas são obrigatórias. A existência do comando acima não constitui
autorização de execução. Em modo de engenharia, duração e usuários podem ser
reduzidos com `ENGINEERING_DURATION_SECONDS` e `ENGINEERING_USERS`; esses
overrides são rejeitados em modo confirmatório.

## Independência e não vazamento

- staging e PDT recebem as mesmas invariantes públicas;
- nenhum deles recebe o operador, seus parâmetros ou o rótulo pretendido;
- o oráculo pode usar os parâmetros revelados para ativar entradas e falhas,
  mas sua classificação é calculada exclusivamente pelas asserções e métricas;
- `intended_label` aparece somente depois da adjudicação, para verificar se a
  mutação produziu o efeito previsto pelo desenho;
- uma discordância entre intenção e observação não é reclassificada
  manualmente: é registrada como resultado do operador.

## Política e estado atual

[`policy-v1.json`](./policy-v1.json) define nove invariantes funcionais, três
perfis de desempenho, limites de saúde e a regra de duas repetições prejudiciais
entre pelo menos duas válidas. `adjudicate-oracle.py` já implementa e testa essa
regra sem usar o rótulo pretendido como entrada da classificação.

[`suite-manifest.json`](./suite-manifest.json) vincula por SHA-256 os 27
arquivos que definem a política, o harness, os avaliadores e o runner. O
validador `validate-oracle-suite.py` falha se qualquer arquivo mudar. O
manifesto permanece `pre-registration-candidate` e seus dois digests de imagem
permanecem nulos até o build, publicação e validação deliberados; ele não pode
ser marcado como `frozen` nesse estado.

O inventário inclui o binder e o próprio validador. Quando existirem imagens
publicadas, os digests de `oracle-harness` e `currency-reference` só serão
aceitos com a mesma proveniência de publicação usada pelo controlador PDT;
referências manuais, outro registry ou execuções sem as travas protegidas são
recusadas.

O harness independente em [`harness/`](./harness/) já fornece doubles gRPC,
proxies opcionais para dependências candidatas, matriz funcional, perfis de
carga e coleta de efeitos. Os scripts `run-oracle-functional-suite.py`,
`evaluate-oracle-functional.py`, `run-oracle-performance-profile.py` e
`compose-oracle-observation.py` produzem a observação no schema consumido pelo
adjudicador. `prepare-oracle-runtime.py` gera um runtime Kubernetes mínimo,
privado e vinculado aos mesmos artefatos selados pelo controle, e
`run-oracle-repetition.sh` encadeia validação do gate humano, deployment,
medições, composição e cleanup.

Quando há previsão PDT, o runner também chama
[`../scripts/calculate-pdt-fidelity.py`](../scripts/calculate-pdt-fidelity.py).
Em uma coleta repetida, `PDT_DECISION` aponta para a decisão candidata-nível
que alimentou o gate humano, enquanto `PDT_PREDICTION_DECISION` aponta para a
previsão daquela repetição. O runner confere que o hash dessa previsão aparece
na lista de inputs da decisão agregada antes de calcular fidelidade. Em pilotos
de uma única repetição, a segunda variável pode ser omitida e a decisão única é
reutilizada. Essa separação impede comparar a observação de uma repetição com
uma mediana agregada ou com o snapshot errado.
Se uma repetição PDT permaneceu inválida depois da substituição permitida,
`PDT_PREDICTION_DECISION` fica ausente e
`PDT_INVALID_REPETITION_LEDGER` deve provar as duas falhas anteriores à abertura
do rótulo. O oráculo ainda mede o resultado real daquela repetição, mas não
inventa uma previsão nem um erro de fidelidade; o agregado usa somente a matriz
completa das duas ou três repetições PDT válidas.
O relatório `pdt-fidelity.json` compara sucesso, p95/p99 do checkout,
indisponibilidade e reinícios da mesma candidata, alternativa e repetição. Ele
registra erro assinado, absoluto e relativo, além da concordância entre a
classificação prevista e a observada. Observação zero mantém erro relativo
como `null`; não há imputação. A política
[`../pdt/fidelity-policy.json`](../pdt/fidelity-policy.json) proíbe que o
relatório altere a decisão ou recalibre o modelo com o corpus confirmatório.

Depois de completar todas as alternativas e repetições de uma candidata,
[`../scripts/aggregate-pdt-fidelity.py`](../scripts/aggregate-pdt-fidelity.py)
exige a matriz cartesiana inteira de alternativas por repetições PDT válidas
antes de produzir o agregado candidata-nível. Três repetições são planejadas;
duas só são aceitas quando o ledger pré-rótulo comprova que a tentativa original
e a única substituta da terceira falharam por infraestrutura. Relatório ausente
sem ledger, duplicado, misto entre engenharia/confirmatório ou com aritmética
adulterada é recusado. Assim, repetições técnicas não são tratadas indevidamente
como unidades experimentais independentes nem inventadas por imputação.

O manifesto de coleta referencia esse agregado em `pdt_fidelity` para toda
candidata aprovada pelo controle. O compositor verifica o hash e a matriz, e o
analisador final resume a concordância e as medianas de erro entre candidatas.
Candidatas bloqueadas pelo controle não executam o PDT e registram fidelidade
como não aplicável.

Para candidatas bloqueadas antes de existir artefato,
[`../scripts/evaluate-oracle-preartifact.py`](../scripts/evaluate-oracle-preartifact.py)
confere a ligação exata entre definição, item privado, ordem de trabalho, patch,
commit/árvore e evidência da CI. Depois executa uma verificação independente:
`go test` em imagem fixada para falhas de compilação/teste, busca redigida do
canário sintético de segredo ou inspeção do manifesto renderizado para
privilégio proibido. Falha da ferramenta é classificada como execução inválida,
nunca como dano. O rótulo pretendido só é comparado depois de calculado o
rótulo observado.

Ainda falta validar o runner no cluster contra todas as imagens materializadas,
validar o caminho pré-artefato contra as candidatas materializadas, publicar e
congelar os digests do harness e da referência. Até isso acontecer, a política
permanece `pre-registration-candidate` e nenhuma observação pode ser incluída
na análise principal.
