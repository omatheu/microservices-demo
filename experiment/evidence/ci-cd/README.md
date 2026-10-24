# Evidências da CI/CD convencional

Cada execução local cria um diretório ignorado pelo Git com metadados, logs,
relatórios dos scanners, SBOM, resultados por gate e uma decisão pré-staging.

O conteúdo gerado só constitui evidência confirmatória quando o protocolo e a
política estiverem congelados e a execução usar `MODE=confirmatory`.

## Regressão de segurança pré-coleta e emenda v1.2 em 12/10/2026

O gate de imagens do PR #12 bloqueou corretamente o `oracle-harness` por quatro
achados HIGH corrigíveis: `CVE-2026-78669` em `golang.org/x/net` e três achados
na biblioteca padrão Go. A política do scanner não foi alterada. O registro
sanitizado [`runtime-security-regression-pr12-20261012.json`](runtime-security-regression-pr12-20261012.json)
vincula o run, o job e os SHA-256 dos artefatos baixados. Não houve publicação,
execução GCP ou observação confirmatória.

A emenda v1.2 atualiza Go para 1.27.3, `golang.org/x/net` para v0.60.0 e o
runtime Alpine do `currency-reference` para 3.24.3; ela invalida
os vínculos de runtime, aprovações e corpus v1.1 e exige que o mesmo gate passe
antes de uma nova publicação protegida.

O preflight local da correção reconstruiu as três imagens, gerou SBOMs e repetiu
o Trivy fixado com a mesma política. As três passaram com zero achados
HIGH/CRITICAL corrigíveis; o SBOM do `oracle-harness` confirma Go 1.27.3 e
`golang.org/x/net` v0.60.0. O `checkoutservice`, que compartilha o módulo e o
builder corrigidos, também foi reconstruído e passou no mesmo scan. Uma nova
regressão em 24/10/2026 foi bloqueada antes da publicação: `CVE-2026-111943`
no Go 1.27.2 e quatro achados no runtime Alpine/Node do `currency-reference`.
Os registros sanitizados estão em
[`runtime-security-regression-pr12-20261024.json`](runtime-security-regression-pr12-20261024.json)
e
[`runtime-security-remediation-v1.2-local-20261024.json`](runtime-security-remediation-v1.2-local-20261024.json).
Ela não é proveniência de publicação nem evidência confirmatória.

## Publicação protegida dos runtimes da emenda v1.2 em 24/10/2026

Depois de bloquear os CVEs recém-publicados, o PR #12 repetiu a CI no commit
`6a39f7f77206c229144dd593560536cdad607825`. As três imagens passaram pelo
build, SBOM e Trivy com a política HIGH/CRITICAL inalterada e foram publicadas
no caminho protegido, sem credenciais GKE. Staging, PDT, gate humano e Oracle
foram explicitamente ignorados pelo workflow.

O resumo auditável
[`runtime-publication-pr12-20261024T154243Z.json`](runtime-publication-pr12-20261024T154243Z.json)
vincula o commit, a árvore Git, o run protegido, os relatórios e os digests
imutáveis. Os manifests PDT e Oracle compartilham exatamente a mesma
proveniência. Depois do job, a chave de publicação voltou a `false` e os
rótulos cloud foram removidos do PR.

## Publicação protegida dos runtimes da emenda v1.1 em 05/10/2026

O PR #10 executou o caminho isolado `runtime-publication` no commit
`450e17aabc1e1b6783aec4ba022ac471886f2af5`. O job protegido construiu,
gerou SBOM, escaneou e publicou `checkout-pdt-controller`, `oracle-harness` e
`currency-reference`; as três análises passaram sem achados HIGH/CRITICAL
corrigíveis. Staging, PDT, gate humano e Oracle foram ignorados, e o workflow
não recebeu credenciais GKE.

O resumo auditável, com os digests imutáveis, hashes dos relatórios, árvore
Git, PR, workflow e ambiente protegido, está em
[`runtime-publication-pr10-20261005T214319Z.json`](runtime-publication-pr10-20261005T214319Z.json).
Os manifests PDT e Oracle vinculam exatamente o SHA-256 desse resumo. Após o
job, a chave financeira exclusiva voltou a `false` e todos os rótulos cloud
foram removidos do PR.

## Matriz local das candidatas de runtime em 26/09/2026

As 14 candidatas de runtime do corpus de engenharia `corpus-bfgvbgq63vyd4`
foram materializadas e seladas separadamente sobre o commit `c32a34b2`. Cada
uma percorreu os 22 gates locais da CI convencional, build das imagens
afetadas, geração de SBOM e scans de filesystem e imagem.

O resultado foi 13 `PASS` e um `BLOCK`. As quatro candidatas seguras passaram;
entre as dez prejudiciais, nove passaram e `FUNC-AMOUNT-01` foi bloqueada pelos
testes unitários e contratos semânticos. Foram 17 validações de artefato — 14
do `checkoutservice` e uma de cada `paymentservice`, `currencyservice` e
`recommendationservice` — todas com zero achados HIGH/CRITICAL.

A preparação revelou dois vieses de infraestrutura, e as rodadas afetadas
foram descartadas: o adaptador Python não permitia atualizar bytecode como
usuário não privilegiado, e o autoteste do materializador reutilizava o arquivo
já mutado da candidata como fixture. A rodada registrada usa fontes do
commit-base para o autoteste e uma imagem Python gravável somente pelo UID/GID
`10001`, sem conceder privilégios.

O registro sanitizado está em
[`runtime-candidate-matrix-preflight-20260926T200948Z.json`](runtime-candidate-matrix-preflight-20260926T200948Z.json).
Ele é somente evidência de prontidão de engenharia: não houve staging, PDT,
GCP, registry ou publicação de imagens; os worktrees, patches, ordens de
trabalho e logs privados foram destruídos após a extração dos hashes. Volumes
Docker não foram removidos nem modificados. Como os rótulos foram revelados e
versionados depois dessa execução, esse corpus fica aposentado para qualquer
coleta confirmatória. Um novo corpus cego v1.1 foi gerado somente após o
congelamento 17/17 de 12/10/2026.

## Preflight local das imagens de runtime em 26/09/2026

As três imagens adicionais necessárias ao PDT e ao oráculo foram reconstruídas
no commit `4504cfab`. Os três SBOMs foram gerados e os scans fixados da esteira
encontraram zero vulnerabilidades HIGH/CRITICAL. Nenhuma imagem foi publicada,
nenhum recurso GCP foi acessado ou alterado e a execução continua inelegível
como evidência confirmatória ou proveniência de publicação.

A soma conservadora dos tamanhos locais foi de `228.203.127` bytes. Somada ao
inventário remoto previamente observado, a projeção é `236.046.622` de
`500.000.000` bytes, com `263.953.378` bytes de margem sob a franquia assumida.
Isso não constitui garantia de cobrança nem autorização financeira. O registro
auditável está em
[`runtime-image-preflight-20260926T164347Z.json`](runtime-image-preflight-20260926T164347Z.json).

## Validação de engenharia de 20/09/2026

A execução `ci-engineering-artifact-binding-v2-20260920T063313Z` aprovou os 20
gates para o `checkoutservice` e publicou exatamente o artefato validado em:

`us-central1-docker.pkg.dev/microservices-demo-tcc/online-boutique-experiment/checkoutservice@sha256:fc60c11a7146a53a5f87df486517453b4c91073e919d0d0b6342c5a318a3734f`

A decisão registra build, SBOM, scan, publicação e digest. A imagem local foi
removida depois do envio. Uma tentativa anterior sem helper de credenciais
falhou fechada no gate de publicação e não gerou referência remota.

A execução `ci-engineering-protobuf-gate-20260920T060133Z` aprovou os 20 gates
obrigatórios depois da integração da validação protobuf. Ela compilou o
contrato canônico, comparou-o com `HEAD`, validou os espelhos, o subconjunto C#,
os descriptors e os métodos gRPC gerados. A candidata explícita alterava apenas
o controle experimental; por isso nenhum artefato de serviço foi construído,
nenhum recurso cloud foi acessado e o resultado continua sendo apenas evidência
de engenharia.

A execução `ci-engineering-frozen-sast-20260920T055029Z` aprovou os 19
gates obrigatórios para uma seleção de engenharia do `checkoutservice`,
incluindo contratos semânticos, seleção de componente e validação consolidada
do artefato:

- `local_decision: pass`;
- `eligible_for_staging: true`;
- `confirmatory_eligible: false`;
- zero gates obrigatórios com falha;
- build, SBOM e scan da imagem aprovados;
- ruleset SAST local com hash validado e canário adversarial detectado;
- imagem local removida depois da análise;
- nenhum recurso cloud criado.

Essa rodada usou a fixture explícita
`checkout-only.changed-files.txt` para não baixar e construir todas as imagens
em um host com pouco espaço. O modo confirmatório não aceita esse mecanismo: a
seleção terá de ser derivada do intervalo Git limpo da candidata. Os adaptadores
de `shippingservice`, `productcatalogservice`, `frontend`, `paymentservice`,
`currencyservice`, `cartservice` e `emailservice` foram exercitados
separadamente; ainda não há uma execução integral multi-serviço.

Uma execução anterior bloqueou corretamente a candidata ao detectar um erro do
`go vet`, execução da imagem como usuário root e problemas na configuração
inicial do scanner. Esses pontos foram corrigidos antes da execução aprovada.
Isso valida a mecânica de bloqueio do runner, mas não transforma nenhum dos
dois resultados em evidência do experimento principal.

Os diretórios completos de execução são deliberadamente ignorados pelo Git por
conterem artefatos volumosos. A coleta confirmatória deverá publicar o pacote
imutável de evidências no destino de retenção definido pelo protocolo, junto
dos hashes e da decisão convencional consolidada.

## Preflight local dos runtimes experimentais de 22/09/2026

As três imagens experimentais foram reconstruídas para o commit
`6ecffab7d03fca1ae434515ef2b6ab5c55caf989` em `linux/amd64`, com Syft e
Trivy fixados por digest. Os três SBOMs foram gerados e as três varreduras
retornaram zero achados HIGH/CRITICAL corrigíveis. O limite superior adicional
foi de 228.203.127 bytes; somado ao armazenamento observado na conta, a
projeção conservadora é 236.046.622 de 500.000.000 bytes.

O registro está em
[`runtime-image-preflight-20260922T021540Z.json`](./runtime-image-preflight-20260922T021540Z.json).
Ele é evidência de engenharia local, não evidência de publicação: não houve
acesso ao GCP, push ou autorização cloud. A comparação com o artefato anterior
da CI também mostrou que rebuilds não preservam o mesmo image ID apesar de os
inputs materiais não terem mudado. Por isso o protocolo não pressupõe
reprodutibilidade bit-a-bit; o job protegido deve escanear exatamente a imagem
que enviará, vincular os hashes dos relatórios brutos e congelar o digest
retornado pelo registry.

O contrato entre publicação e binding também possui uma simulação local ponta
a ponta em
[`../../ci/tests/test_runtime_publication_integration.py`](../../ci/tests/test_runtime_publication_integration.py).
Ela substitui somente os comandos `docker` e `gcloud` por dublês locais,
executa o publisher real, gera relatórios CycloneDX/Trivy sintéticos, passa o
mesmo `summary.json` pelo binder real e comprova que a ausência de qualquer uma
das duas autorizações interrompe o fluxo antes da criação de artefatos. O teste
não acessa rede ou cloud e não simula sucesso alterando o código de produção.
