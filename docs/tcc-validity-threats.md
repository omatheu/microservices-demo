# Registro de ameaças à validade do experimento PDT

> **Status:** registro pré-coleta; versão inicial em 21 de setembro de 2026.
>
> Este documento deve ser revisado antes do congelamento do protocolo e outra
> vez depois da coleta. A revisão posterior pode registrar impacto observado,
> mas não pode apagar ameaças, mudar exclusões ou redefinir o desfecho com base
> em resultados favoráveis.

## Finalidade e fronteira da inferência

O experimento estima se adicionar um Partial Digital Twin do
`checkoutservice` a uma CI/CD convencional completa com staging reduz
aprovações inseguras entre as mesmas candidatas, sem produzir bloqueios
desnecessários em nível inaceitável. A unidade experimental é a candidata; as
repetições são medições técnicas da mesma unidade.

A inferência pretendida é deliberadamente limitada:

- sistema: o fork da Online Boutique registrado neste repositório;
- objeto geminado: `checkoutservice` e o contexto necessário ao seu fluxo;
- infraestrutura: GKE Autopilot no projeto experimental documentado;
- decisão: pré-deployment, com atuação semiautônoma no pipeline;
- comparador: CI/CD convencional completa, não apenas um namespace de staging;
- corpus: mutações e controles gerados pelo protocolo congelado;
- resultado observado: oráculo isolado, sem implantação adversarial no ambiente
  operacional público.

Os resultados não demonstrarão automaticamente eficácia em outros sistemas,
provedores, escalas, equipes ou classes de defeito. Generalizações além dessa
fronteira deverão ser apresentadas como hipóteses, não como achados medidos.

## Escala de avaliação

Antes da análise final, cada ameaça receberá:

- **probabilidade:** baixa, média ou alta;
- **impacto:** baixo, médio ou alto sobre o estimando primário;
- **estado:** prevenida, monitorada, materializada ou indeterminada;
- **direção provável:** favorece controle, favorece PDT, atenua diferença ou
  direção incerta;
- **evidência:** artefato verificável que sustenta a classificação.

Probabilidade e impacto finais serão preenchidos sem alterar as regras abaixo.
Uma ameaça materializada não autoriza remover uma candidata porque seu resultado
é inconveniente.

## Validade de construto

| ID | Ameaça e possível distorção | Controle pré-definido | Evidência exigida | Risco residual |
| --- | --- | --- | --- | --- |
| `C-01` | Chamar de PDT um staging adaptativo favoreceria artificialmente a contribuição conceitual. | Exigir vínculo operacional, sincronização, modelo executável, alternativas, previsão, prescrição e avaliação de fidelidade. | Snapshot, alternativas, decisão PDT, observação do oráculo e relatório de fidelidade. | O modelo continua parcial e não representa toda a Online Boutique. |
| `C-02` | Comparar PDT com um staging fraco confundiria “mais testes” com valor do twin. | Preservar todos os 22 gates convencionais, contratos, segurança, imagem, staging e SLOs no tratamento. | Decisão convencional selada antes do PDT e identidade de artefatos por digest. | A maturidade escolhida para a esteira não cobre todas as práticas industriais possíveis. |
| `C-03` | Medir somente latência ignoraria danos funcionais, cobrança e disponibilidade. | Separar segurança funcional, não funcional, ação prescritiva, tempo e custo. | Matriz do oráculo, perfis de carga, efeitos observados e dataset consolidado. | Algumas propriedades de negócio reais não existem na aplicação demonstrativa. |
| `C-04` | Tratar a intenção da mutação como ground truth superestimaria a validade do oráculo. | Classificar por asserções e execução; usar `intended_label` somente depois da observação. | Observação composta, adjudicação e divergência intenção–efeito. | O próprio oráculo pode conter defeitos ou cobertura incompleta. |
| `C-05` | Confundir crédito promocional, custo líquido e consumo bruto ocultaria o custo incremental. | Registrar custo bruto, créditos separadamente, capacidade-tempo e duração por bloco. | Exportação do Billing, consulta versionada e medição dos recursos. | Atribuição monetária pode atrasar e custos compartilhados podem exigir rateio. |
| `C-06` | Contar `reconfigure` como sucesso sem validar a alternativa favoreceria o PDT. | Avaliar separadamente segurança de `deploy-as-is` e qualidade/custo da alternativa prescrita. | Observação de cada alternativa permitida e política de menor custo válido. | O espaço contrafactual é limitado às configurações predefinidas. |

## Validade interna

| ID | Ameaça e possível distorção | Controle pré-definido | Evidência exigida | Risco residual |
| --- | --- | --- | --- | --- |
| `I-01` | Escolher falhas depois de observar o PDT favoreceria o tratamento. | Congelar operadores, parâmetros, proporções, sementes e corpus antes da coleta. | Auditoria de congelamento e compromisso criptográfico do manifesto privado. | O desenho dos operadores ocorreu com conhecimento da arquitetura do PDT. |
| `I-02` | Vazamento de operador, parâmetros ou rótulo permitiria decisões direcionadas. | IDs opacos, manifesto privado `0600`, recibo público redigido e liberação somente após decisões seladas. | Validação do corpus, hashes, permissões e teste de chaves proibidas. | O pesquisador único conhece o desenho geral e o cegamento humano é parcial. |
| `I-03` | Testes exclusivos do PDT confundiriam contexto operacional com cobertura adicional. | Entregar as mesmas invariantes e SLOs aos dois mecanismos; reservar ao PDT apenas snapshot, modelo e contrafactuais. | Manifests de política selados e logs dos gates executados. | Diferentes formas de operacionalizar a mesma regra podem ter sensibilidades distintas. |
| `I-04` | Substituir commit, imagem ou candidata entre condições destruiria o pareamento. | Vincular commit, árvore, patch, definição e digests imutáveis em todas as decisões. | Hashes e digests conferidos pelo compositor e pelo oráculo. | Dependências externas reconstruídas em outro momento podem variar se não estiverem fixadas. |
| `I-05` | Mudança do estado operacional entre snapshot e previsão introduziria confusão temporal. | Registrar UID, geração, versão de recurso, instante do snapshot e tempo até decisão. | Snapshot e telemetria da janela; rejeição por identidade divergente. | Carga e condições do cluster podem mudar depois da captura. |
| `I-06` | Execução concorrente ou resíduo da candidata anterior contaminaria a seguinte. | Serializar globalmente, limpar namespaces e verificar ausência de pods antes de cada condição. | Logs de cleanup, inventários inicial/final e política de não concorrência. | Estado externo ao namespace e caches de nó podem persistir. |
| `I-07` | Ordem fixa produziria aprendizado, aquecimento ou tendência temporal. | Randomizar por semente privada e executar em blocos, sem alterar a ordem após revelar resultados. | Ordem do manifesto privado e timestamps das execuções. | Blocos longos ainda podem coincidir com mudanças da plataforma. |
| `I-08` | Ruído do Autopilot, agendamento ou rede poderia ser confundido com efeito da candidata. | Repetições, aquecimento separado, perfis fixos e registro de eventos/recursos. | Distribuições por repetição, eventos Kubernetes e métricas de capacidade. | Três repetições capturam apenas parte da variabilidade de cauda. |
| `I-09` | Instrumentação diferente entre condições favoreceria uma delas. | Consultas canônicas, mesmos identificadores e schemas de evidência. | Manifesto de métricas, exportações e validador de evidências. | O PDT possui métricas internas que não existem no controle e devem ser analisadas separadamente. |
| `I-10` | Ajustar limiares ou modelo usando o corpus confirmatório causaria overfitting. | Separar pilotos/calibração; qualquer ajuste cria nova versão e novo corpus. | Status do protocolo, hashes de política e registro cronológico. | O pequeno conjunto de calibração pode não representar o corpus futuro. |
| `I-11` | Exclusões dependentes do resultado poderiam fabricar ganho. | Aplicar regras de falha, repetição e dados ausentes antes de abrir rótulos. | Log de exclusões com motivo técnico, instante e estado de cegamento. | Algumas falhas de infraestrutura podem ser difíceis de distinguir de falhas da candidata. |
| `I-12` | O oráculo compartilhar código com o PDT faria erros correlacionados parecerem acertos. | Harness, política e avaliação independentes; nenhum consumo da decisão PDT na classificação. | Manifesto da suíte do oráculo e hashes de implementação. | Ambos ainda exercitam a mesma aplicação e alguns contratos canônicos. |
| `I-13` | Código adversarial poderia adulterar a esteira, o coletor ou o oráculo. | Candidatas restritas a operadores seguros, CI sem credencial cloud, identidade curta, políticas Kubernetes e imagens por digest. | Seletor de componentes, scans, RBAC e manifests renderizados. | O experimento não pretende representar malware com exfiltração ou escalada real. |
| `I-14` | Aprovação humana informal não provaria atuação semiautônoma. | Ambiente protegido, revisor registrado pela API, recibo ligado por hash e execução fail-closed. | Histórico do GitHub, recibo, ação e validação do runner. | Um único revisor não mede concordância entre operadores humanos. |
| `I-15` | Revelar o manifesto privado antes do gate contaminaria a decisão. | Exigir decisão convencional, PDT, gate e, para ação deployável, aprovação protegida antes do unlock. | Recibo de unlock e hashes da cadeia. | A máquina local do pesquisador continua sendo uma fronteira confiável. |

## Validade de conclusão estatística

| ID | Ameaça e possível distorção | Controle pré-definido | Evidência exigida | Risco residual |
| --- | --- | --- | --- | --- |
| `S-01` | Tratar repetições como amostras independentes causaria pseudorreplicação e intervalos estreitos. | Agregar repetições por candidata; usar candidata como unidade estatística. | Dataset com uma linha analítica por candidata. | Dezoito candidatas oferecem precisão limitada. |
| `S-02` | Corpus pequeno reduz poder para detectar diferenças e estimar subgrupos. | Priorizar efeito pareado, intervalos exatos e descrição transparente, sem depender apenas de significância. | McNemar exato, diferença pareada de risco e intervalos binomiais. | Resultados nulos podem permanecer inconclusivos. |
| `S-03` | Muitas métricas aumentam risco de achados oportunistas. | Fixar um desfecho primário; classificar demais métricas como secundárias ou exploratórias. | Protocolo congelado e relatório com hierarquia explícita. | Análises por estrato terão caráter principalmente descritivo. |
| `S-04` | Limiar calibrado com a própria avaliação inflaria desempenho. | Congelar SLOs com pilotos excluídos da análise confirmatória. | IDs de pilotos, arquivo de limiares e auditoria temporal. | Pilotos curtos podem produzir limiares pouco estáveis. |
| `S-05` | Pares ausentes quebrariam a comparabilidade. | Registrar motivo, nunca imputar decisão favorável e apresentar conjunto completo e conjunto pareado válido. | Relatório de completude por candidata e mecanismo. | Exclusão técnica pode reduzir ainda mais o poder. |
| `S-06` | Agregação ocultaria efeitos opostos entre classes. | Reportar total e estratos predefinidos: funcional, não funcional, infraestrutura/dependência e dependência de contexto. | Registro de mutações e tabela estratificada. | Poucas candidatas por estrato impedem inferência forte. |
| `S-07` | Medidas contínuas de latência e erro têm caudas e assimetria. | Reportar mediana, dispersão, quantis e intervalos adequados, além de média quando útil. | Amostras brutas e resumo reproduzível. | p99 com janelas pequenas permanece instável. |

## Validade externa

| ID | Ameaça e possível distorção | Controle e forma de relato | Risco residual |
| --- | --- | --- | --- |
| `E-01` | Um único microserviço pode não representar sistemas maiores ou monólitos. | Descrever arquitetura, fronteira do twin e dependências; não extrapolar causalmente. | Generalização depende de replicações em outros sistemas. |
| `E-02` | Online Boutique é demonstrativa, não uma operação comercial real. | Preservar regras funcionais observáveis e explicitar ausência de usuários, receita e dados reais. | Incentivos e falhas organizacionais reais não são reproduzidos. |
| `E-03` | Mutações sintéticas podem ser mais regulares que defeitos reais. | Misturar controles, falhas funcionais, não funcionais, dependências e contexto; publicar operadores. | O corpus não reproduz a distribuição de defeitos de uma empresa específica. |
| `E-04` | GKE Autopilot/GCP limita portabilidade para outros runtimes. | Separar lógica do PDT dos manifests e registrar versões/plataforma. | Custos, escalonamento e ruído diferem em outros provedores. |
| `E-05` | Carga, duração e escala reduzidas podem omitir degradações lentas. | Incluir perfis e operadores dependentes de duração dentro do teto financeiro; declarar janelas. | Vazamentos longos, sazonalidade e picos reais permanecem fora do estudo. |
| `E-06` | Um único pesquisador não representa equipes e processos de revisão reais. | Automatizar decisões, registrar intervenção humana e limitar alegações sobre usabilidade organizacional. | Não haverá medida de concordância, fadiga ou tempo entre múltiplos revisores. |
| `E-07` | Créditos e cota gratuita alteram a decisão econômica. | Reportar consumo bruto e capacidade-tempo, não apenas valor líquido pago. | Preços e descontos variam por região, data e organização. |

## Regras para falhas, repetições e exclusões

Estas regras devem permanecer coerentes com o protocolo congelado:

1. falha de ferramenta, credencial, quota ou cluster é falha de infraestrutura,
   não evidência de segurança ou dano da candidata;
2. falha esperada de readiness, dependência ou desempenho causada pela candidata
   é resultado, não falha de infraestrutura;
3. uma repetição inválida pode ser repetida somente pela regra predefinida, com
   ambos os registros preservados;
4. uma candidata não pode ser removida porque controle e PDT concordaram,
   discordaram ou produziram resultado desfavorável à hipótese;
5. exclusões devem ser decididas antes de abrir `intended_label` e parâmetros;
6. pares incompletos permanecem na tabela de fluxo e são excluídos apenas da
   estatística que exige o par;
7. qualquer alteração de política, modelo, teste ou limiar depois do unblinding
   cria uma nova versão experimental e um novo corpus.

## Evidência de auditoria

| Afirmação | Artefato autoritativo |
| --- | --- |
| Protocolo existia antes da coleta | `experiment/protocol/protocol-v1.json` e auditoria de freeze |
| Corpus não vazou rótulos | corpus público, compromisso do oráculo e manifesto privado |
| Mesma candidata e artefato | commit, árvore, patch, definição e digests nas decisões |
| Controle foi selado antes do PDT | `conventional-decision.json` e seus hashes |
| Gate humano foi real | histórico de aprovação, recibo e validação fail-closed |
| Condições não concorreram | timestamps, locks/concurrency e inventários de namespace |
| Ground truth foi independente | suíte do oráculo, observações e adjudicação |
| Repetição não virou amostra | dataset consolidado no nível da candidata |
| Custo incremental foi contabilizado | Billing Export, capacidade-tempo e duração |
| Exclusões não foram oportunistas | log de completude e motivos anterior ao unblinding |

## Revisão pós-coleta obrigatória

Depois da coleta, uma seção final deverá registrar, sem reescrever este plano:

- ameaças que efetivamente se materializaram;
- candidatas ou repetições afetadas;
- direção provável do viés;
- análises de sensibilidade executadas;
- limitações que impedem determinada interpretação;
- ameaças novas descobertas durante a execução;
- quais conclusões permanecem sustentadas apesar do risco residual.

O experimento não será declarado completo enquanto essa revisão residual não
estiver ligada ao relatório de resultados e ao pacote reproduzível de
evidências.
