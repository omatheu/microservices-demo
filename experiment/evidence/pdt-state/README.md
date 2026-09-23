# Evidências de sincronização do PDT

O snapshot `operational-state-20260920T024714Z` estabelece o primeiro vínculo
versionado entre a instância operacional e o ambiente PDT.

Ele registra:

- projeto `microservices-demo-tcc` e cluster `online-boutique-experiment`;
- self-link do cluster e UID do namespace `operational`;
- namespace-alvo `pdt` e relação `observes-and-simulates`;
- estado de 12 deployments, incluindo imagens, réplicas e recursos;
- perfil observado do load generator: 10 usuários e taxa 1;
- quotas, pods, serviços, eventos e manifesto operacional renderizado;
- janela associada de observabilidade com 1.368 pontos;
- commit Git e sinalização `immutable_for_decision: true`.

O arquivo canônico é
[`operational-state-20260920T024714Z/pdt-input-state.json`](./operational-state-20260920T024714Z/pdt-input-state.json).
A materialização e a decisão de uma candidata devem consumir esse arquivo, sem
reconsultar o operacional durante o mesmo ciclo decisório.
