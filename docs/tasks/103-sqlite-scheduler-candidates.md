---
id: 103-sqlite-scheduler-candidates
feature: sqlite-modal
status: done
depends_on: ["096-sqlite-task-evidence","102-durable-effect-barriers"]
---

# Task 103: Consultas de candidatos do scheduler

**Descrição:** Substituir varreduras de histórico por consultas SQL limitadas a reservas, fila e workspaces candidatos à manutenção.

**Critérios de aceitação:**

- [x] Scheduler/supervisão não carregam todas as tarefas por ciclo; recuperação inclui apenas candidatos necessários.
- [x] Índices sustentam FIFO, reservas e expiração; manter cadência/limites atuais e recuperação de ciclo que falha.
- [x] Histórico volumoso não altera resultado nem número de registros retornados para um conjunto fixo de candidatos.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_scheduler.py backend/tests/test_scheduler_recovery.py`.
- [x] Demo/check operacional: Popular histórico sintético, usar EXPLAIN QUERY PLAN e registrar consultas/linhas retornadas por ciclo.

**Dependências:** [096-sqlite-task-evidence](096-sqlite-task-evidence.md), [102-durable-effect-barriers](102-durable-effect-barriers.md).

**Arquivos prováveis:**

- `backend/gg/runtime/ledger.py`
- `backend/gg/runtime/scheduler.py`
- `backend/gg/runtime/task_supervision/manager.py`
- `backend/tests/test_scheduler.py`
- `backend/tests/test_scheduler_recovery.py`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

## Resultado — 2026-10-08

Implementação e provas automatizadas na worktree 091. Ver
[provas 103–105](evidence/103-105-sqlite-sandbox-verification.md).
