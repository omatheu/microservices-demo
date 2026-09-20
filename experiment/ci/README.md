# CI convencional local — gates pré-staging

Este diretório implementa a parte local e sem custo cloud da condição de
controle descrita em
[`../../docs/tcc-ci-cd-baseline.md`](../../docs/tcc-ci-cd-baseline.md).

A matriz versionada seleciona os componentes alterados no caminho de checkout
e aplica o adaptador da linguagem, SAST, scan de dependências, build, SBOM e
scan da imagem correspondente. Caminhos críticos desconhecidos e contratos
protobuf incompatíveis ou dessincronizados bloqueiam de forma fechada.

Execute:

```bash
CANDIDATE_ID=engineering-current MODE=engineering \
  ./experiment/scripts/run-conventional-ci-local.sh
```

Por padrão, o modo de engenharia usa o diff do worktree. Ele também aceita
`CANDIDATE_CHANGED_FILES_FILE` para testar a mecânica com uma fixture explícita.
O modo confirmatório proíbe essa opção e exige `CANDIDATE_BASE_REF`, árvore
limpa e seleção derivada do intervalo Git real.

O runner executa todos os gates mesmo depois de uma falha, produzindo diagnóstico
completo em `experiment/evidence/ci-cd/ci-*/`. A saída canônica é
`ci-local-decision.json`. Uma decisão local `pass` significa apenas que a
candidata está elegível para staging; não é uma aprovação de deployment.
O campo `confirmatory_eligible` permanece falso em modo de engenharia.

Em pull requests, esse runner é chamado automaticamente por
[`../../.github/workflows/tcc-pr-ci.yaml`](../../.github/workflows/tcc-pr-ci.yaml).
O workflow não recebe identidade cloud. Uma falha mantém o check do PR vermelho
e, quando há uma definição experimental pública, preserva também a decisão
convencional selada para adjudicação posterior; isso é um resultado válido do
experimento, embora corretamente impeça o release.

## Modos

- `engineering`: permite árvore Git suja e política ainda em rascunho, mas não
  converte falhas de testes/scanners em sucesso;
- `confirmatory`: exige commit limpo, identificador opaco e política congelada.

No modo confirmatório, a CI também exige `PUBLISH_ARTIFACTS=true` e
`ARTIFACT_REGISTRY_PREFIX=REGION-docker.pkg.dev/PROJECT/REPOSITORY`. A imagem é
publicada somente depois de build, SBOM e scan aprovados; a evidência registra
a referência imutável `imagem@sha256:...`. Em engenharia a publicação permanece
desabilitada por padrão e nenhuma escrita cloud ocorre.

O ruleset Semgrep está versionado localmente e seu SHA-256 é verificado pelo
gate. O modo confirmatório permanece bloqueado enquanto `policy.json` estiver
com status `pre-registration-candidate`; a política completa só será congelada depois
de protocolo, corpus, limiares e retenção do artefato serem definidos.

## Gates atuais

- identidade da candidata e prontidão da política;
- ShellCheck, sintaxe Python, testes do contrato da esteira e JSON;
- compilação do protobuf canônico com `protoc` versionado, compatibilidade
  estrita com a base Git, equivalência semântica dos espelhos e sincronização
  dos descriptors/métodos gRPC gerados em Go e Python;
- Terraform estático e renderização Kustomize;
- política Kubernetes sobre todos os manifests renderizados e autoteste
  adversarial que precisa detectar um container privilegiado; a política
  também bloqueia escalada de privilégio, `hostPath`, `hostPort`, capacidades
  não removidas e `LoadBalancer`/`NodePort` em `staging`, `pdt` e `oracle`;
- `go test ./...` do `checkoutservice` em Go versionado;
- contratos semânticos de valor cobrado e efeitos após falhas de pagamento,
  entrega e e-mail;
- seleção determinística de componentes e testes Go adicionais para
  `shippingservice`, `productcatalogservice` e `frontend` quando afetados;
- testes Node para validação de cartão no `paymentservice` e de
  conversão/arredondamento no `currencyservice` quando afetados;
- testes gRPC existentes do `cartservice` em SDK .NET fixado por digest;
- contratos do `emailservice` executados dentro de sua própria imagem;
- autoteste e scan de segredos com Gitleaks;
- SAST com Semgrep, ruleset versionado por hash e autoteste adversarial;
- dependências/misconfiguração de cada serviço afetado com Trivy;
- build sequencial das imagens afetadas;
- SBOM CycloneDX com Syft e scan de cada imagem com Trivy;
- correspondência exata entre gates obrigatórios da política e gates executados.

As imagens das ferramentas e a versão de PyYAML são fixadas em `policy.json`. O runner
jamais aplica Terraform nem acessa o cluster. Por padrão ele também não envia
imagens. Para limitar o disco local, cada imagem candidata é removida após SBOM
e scan; quando a publicação é explicitamente ativada, ela ocorre antes dessa
remoção e o digest remoto é preservado na decisão.

Depois de uma execução local, o controle convencional é consolidado com a
decisão de staging por:

```bash
./experiment/scripts/compose-conventional-decision.py \
  --candidate-definition <candidate-definition.json> \
  --local-ci-decision <ci-local-decision.json> \
  --staging-decision <staging-decision.json> \
  --output conventional-decision.json
```

O agregador verifica a identidade da candidata, o hash da decisão local e a
igualdade dos digests executados no staging antes de produzir `approve` ou
`block`. A definição da candidata também é selada mesmo quando a CI local
bloqueia antes de existir imagem. Ele não consulta o PDT.
