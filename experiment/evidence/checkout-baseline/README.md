# Linha de base funcional do checkoutservice

Em 20 de setembro de 2026 foram executadas três repetições com 20 transações de
checkout cada. Cada teste criou uma sessão, adicionou um produto ao carrinho,
enviou o pedido e validou simultaneamente o HTTP 2xx e o marcador
`Your order is complete!`.

Resultado da execução `checkout-baseline-20260920T031605Z`:

- 60 testes, 60 sucessos e nenhuma falha;
- p50 médio entre repetições: 391,828 ms;
- p95 médio: 441,009 ms; pior p95: 473,353 ms;
- p99 médio: 505,636 ms; pior p99: 522,877 ms.

Para os pilotos foram definidos os limites de p95 ≤ 600 ms e p99 ≤ 700 ms.
Eles aplicam margem de aproximadamente 25% ao pior valor observado, arredondada
para um limite conservador e legível. O protocolo comparativo deverá aceitar ou
revisar esses limites usando apenas baseline e especificação, nunca os
resultados do corpus de avaliação, e então congelá-los antes da coleta
principal.

O agregado sanitizado e versionável está em
[`aggregate-summary.json`](./aggregate-summary.json). Os diretórios de cada
execução permanecem locais ou em artefatos do pipeline e são ignorados pelo Git.
As 60 linhas brutas, os três resumos de repetição e este agregado foram
recalculados e vinculados por SHA-256 no
[`relatório de validação da Fase 1`](../baseline/validation-report.json).
