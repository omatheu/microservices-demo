# checkout-pdt-controller

Este é o plano de controle identificável do Partial Digital Twin. Ele é
separado da observabilidade e possui duas responsabilidades:

1. `plan`: validar e vincular a candidata, a decisão convencional selada, o
   snapshot operacional, os artefatos imutáveis, SLOs, modelo e alternativas;
2. `decide`: transformar observações contrafactuais em uma decisão
   `approve`, `block` ou `reconfigure`, sempre com confirmação humana.

O controlador não possui permissão para modificar `operational`. O plano fixa
`target_namespace: pdt`, execução sequencial, cleanup entre alternativas e
`operational_mutation_allowed: false`. O executor continua responsável por
materializar as alternativas no plano de dados `pdt`; o gate do pipeline
consome a decisão do controlador.

Uso local:

```bash
python3 experiment/pdt/controller/checkout_pdt_controller.py plan \
  --candidate candidate.json \
  --conventional-decision conventional-decision.json \
  --snapshot pdt-input-state.json \
  --thresholds experiment/staging/safety-thresholds.json \
  --model-policy experiment/pdt/model-policy.json \
  --repetition 1 \
  --output controller-plan.json
```

O `Dockerfile` fornece o mesmo runtime para execução como Job sob demanda no
namespace `pdt-system`. O runner pareado exige uma imagem publicada por digest,
aplica o Job antes das alternativas, captura o plano emitido pelo runtime,
compara-o com o preflight normalizado e remove todos os recursos do controlador.
A publicação da imagem e a primeira aplicação do Job continuam bloqueadas até
revisão de custo e autorização explícita.

[`../../scripts/prepare-pdt-controller-job.py`](../../scripts/prepare-pdt-controller-job.py)
gera esse Job a partir de uma imagem imutável e dos mesmos inputs selados. O
pod não recebe token da API Kubernetes, executa como usuário não-root, usa
filesystem somente leitura e recebe uma NetworkPolicy sem ingress ou egress.
O resultado é emitido no log do Job para ser capturado pela esteira; nenhum
Deployment permanente é criado.
