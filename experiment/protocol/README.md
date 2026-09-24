# Protocolo comparativo CI/CD convencional × CI/CD com PDT

> **Status:** rascunho metodológico; coleta confirmatória bloqueada.
>
> O protocolo só muda para `frozen` depois que tamanho do corpus, orçamento de
> execução, sementes, suítes e análise estatística estiverem definidos sem usar
> resultados do corpus de avaliação.

O desenho executável candidato está em
[`protocol-v1.json`](./protocol-v1.json). Ele fixa provisoriamente 18
candidatas, três repetições técnicas, blocos de três e um plano pareado de
análise. Seu status é `pre-registration-candidate`, e a coleta cloud permanece
explicitamente desautorizada até que os operadores, o oráculo, os SLOs finais e
o teto financeiro sejam validados e seus hashes registrados.

## Objetivo

Medir, com o menor viés viável, a utilidade incremental do
`checkout-pdt-controller` quando adicionado a uma esteira convencional completa
de CI/CD que já inclui staging e testes pré-deployment.

O desfecho primário é a taxa de candidatas prejudiciais aprovadas. Os desfechos
secundários são bloqueios desnecessários, sensibilidade, especificidade,
acurácia balanceada, qualidade da ação recomendada, erro de previsão, tempo e
custo computacional.

## Unidade experimental

A unidade experimental é uma versão candidata opaca capaz de afetar o caminho
de checkout. Ela pode alterar o `checkoutservice`, uma dependência desse fluxo
ou a infraestrutura que condiciona sua execução. O objeto geminado permanece o
`checkoutservice`. Janelas e repetições reduzem o ruído da medição, mas não
contam como candidatas independentes na análise estatística.

## Condições comparadas

### Controle: CI/CD convencional completa

- valida fonte, dependências, artefatos, manifests e IaC;
- executa testes unitários, integração, contrato e segurança;
- implanta a candidata em staging efêmero;
- executa readiness, smoke, E2E, caminhos negativos e carga fixa;
- recebe as invariantes e os SLOs congelados;
- não recebe o snapshot operacional;
- decide `approve` ou `block` para `deploy-as-is`.

### Tratamento: a mesma CI/CD acrescida do PDT

- preserva todos os gates e evidências da condição de controle;
- recebe a mesma candidata, invariantes e SLOs;
- recebe o snapshot permitido da instância operacional;
- atualiza a representação do `checkoutservice` e de seu contexto;
- materializa e avalia alternativas contrafactuais;
- prevê o resultado e decide `approve`, `block` ou `reconfigure`;
- também registra se `deploy-as-is` foi classificada como segura.

Nenhuma regra funcional é exclusiva do PDT. O tratamento experimental é o uso
do estado sincronizado, do modelo e das alternativas na decisão.

Em particular, este protocolo não compara:

- um namespace de staging isolado contra outro namespace chamado PDT;
- observabilidade tradicional contra o controlador do twin;
- uma esteira convencional deliberadamente sem testes contra uma suíte mais
  forte disponível apenas ao PDT;
- cenários escolhidos depois de observar qual mecanismo os detecta.

Ele compara duas **políticas completas de release**. A segunda contém todos os
passos e decisões da primeira e adiciona somente o ciclo específico do PDT.

A decisão convencional é persistida antes de abrir a saída do PDT. Na esteira
real, apenas candidatas aprovadas pelo controle precisam chegar ao gate PDT. O
resultado primário é a capacidade incremental do PDT entre essas candidatas,
sem apagar as detecções obtidas anteriormente pelo CI/CD.

Candidatas bloqueadas pela CI antes da criação da imagem permanecem na amostra.
Como o tratamento contém integralmente a condição de controle, ele herda esse
bloqueio e não executa o PDT. Depois de seladas as decisões, o oráculo verifica
independentemente o commit, a árvore e o patch privados para atribuir o rótulo
observado. Assim, um acerto de compilação ou política é creditado à CI
convencional e não é artificialmente apresentado como vantagem do twin.

## Gates mínimos da condição de controle

1. commit, candidato e artefato identificados de forma imutável;
2. formatação, lint, compilação e testes unitários relevantes;
3. segredos, SAST e análise de dependências;
4. build de imagem, inventário e varredura de vulnerabilidades;
5. renderização e políticas para Kubernetes/Terraform;
6. integração e contratos do caminho de checkout;
7. staging efêmero com readiness e smoke test;
8. E2E funcional, caminhos de erro e teste não funcional fixo;
9. decisão registrada e gate humano antes do ambiente operacional.

As ferramentas, versões, políticas e critérios exatos serão congelados antes
da coleta. Uma candidata não será escolhida ou descartada porque produziu o
resultado comparativo desejado.

O catálogo inicial de cenários está em
[`../../docs/tcc-candidate-scenarios.md`](../../docs/tcc-candidate-scenarios.md).

## Corpus

O corpus deve ser gerado depois do congelamento dos operadores, sementes e
proporções, e deve conter:

1. candidatas seguras de controle;
2. mutações funcionais no checkout/pagamento;
3. mutações não funcionais de latência, disponibilidade ou recursos;
4. mudanças de dependências e infraestrutura observáveis no checkout;
5. casos independentes do contexto e casos dependentes do estado/carga.

Operadores possíveis incluem alteração de valor cobrado, omissão controlada de
uma etapa, propagação incorreta de falha, atraso condicionado, consumo adicional
limitado de CPU ou memória e erro intermitente. Eles não podem executar
exfiltração, persistência, acesso a credenciais, expansão de privilégio ou
tráfego contra alvos externos.

Cada candidata recebe um identificador aleatório. O manifesto que relaciona o
identificador ao operador e ao efeito esperado fica separado dos inputs dos
dois mecanismos. Em um trabalho conduzido por um único pesquisador, o cegamento
humano pode ser parcial; o cegamento dos mecanismos e da análise automatizada é
obrigatório e essa limitação deve ser declarada.

Na materialização confirmatória, toda alteração é gravada em um commit
determinístico dentro do worktree descartável. A ordem privada registra commit,
árvore, base e SHA-256 do patch binário. A CI precisa avaliar exatamente esse
commit limpo, e o oráculo rejeita qualquer substituição posterior da fonte ou
do patch.

## Oráculo de validação

Após staging e PDT persistirem suas decisões, o oráculo executa a candidata em
namespace efêmero, sem endpoint público, usando uma matriz mais ampla de testes
e perfis de carga. Ele combina:

- manifesto da mutação;
- asserções determinísticas do contrato;
- observação funcional e não funcional;
- regra de adjudicação congelada para resultados inconclusivos.

O oráculo rotula `deploy-as-is` e cada alternativa permitida. Ele não fornece
dados para o staging nem para o PDT antes do fechamento das decisões.

O registro pré-coleta de ameaças à validade e as regras que impedem exclusões
pós-hoc estão em
[`../../docs/tcc-validity-threats.md`](../../docs/tcc-validity-threats.md).

## Ordem e isolamento

- a mesma candidata passa pela esteira convencional e, quando elegível, pelo
  gate PDT;
- a ordem das candidatas é randomizada ou contrabalanceada;
- as condições nunca executam simultaneamente;
- cada namespace é limpo antes da condição seguinte;
- imagem, dependências, perfil de cluster e versão das ferramentas são
  registrados;
- duração e capacidade-tempo respeitam limites congelados;
- falhas de infraestrutura seguem uma regra de repetição/exclusão prévia.

## Vedação das decisões

Antes do oráculo, cada condição deve salvar sua decisão, evidências e hashes em
diretório timestampado. O manifesto reservado só pode ser associado a esses
resultados depois que ambas as decisões estiverem completas. Ajustar um limiar
ou o modelo após abrir o rótulo invalida a candidata para a análise
confirmatória e exige novo corpus para a versão ajustada.

## Plano de análise

- construir matriz de confusão para a esteira convencional e para a esteira
  acrescida do PDT;
- medir a fração de escapes prejudiciais do controle detectada pelo PDT;
- medir a fração de candidatas seguras aprovadas pelo controle que o PDT
  bloqueia desnecessariamente;
- registrar o primeiro gate que detectou cada candidata;
- comparar pares discordantes, pois as candidatas são compartilhadas;
- calcular intervalos de confiança no nível da candidata;
- agregar repetições antes da análise para evitar pseudorreplicação;
- apresentar resultado por classe funcional, não funcional e dependência de
  estado;
- apresentar custo e tempo junto à melhora de detecção;
- avaliar separadamente a classificação de `deploy-as-is` e a utilidade da
  reconfiguração prescrita pelo PDT.

O teste estatístico, o tamanho do corpus e a regra de parada serão incluídos
antes da mudança de status para `frozen`. Eles devem ser escolhidos por poder,
variabilidade dos pilotos, tempo e custo, não pelo resultado desejado.

## Geração cega e compromisso do oráculo

O utilitário [`../scripts/manage-blinded-corpus.py`](../scripts/manage-blinded-corpus.py)
usa uma chave privada de no mínimo 32 bytes para derivar IDs, parâmetros e
ordem por HMAC-SHA256. A parte pública não contém operador, estrato, componente,
parâmetros ou rótulo; ela expõe somente um compromisso SHA-256 do manifesto do
oráculo. Alterações no manifesto, na chave ou no protocolo invalidam a
verificação.

O comando falha fechado quando o protocolo ainda não está `frozen`. A opção
`--allow-draft` gera apenas uma prévia marcada como inelegível, documentada em
[`preview/`](./preview/). A chave e o manifesto reservado nunca são versionados.

Os `frozen_inputs` do protocolo já vinculam as políticas de CI, staging e PDT,
a implementação do `checkout-pdt-controller`, o registro de mutações e o
manifesto da suíte independente do oráculo. Isso
ainda não significa congelamento: o manifesto do oráculo só poderá ser
congelado depois de registrar e validar os digests imutáveis de suas imagens,
e o runtime PDT exige o digest imutável de sua própria imagem.

Antes da publicação, o job `Validate experiment runtime images` do workflow de
pull request constrói localmente `checkout-pdt-controller`, `oracle-harness` e
`currency-reference`, gera SBOMs, bloqueia vulnerabilidades HIGH/CRITICAL
corrigíveis e registra o tamanho. Esse job não possui identidade GCP e define
explicitamente `published_to_registry: false`.

Quando uma publicação cloud for autorizada, o job protegido produzirá um
`summary.json` com os três digests remotos e os SHA-256 dos relatórios brutos.
O utilitário
[`../scripts/bind-runtime-publication.py`](../scripts/bind-runtime-publication.py)
confere repositório, commit, árvore, pull request, ambiente protegido, revisão
financeira, o prefixo exato do Artifact Registry e cada SBOM/scan por conteúdo
e hash antes de gerar propostas para os manifests PDT e oráculo. O relatório
Trivy deve descrever o mesmo tag e image ID publicados e não pode conter
achados bloqueantes. As duas propostas recebem a mesma proveniência
hash-bound. O binder não publica imagens, não modifica o GCP e não marca nenhum
artefato como `frozen`.

Uma integração local executa o publisher e o binder reais com somente Docker e
`gcloud` substituídos por dublês sem rede. Ela verifica que o schema produzido
é aceito ponta a ponta, que os hashes dos relatórios chegam ao recibo e que as
travas cloud e financeira falham antes de qualquer saída quando desligadas.

A publicação necessária ao congelamento não precisa disparar staging ou PDT.
O mesmo workflow protegido possui um caminho `runtime-publication` selecionado
por rótulo próprio e mutuamente exclusivo do experimento completo. Esse job usa
uma identidade federada exclusiva, com escrita somente no repositório Artifact
Registry revisado, e não instala kubectl, não obtém credenciais GKE nem chama o
runner comparativo. A trava `ALLOW_RUNTIME_PUBLICATION` não concede
`ALLOW_EXPERIMENTAL_CLOUD_EXECUTION`, e a variável protegida
`TCC_RUNTIME_PUBLICATION_ACKNOWLEDGED` é distinta da chave financeira usada
pelos blocos experimentais.

Antes de qualquer janela de publicação, o auditor fail-closed deve aprovar os
13 controles de instalação, proteção, estado financeiro desarmado e privilégio
mínimo:

```bash
python3 experiment/scripts/audit-runtime-publication-readiness.py \
  --pull-request 1 \
  --require-ready
```

O auditor compara o conteúdo em `main` com o workflow local revisado, exige
revisor e branch exatos, rejeita qualquer rótulo de autorização já anexado ao
PR e falha quando uma leitura IAM necessária está indisponível. Mesmo com 13/13,
o resultado não autoriza publicação; a janela ainda exige aprovação humana e a
ativação deliberada da variável financeira exclusiva.

O arquivo binário candidato a `terraform apply` também precisa passar pelo gate
de escopo antes de qualquer instalação:

```bash
python3 experiment/scripts/validate-runtime-publication-terraform-plan.py \
  --plan /tmp/runtime-publication-controls.tfplan \
  --require-safe
```

Esse gate abre diretamente o plano binário, registra seu SHA-256 e aceita
somente as três criações IAM predeclaradas. Um resultado 9/9 continua com
`apply_authorized: false` e `cost_authorized: false`; autorização e execução são
eventos posteriores e separados.

Em 22/09/2026 UTC, uma autorização posterior levou à aplicação daquele mesmo
plano binário: 3 recursos IAM adicionados, 0 alterados e 0 destruídos. O estado
pós-apply não possui drift, as variáveis financeiras continuam `false`, o PR #1
continuava desarmado e nenhuma imagem havia sido publicada. Na auditoria
pré-merge, 12/13 controles passaram; o único bloqueio naquele momento era o
workflow revisado ainda não estar na `main`.

Após o merge, o workflow está em `main`. O auditor agora explicita duas
dimensões: os 12 controles estruturais estão prontos, enquanto o único controle
da candidata está inativo porque o PR #1 foi encerrado. Um novo PR candidato
aberto e desarmado é necessário para alcançar 13/13; isso não liga variáveis,
não anexa rótulos e não autoriza publicação.

Depois da revisão dos dois manifests propostos, o próximo passo também é
gerado sem tocar na árvore ativa:

```bash
python3 experiment/scripts/prepare-protocol-freeze-candidate.py \
  --repo-root . \
  --bound-pdt-manifest <binding>/pdt-runtime-manifest.bound.json \
  --bound-oracle-manifest <binding>/oracle-suite-manifest.bound.json \
  --frozen-at <timestamp-RFC3339-UTC> \
  --output-directory <freeze-candidate>
```

O comando valida que os manifests diferem dos atuais somente nos campos de
publicação e que ambos vêm da mesma execução protegida. Em seguida produz, como
proposta, as cinco políticas congeladas, os dois manifests congelados e um
protocolo ainda `pre-registration-candidate`, com todos os hashes encadeados.
Nenhum arquivo ativo é alterado, a coleta permanece desabilitada e o recibo
declara `cloud_execution_authorized: false`. O bundle inteiro deve ser aplicado
e revisado como uma única mudança antes das aprovações financeira e do
pesquisador.

Depois que o bundle estiver aplicado, as aprovações reais existirem nos
caminhos canônicos e a auditoria passar nos 17 checks, a proposta final de
congelamento é gerada por:

```bash
python3 experiment/scripts/finalize-protocol-freeze.py \
  --repo-root . \
  --researcher-approval experiment/protocol/approvals/researcher-approval-v1.json \
  --cost-review experiment/protocol/approvals/cost-review-v1.json \
  --frozen-at <timestamp-RFC3339-UTC> \
  --output-directory <freeze-finalization>
```

O finalizador carrega pelo hash o auditor selado no próprio protocolo, exige
os 17 checks aprovados e vincula por SHA-256 tanto a aprovação do pesquisador
quanto a revisão financeira. Ele recusa timestamps anteriores aos componentes
ou às aprovações e produz três artefatos: o protocolo congelado proposto, a
auditoria usada e um recibo criptográfico da finalização. O comando não altera
a árvore ativa nem o GCP; o recibo mantém `cloud_execution_authorized: false`,
portanto a futura execução cloud continua dependendo de autorização explícita
independente.

O teto proposto para a coleta é R$200 de custo incremental, com parada para
revisão em R$150 e ao final de cada bloco de três candidatas. Isso ainda não é
uma autorização de gasto: orçamento do GCP gera alertas, não um bloqueio rígido,
e a coleta continuará proibida até existir uma forma de conferir o custo
incremental após cada bloco.

## Auditoria de prontidão para congelamento

O verificador [`../scripts/audit-protocol-freeze.py`](../scripts/audit-protocol-freeze.py)
materializa os pré-requisitos do congelamento como checks fail-closed. Ele
confere estrutura e hashes do protocolo, operadores, estados das políticas,
arquivos e imagens imutáveis do oráculo, revisão financeira e aprovação
explícita do pesquisador.

O auditor de congelamento, o auditor da publicação dos runtimes, o validador do
plano Terraform, o preparador do candidato, o finalizador, o cleanup restrito
dos workloads experimentais e o próprio validador agora também fazem parte dos
30 inputs selados do protocolo. Assim, as regras
que decidem a prontidão e materializam a proposta final não podem ser trocadas
silenciosamente depois da aprovação do desenho.

Os dois workflows GitHub também são inputs selados. Qualquer mudança no
gatilho do pull request, nas travas financeiras, na identidade cloud ou na
ordem de publicação invalida o hash do protocolo.
O runner de staging e o probe de contratos com serviços reais também são
selados. O controle só pode aprovar quando os dois casos predefinidos passam;
o probe declara e verifica que não acessou o snapshot operacional.
O runner pareado, o preparador da ação selecionada e o registrador do gate
humano também são inputs selados. Assim, a fronteira do `checkoutservice`, o
rollback efêmero e a separação entre aprovação humana e autorização cloud não
podem ser alterados depois da observação dos resultados.
O runner do oráculo, a política de fidelidade e o calculador pós-decisão ficam
vinculados pelo manifesto da suíte do oráculo. Assim, as alternativas
observáveis, o conjunto de métricas, as fórmulas de erro e a vedação de
recalibração confirmatória não podem ser modificados depois da abertura dos
rótulos. O agregador de fidelidade também é selado e recusa cobertura parcial,
preservando a candidata — e não suas repetições — como unidade estatística.
O compositor do dataset e o analisador confirmatório também são selados. O
primeiro verifica os hashes de cada decisão e adjudicação e exige uma linha de
fluxo para cada candidata declarada. Quando o controle aprova, ele exige ainda
o agregado de fidelidade vinculado por hash, valida política, artefatos,
cobertura alternativa × repetição e controles contra recalibração. Quando o
controle bloqueia, a fidelidade deve ser explicitamente ausente. Uma exclusão
de infraestrutura só é aceita antes da abertura do rótulo, depois da repetição
substituta prevista, com ledger hash-bound dos dois intentos inválidos e sem
evidência de decisão ou oráculo na mesma linha. O segundo rejeita candidatas
silenciosamente ausentes, separa exclusões do manifesto de adjudicações
inconclusivas, não imputa decisões ou rótulos e aplica a unidade de análise no
nível da candidata, intervalos binomiais exatos e McNemar pareado definidos
nesta versão do protocolo. A fidelidade é resumida entre candidatas a partir
dos agregados candidatos; nenhuma repetição técnica entra como unidade
estatística independente.
O dataset declarativo e a consulta de custo limitada a 100 MB também são
selados, impedindo que a regra de contabilização seja alterada depois da
observação dos resultados.
Os agregados da linha de base operacional e funcional, seu auditor fail-closed
e o relatório que vincula cada amostra bruta por SHA-256 também são inputs
selados. Assim, os SLOs finais não podem ser recalibrados contra um baseline
substituído depois da geração do corpus.
O registro de ameaças à validade também é um input selado, para que regras de
exclusão e interpretações de viés não sejam reescritas depois da coleta.

```bash
python3 experiment/scripts/audit-protocol-freeze.py \
  --repo-root . \
  --require-ready
```

Enquanto houver pendências, o comando termina com status diferente de zero e
lista `blocking_requirements`. Os modelos em [`approvals/`](./approvals/) não
são aprovações; arquivos sem o sufixo `.example` só devem ser criados com dados
reais. Tanto a revisão financeira quanto a aprovação do protocolo registram
`cloud_execution_authorized: false`: congelar o desenho nunca autoriza uma
execução paga. A revisão financeira só é aceita quando `evidence` contém caminho
seguro e SHA-256 de uma saída real de `query-billing-cost-window.sh`. O auditor
confere projeto, moeda BRL, janela, timestamp, custo bruto, linhas retornadas e
o teto de 100 MB; um snapshot de prontidão sem custo observado não pode
substituir essa evidência.

## Dados excluídos da comparação principal

As execuções de `current` e `checkout-cpu-restriction-v1` são pilotos de
engenharia/calibração. Como a hipótese e a falha eram conhecidas durante a
construção dos mecanismos, seus resultados não podem ser usados para estimar a
vantagem comparativa do PDT.
