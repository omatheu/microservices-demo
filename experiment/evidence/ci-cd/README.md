# Evidências da CI/CD convencional

Cada execução local cria um diretório ignorado pelo Git com metadados, logs,
relatórios dos scanners, SBOM, resultados por gate e uma decisão pré-staging.

O conteúdo gerado só constitui evidência confirmatória quando o protocolo e a
política estiverem congelados e a execução usar `MODE=confirmatory`.

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
