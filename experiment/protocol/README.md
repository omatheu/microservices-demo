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
o registro de mutações e o manifesto da suíte independente do oráculo. Isso
ainda não significa congelamento: o manifesto do oráculo só poderá ser
congelado depois de registrar e validar os digests imutáveis de suas imagens.

O teto proposto para a coleta é R$200 de custo incremental, com parada para
revisão em R$150 e ao final de cada bloco de três candidatas. Isso ainda não é
uma autorização de gasto: orçamento do GCP gera alertas, não um bloqueio rígido,
e a coleta continuará proibida até existir uma forma de conferir o custo
incremental após cada bloco.

## Dados excluídos da comparação principal

As execuções de `current` e `checkout-cpu-restriction-v1` são pilotos de
engenharia/calibração. Como a hipótese e a falha eram conhecidas durante a
construção dos mecanismos, seus resultados não podem ser usados para estimar a
vantagem comparativa do PDT.
