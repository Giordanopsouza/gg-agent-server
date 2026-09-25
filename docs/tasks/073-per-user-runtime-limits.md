---
id: 073-per-user-runtime-limits
feature: mvp-web
status: pending
depends_on: [062-task-ownership-and-idempotency, 071-durable-task-continuation]
---

# Limites por usuário e proteção de capacidade

## Migration preflight

Ler o [plano do MVP](../mvp-web-plan.md), os ADRs [0001](../adr/0001-modal-background-tasks.md), [0002](../adr/0002-general-background-tasks.md) e [0003](../adr/0003-remove-legacy-learning-surfaces.md), o AGENTS.md do componente e as tasks diretamente dependentes/consumidoras. Registrar estado final, pontes temporárias com legado, responsável pela remoção e teste que protege a fronteira. Inspecionar scheduler, reservas, storage e limites atuais. A chave pessoal OpenRouter não paga Modal; usar contadores duráveis existentes quando possível, sem novo broker.

## Scope

Limitar fila e execuções por usuário sem enfraquecer o limite global e a reconciliação de capacidade existentes.

## Acceptance criteria

- [ ] Configurar limites tipados de tarefas pendentes e execuções por usuário, além do teto global existente; documentar defaults e respostas de limite.
- [ ] Aplicar limites atomicamente em criação, retry e continuação; reenvio idempotente não consome quota adicional.
- [ ] Contabilizar reservas ativas e incertas até ausência confirmada do sandbox; restart não zera consumo.
- [ ] Despachar tarefas elegíveis sem que a quota esgotada de uma conta paralise todas as demais, preservando ordem entre candidatas elegíveis.
- [ ] Exibir limite atingido na UI com ação apropriada, sem revelar tarefas ou consumo de outra conta.
- [ ] Testar submissões concorrentes, cancelamento/limpeza pendente, recuperação e liberação de quota sem ultrapassar teto global.

## Validation

Testes de admissão/scheduler com duas contas e corridas no ledger; production-smoke-tests para a mudança operacional. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Billing, planos pagos, escalonamento distribuído e afirmar capacidade live de dez sandboxes.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.
