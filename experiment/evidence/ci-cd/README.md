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
