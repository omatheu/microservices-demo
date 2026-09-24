# Gate PDT semiautônomo

O gate definitivo combinará a decisão consolidada de uma CI/CD convencional
completa, que inclui staging, com a decisão PDT da mesma candidata. A
especificação do controle está em
[`../../docs/tcc-ci-cd-baseline.md`](../../docs/tcc-ci-cd-baseline.md).

- CI/CD convencional ou staging diferente de `PASS`: bloqueio automático;
- PDT com `block`: bloqueio automático;
- CI/CD convencional selada com staging `PASS` e PDT `approve` ou
  `reconfigure`: estado
  `awaiting-human-confirmation`;
- para `approve` ou `reconfigure`, o runner prepara uma ação vinculada por hash
  para validação isolada no namespace `oracle`, acompanhada de rollback por
  remoção e verificação do runtime efêmero;
- nenhuma mutação do operacional ocorre antes da confirmação humana e da
  existência de um plano de rollback.

Uso:

```bash
./experiment/scripts/evaluate-deployment-gate.py \
  --conventional-decision <conventional-decision.json> \
  --pdt-decision <pdt-decision.json> \
  --output gate.json
```

Uma decisão isolada de staging não é aceita. O gate exige o resultado selado da
esteira convencional, verifica a presença da CI local e exige que controle e PDT
tenham executado os mesmos artefatos imutáveis.

`prepare-deployment-action.py` valida que a alternativa selecionada pertence ao
`checkoutservice`, coincide exatamente com a recomendação PDT e contém apenas
réplicas ou recursos permitidos. O artefato resultante mantém
`cloud_execution_authorized` e `operational_mutation_authorized` como `false`.
`record-human-gate-decision.py` registra aprovação ou rejeição humana em um novo
arquivo imutável; mesmo uma aprovação vale somente para solicitar a validação
isolada e não substitui a revisão financeira nem as travas cloud.

O piloto `engineering-artifact-binding-v2` percorreu CI local, staging e PDT
com o mesmo digest. Controle e PDT aprovaram `deploy-as-is`, então o gate parou
em `awaiting-human-confirmation`; não houve mutação operacional. O resultado
valida o encadeamento, mas não integra a comparação confirmatória.

## Orquestração pareada

`run-comparative-candidate.sh` encadeia a condição de controle e a de
tratamento sem permitir que o PDT substitua qualquer gate convencional:

1. executa os 22 gates pré-staging, publica os artefatos aprovados e fixa os
   digests;
2. se a CI bloquear, sela o controle e o tratamento herda o bloqueio;
3. se a CI passar, executa staging, sua suíte fixa e sela a decisão
   convencional;
4. somente quando o controle aprovar captura o snapshot operacional e executa
   o PDT com os mesmos artefatos e configuração candidata;
5. produz o gate humano e, quando aplicável, prepara a ação e o rollback para o
   ambiente-oráculo, sempre com `operational_mutation_performed: false`.

Depois da revisão, o recibo humano pode ser produzido sem executar o cluster:

```bash
./experiment/scripts/record-human-gate-decision.py \
  --deployment-gate <gate.json> \
  --deployment-action <deployment-action.json> \
  --decision approve-isolated-validation \
  --actor <identidade-do-pesquisador> \
  --output <human-gate-decision.json>
```

O recibo aprovado ainda registra `cloud_execution_authorized: false`; a
autorização financeira e operacional da janela continua sendo um ato separado.
Para candidatas aprovadas pelo controle, o runner do oráculo recusa iniciar sem
esse recibo, o histórico bruto de aprovação do GitHub e toda a cadeia de
decisões vinculada por hash. A aprovação humana é, portanto, uma precondição
executável da validação isolada e não apenas um registro documental.

O runner falha antes de qualquer escrita cloud sem duas confirmações explícitas:
`ALLOW_EXPERIMENTAL_CLOUD_EXECUTION=true` e
`COST_REVIEW_ACKNOWLEDGED=true`. Também recusa iniciar se `staging` ou `pdt`
contiverem pods ativos. Essas variáveis são travas de processo, não limites
financeiros do GCP; a revisão de custo por bloco continua obrigatória.

Exemplo apenas após congelamento e autorização da coleta:

```bash
MODE=confirmatory \
CANDIDATE_ID=cand-opaque \
CANDIDATE_DEFINITION=experiment/pdt/candidates/cand-opaque.json \
CANDIDATE_BASE_REF=<commit-base-congelado> \
ARTIFACT_REGISTRY_PREFIX=us-central1-docker.pkg.dev/PROJECT/REPOSITORY \
REPETITION=1 \
ALLOW_EXPERIMENTAL_CLOUD_EXECUTION=true \
COST_REVIEW_ACKNOWLEDGED=true \
./experiment/scripts/run-comparative-candidate.sh
```

O item privado do oráculo não é aceito por esse runner. Sua liberação e
execução pertencem à fase posterior, depois de as decisões estarem seladas.

## Gatilho por pull request no GitHub

No GitHub, o equivalente a um merge request é um **pull request**. Os workflows
versionados implementam o encadeamento em três fronteiras de confiança:

1. [`.github/workflows/tcc-pr-ci.yaml`](../../.github/workflows/tcc-pr-ci.yaml)
   roda automaticamente em abertura, atualização, reabertura ou retirada do
   estado de rascunho. Ele executa os 22 gates locais sem `id-token` e sem
   credenciais do GCP, sela bloqueios pré-staging e publica a evidência como
   artefato do GitHub;
2. [`.github/workflows/tcc-pr-experiment.yaml`](../../.github/workflows/tcc-pr-experiment.yaml)
   recebe o evento `workflow_run` somente após sucesso da CI. Ele rejeita fork,
   revisão obsoleta, PR em rascunho e ausência dos rótulos
   `tcc-experiment-cloud` e `tcc-cost-reviewed`. A autenticação cloud só ocorre
   depois da aprovação do ambiente protegido e das validações locais;
3. depois que staging e PDT selam as decisões, um job separado e sem
   `id-token` espera a aprovação do ambiente protegido
   `tcc-deployment-approval`. O job consulta o histórico de aprovações do
   próprio workflow pela API do GitHub, vincula o login real do revisor ao hash
   do gate e da ação preparada e publica um recibo. Esse recibo autoriza apenas
   solicitar a validação isolada no oráculo; ele não autoriza GCP nem mutação do
   ambiente operacional.

Um PR comum nunca executa GKE. Para ser elegível ao estágio experimental, o PR
deve introduzir exatamente um arquivo
`experiment/pdt/candidates/<candidate_id>.json`. O resolvedor valida que o nome
corresponde ao ID, que existe uma única alternativa `deploy-as-is` e que a
definição pública não contém operador, parâmetros ou rótulo esperado.

Os workflows legados do upstream que implantavam ou publicavam artefatos no
projeto `online-boutique-ci` foram removidos desta variante. Assim, não há uma
segunda esteira cloud paralela e não controlada: o `TCC Paired Staging and PDT`
é o único workflow com identidade GCP e permanece sujeito às travas acima.

### Configuração única no repositório GitHub

Depois que os dois workflows estiverem na branch padrão:

1. criar o ambiente `tcc-experiment` e exigir ao menos um revisor;
2. nesse ambiente, cadastrar os secrets `GCP_WORKLOAD_IDENTITY_PROVIDER` e
   `GCP_EXPERIMENT_SERVICE_ACCOUNT` para a execução pareada e
   `GCP_RUNTIME_PUBLISHER_SERVICE_ACCOUNT` para a identidade exclusiva do
   Artifact Registry; ambas são federadas e não possuem chave JSON persistente;
3. cadastrar as variáveis de ambiente `TCC_COST_REVIEW_ACKNOWLEDGED` e
   `TCC_RUNTIME_PUBLICATION_ACKNOWLEDGED` como `false`; a primeira só pode ser
   ligada durante um bloco experimental revisado, e a segunda somente durante
   a janela de publicação dos runtimes; ambas retornam para `false` ao final;
4. criar os rótulos `tcc-experiment-cloud`, `tcc-runtime-publication` e
   `tcc-cost-reviewed`; os dois primeiros são mutuamente exclusivos;
5. tornar o check `TCC Conventional CI / Conventional pre-staging gates`
   obrigatório na proteção da branch `main`;
6. criar o ambiente `tcc-deployment-approval`, exigir revisor e restringi-lo à
   branch `main`. Esse ambiente não recebe secrets nem identidade cloud.

Em execuções de engenharia autorizadas, o job protegido reconstrói as três
imagens experimentais, gera SBOM, bloqueia vulnerabilidades altas ou críticas,
publica e registra o digest retornado pelo Artifact Registry antes de iniciar o
staging. Em modo confirmatório ele não reconstrói runtimes: exige os manifests
PDT e oráculo congelados e verifica que os três digests imutáveis ainda existem.
Assim, o controlador executado em `pdt-system` é exatamente o artefato atestado
na mesma janela autorizada ou o artefato previamente congelado.

Antes do congelamento, o rótulo `tcc-runtime-publication` seleciona um caminho
separado que apenas constrói, escaneia, publica e vincula os três runtimes. Ele
usa uma Service Account com `roles/artifactregistry.writer` somente no
repositório revisado, não instala o plugin GKE, não obtém credenciais do
cluster e não executa staging ou PDT. O workflow rejeita a combinação desse
rótulo com `tcc-experiment-cloud`; autorização de publicação é distinta de
autorização para workloads experimentais. Sua trava financeira exclusiva é
`TCC_RUNTIME_PUBLICATION_ACKNOWLEDGED`; ligar essa variável não habilita o job
pareado.

Aplicar os dois rótulos não substitui a aprovação do ambiente nem a chave
financeira. O job cloud é serializado globalmente e não cancela uma execução em
andamento, para não interromper o cleanup. Ele usa o projeto
`microservices-demo-tcc`, o cluster `online-boutique-experiment` e o Artifact
Registry com retenção curta já provisionado. Nenhum passo faz deploy no
namespace operacional.

Em 21/09/2026, a identidade federada e essas configurações do GitHub foram
aplicadas. O ambiente `tcc-deployment-approval` também foi criado com
`omatheu` como revisor obrigatório, política restrita à branch `main` e sem
secrets. A Service Account não possui chave; a auditoria de RBAC confirmou
mutação somente em `staging`, `pdt` e nos recursos estritamente necessários do
`pdt-system`, com leitura do `operational` e sem acesso de mutação ao `oracle`.
As variáveis `TCC_COST_REVIEW_ACKNOWLEDGED` e
`TCC_RUNTIME_PUBLICATION_ACKNOWLEDGED` permanecem `false`, e nenhum dos três
rótulos cloud foi anexado ao PR #1; portanto essa configuração, por si só, não
iniciou execução cloud. Em 22/09/2026, a identidade de publicação-only, seu
vínculo OIDC e o Writer restrito ao repositório foram aplicados com 3 adições,
0 alterações e 0 destruições. Seu secret, sua variável desligada e seu rótulo
passivo também foram cadastrados. Antes do merge, o auditor passou em 12/13
porque o workflow ainda precisava chegar à branch `main`; o novo gate humano
também continuava pendente de uma execução de engenharia.

O PR #1 foi mesclado em `main` no commit `895473c0` após os três checks
obrigatórios passarem. A auditoria pós-merge confirma 12/12 controles de
infraestrutura prontos; o único controle de candidata está inativo porque não
há mais um PR aberto. Nenhum workflow cloud foi executado, e a próxima candidata
deve começar sem rótulos e com ambas as variáveis financeiras em `false`.
