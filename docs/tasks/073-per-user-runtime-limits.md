---
id: 073-per-user-runtime-limits
feature: mvp-web
status: pending
depends_on: [062-task-ownership-and-idempotency, 071-durable-task-continuation]
---

# Limites por usuário e proteção de capacidade

## Scope

Limitar fila e execuções por usuário sem enfraquecer o limite global e a reconciliação de capacidade existentes.

## Acceptance criteria

- [ ] Configurar limites tipados de tarefas pendentes e execuções por usuário, além do teto global existente; documentar defaults e respostas de limite.
- [ ] Aplicar limites atomicamente em criação, retry e continuação; reenvio idempotente não consome quota adicional.
- [ ] Contabilizar reservas ativas e incertas até ausência confirmada do sandbox; restart não zera consumo.
- [ ] Despachar tarefas elegíveis sem que a quota esgotada de uma conta paralise todas as demais, preservando ordem entre candidatas elegíveis.
- [ ] Exibir limite atingido na UI com ação apropriada, sem revelar tarefas ou consumo de outra conta.
- [ ] Testar submissões concorrentes, cancelamento/limpeza pendente, recuperação e liberação de quota sem ultrapassar teto global.

- [ ] Provar atomicidade de quotas em Postgres real com conexões concorrentes e restart; não usar SQLite em memória como prova das transações de produção. Definir teto de duração, fila, taxa de admissão e gasto de infraestrutura por período; testar bloqueio e recuperação sem depender de sandboxes pagos para cada caso.

## Validation

Testes de admissão/scheduler com duas contas e corridas no ledger; production-smoke-tests para a mudança operacional. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Billing, planos pagos, escalonamento distribuído e afirmar capacidade live de dez sandboxes.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.

### [PA] 2026-09-25 — Revisão para produção com Supabase

Plano atualizado por solicitação do usuário: Supabase Auth/Postgres, isolamento e provas no ambiente publicado. Critérios continuam pendentes; esta revisão não implementa nem valida o serviço.
