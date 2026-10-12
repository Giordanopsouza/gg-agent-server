---
id: 115-sqlite-scheduler-test-imports
feature: sqlite-modal
status: done
depends_on: ["113-sqlite-test-fixtures"]
---

# Task 115: Fixtures SQLite nos testes de dispatch

**Descrição:** Portar consumidores do helper nos testes de scheduler, sandbox, latência e operação.

**Critérios de aceitação:**

- [x] Testes unitários não exigem Postgres nem skipam por URL ausente.
- [x] Capacidade/FIFO/recovery/health continuam cobertos com providers simulados e arquivo SQLite real.
- [x] Casos live continuam opt-in modal sem ocultar casos unitários.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_scheduler.py backend/tests/test_modal_sandbox.py backend/tests/test_runtime_latency.py backend/tests/test_production_operations.py -m 'not modal and not github'`.
- [x] Demo/check operacional: Rodar sem rede e demonstrar concorrência entre conexões e recuperação de ciclo.

**Dependências:** [113-sqlite-test-fixtures](113-sqlite-test-fixtures.md).

**Arquivos prováveis:**

- `backend/tests/test_scheduler.py`
- `backend/tests/test_modal_sandbox.py`
- `backend/tests/test_modal_sandbox_live.py`
- `backend/tests/test_runtime_latency.py`
- `backend/tests/test_production_operations.py`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Resultado (2026-10-08):** Scheduler usa o helper SQLite comum com conexões
independentes; testes de sandbox, latência e operação foram portados. Teste
focado conjunto de 115–116: 81 passed, 1 deselected, zero skips. Ver
[evidência 115–117](evidence/115-117-verification.md).
