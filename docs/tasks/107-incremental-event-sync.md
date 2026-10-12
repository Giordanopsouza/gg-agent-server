---
id: 107-incremental-event-sync
feature: sqlite-modal
status: done
depends_on: ["096-sqlite-task-evidence","106-sandbox-event-pagination"]
---

# Task 107: Sincronização incremental de eventos

**Descrição:** Usar páginas de até 200 eventos na supervisão, com cursor da origem por tarefa/conversa e inserção transacional de cada página.

**Critérios de aceitação:**

- [x] Cursor de origem e eventos da página são commitados juntos; deduplicação preserva cursor público monotônico.
- [x] Respeitar limites de evidência; truncar payload sem interromper avanço do cursor; trocar conversa abre cursor independente.
- [x] Após rollback/restart/retry, retomar da última página completa; WebSocket notifica somente eventos inseridos.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_incremental_event_sync.py backend/tests/test_task_supervision_integration.py`.
- [x] Demo/check operacional: Sincronizar 450 eventos, reiniciar no limite de página e confirmar igualdade de evidência sem reler todo o histórico.

**Dependências:** [096-sqlite-task-evidence](096-sqlite-task-evidence.md), [106-sandbox-event-pagination](106-sandbox-event-pagination.md).

**Arquivos prováveis:**

- `backend/gg/runtime/ledger.py`
- `backend/gg/runtime/sqlite_migrations.py`
- `backend/gg/runtime/task_supervision/manager.py`
- `backend/tests/test_task_supervision_integration.py`
- `backend/tests/test_incremental_event_sync.py (novo)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

## Resultado — 2026-10-08

Implementação e aceite automatizado concluídos na worktree 091.
Ver [provas 106–107](evidence/106-107-verification.md).
