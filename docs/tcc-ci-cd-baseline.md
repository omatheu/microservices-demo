# Especificação da esteira convencional de referência

> **Status:** comparador de engenharia executável, com 22 gates locais,
> artefato publicado por digest, staging pareado, decisão convencional selada e
> gate PDT. Congelamento do protocolo, corpus opaco e orquestração confirmatória
> continuam pendentes.

## Papel no experimento

A condição de controle será uma CI/CD convencional completa com staging. A
condição de tratamento preservará integralmente essa esteira e acrescentará o
gate `checkout-pdt-controller` depois da decisão convencional.

Portanto, a comparação **não** será “staging versus PDT”. Um namespace de
staging sem build, testes, segurança, contratos, políticas e decisão de release
seria um controle artificialmente fraco e não responderia à questão de
pesquisa.

```text
candidata
  └─ CI de fonte e segurança
       └─ build e validação do artefato
            └─ manifests/IaC/políticas
                 └─ integração e contratos
                      └─ staging + E2E + carga fixa
                           ├─ decisão convencional selada
                           └─ gate PDT (somente tratamento)
                                └─ confirmação humana
```

## Regras de equivalência entre as condições

- a mesma árvore de origem, configuração candidata e imagens por digest
  atravessam as duas condições;
- todos os gates convencionais são executados uma vez e suas evidências
  seladas antes da consulta ao PDT;
- requisitos funcionais e SLOs públicos são comuns às duas condições;
- staging usa uma carga fixa congelada e não recebe o snapshot operacional;
- o diferencial autorizado ao PDT é o snapshot permitido, a representação do
  `checkoutservice`, a exploração de alternativas e a ação prescritiva;
- uma candidata bloqueada pela esteira convencional permanece bloqueada no
  tratamento, sem atribuir ao PDT uma detecção que já ocorreu;
- uma candidata aprovada pelo controle só conta como detecção incremental se o
  PDT a bloquear ou reconfigurar e o oráculo confirmar que `deploy-as-is` era
  prejudicial;
- nenhum teste é removido do controle para criar uma vantagem ao PDT.

O resultado de cada candidata registra o primeiro gate que a detectou. Assim,
um cenário de CPU, timeout ou regra de negócio que falhe no staging é evidência
da eficácia da CI/CD convencional, não um fracasso do desenho experimental.

## O que já existe no repositório upstream

- workflows de testes unitários para alguns serviços;
- build de imagens com Skaffold;
- deployment efêmero em GKE;
- espera de readiness dos deployments;
- smoke test baseado no load generator;
- validações separadas de Kustomize, Helm e Terraform;
- limpeza de namespaces de pull requests.

## Lacunas para o comparador do TCC

- o workflow principal não executa `go test ./...` no `checkoutservice`;
- não existe uma decisão única que consolide todos os gates;
- o upstream não traz cobertura explícita de cobrança, ordem de efeitos e
  caminhos de erro; a esteira experimental agora cobre o núcleo desse contrato
  com doubles gRPC em memória;
- testes de contrato são predominantemente estruturais ou inexistentes;
- o smoke test verifica erros agregados, mas não prova semântica de pagamento;
- não há gate consolidado de segredos, SAST e dependências;
- não há inventário/scan/proveniência congelados para a imagem candidata;
- políticas Kubernetes e IaC não estão unificadas com o pipeline experimental;
- staging não registra de forma canônica p95/p99, recursos e decisão por SLO;
- os workflows upstream usam projeto/identidades GCP que não pertencem a este
  experimento e não podem ser reutilizados diretamente.

## Gates obrigatórios

### 1. Identidade da candidata

- SHA do commit e árvore de origem;
- identificador opaco da candidata;
- arquivos e componentes alterados;
- digest das imagens e manifests renderizados.

### 2. Qualidade e unidade

- formatadores e linters por linguagem;
- compilação de todos os componentes alterados;
- testes unitários, incluindo `go test ./...` no `checkoutservice`;
- relatório de resultados e cobertura, sem criar um limiar retrospectivo.

### 3. Segurança de fonte e dependências

- detecção de segredos;
- SAST;
- dependências conhecidamente vulneráveis;
- licenças/política de dependências quando aplicável.

### 4. Artefato

- build reproduzível da imagem;
- digest imutável;
- inventário de componentes (SBOM);
- scan da imagem;
- registro de builder, ferramenta e versão.

### 5. Configuração, Kubernetes e IaC

- `terraform fmt` e `terraform validate` sem aplicar;
- renderização de Kustomize;
- validação de schema;
- políticas para recursos, probes, privilégios, imagens e exposição pública;
- autoteste adversarial da política Kubernetes, incluindo bloqueio de
  `privileged: true`, escalada de privilégio, `hostPath`, capacidades não
  removidas e serviços públicos nos namespaces experimentais;
- verificação das quotas financeiras/operacionais do experimento.

### 6. Integração e contratos

- compatibilidade gRPC/protobuf;
- contratos semânticos mínimos do caminho checkout/pagamento;
- respostas de erro e indisponibilidade de dependências;
- correlação entre pedido, valor cobrado, envio e confirmação.

### 7. Staging efêmero

- deploy sem LoadBalancer adicional;
- readiness e estabilidade;
- smoke test;
- E2E de checkout feliz e caminhos negativos predefinidos;
- carga fixa independente do snapshot operacional;
- SLOs funcionais e não funcionais congelados;
- cleanup obrigatório mesmo em falha.

### 8. Decisão convencional

A esteira produz um único documento auditável:

```json
{
  "candidate_id": "opaque-id",
  "commit": "sha",
  "artifact_digests": {},
  "gates": [],
  "decision": "approve|block",
  "reasons": [],
  "started_at": "...",
  "finished_at": "..."
}
```

Essa decisão deve ser persistida antes de o PDT produzir ou revelar sua saída.

### 9. Tratamento PDT e gate humano

Quando a decisão convencional for `approve`, a condição de tratamento executa
o PDT. `approve` permite seguir para confirmação humana; `block` interrompe;
`reconfigure` apresenta a alternativa e sua evidência para confirmação. Nenhuma
candidata adversarial é aplicada à instância operacional pública.

## Execução e custo

Os jobs que não exigem cluster devem executar fora do GKE. Staging, PDT e
oráculo serão efêmeros, sequenciais e sem LoadBalancer. Imagens e evidências
terão política de retenção definida. Antes de conectar GitHub Actions ao projeto
GCP serão estimados Artifact Registry, build, armazenamento e tempo Autopilot.

## Implementação atual

O runner em [`../experiment/ci/`](../experiment/ci/) executa localmente 22
gates obrigatórios, seleciona os serviços afetados, executa adaptadores Go,
Node, .NET ou Python, gera suas imagens, SBOMs e relatórios de segurança, e
emite `ci-local-decision.json`. Ele não acessa o cluster nem aplica Terraform.
A publicação é desligada por padrão e, quando explicitamente ativada, envia
somente os artefatos aprovados e registra a referência `imagem@sha256`. A
execução de engenharia verificada está
registrada em
[`../experiment/evidence/ci-cd/README.md`](../experiment/evidence/ci-cd/README.md).

O script `compose-conventional-decision.py` combina a decisão local com a de
staging somente quando ambas se referem à mesma candidata. A saída preserva os
hashes das entradas e declara explicitamente que o PDT não foi consultado. Essa
decisão é a entrada de controle usada pelo gate experimental.

O piloto `engineering-artifact-binding-v2` percorreu CI local, publicação,
staging e PDT usando o mesmo digest do `checkoutservice`. Isso valida o
encadeamento técnico, mas não é resultado da comparação principal.

O runner agora exige dois contratos candidato-independentes contra
`cartservice` e `checkoutservice` reais no staging. Eles verificam o caminho
feliz e a preservação do carrinho após rejeição de pagamento, exercitando as
dependências reais de catálogo, câmbio, entrega e pagamento sem consumir o
snapshot operacional. A implementação está pronta, mas o item permanece
pendente até uma execução cloud autorizada produzir a evidência.

Antes de uma coleta confirmatória ainda será obrigatório: congelar política e
limiares, usar árvore Git limpa e identificadores opacos, validar o probe de
serviços reais numa execução autorizada, fixar corpus/sementes/repetições e
executar toda a orquestração em modo confirmatório.

Uma execução confirmatória só poderá ser chamada de “esteira completa” quando
os nove grupos de gates forem orquestrados para a mesma candidata opaca, a
decisão convencional estiver selada e o gate humano estiver presente. Os
pilotos locais e de staging existentes validam partes desse fluxo, mas ainda
não satisfazem sozinhos esse critério de saída.
