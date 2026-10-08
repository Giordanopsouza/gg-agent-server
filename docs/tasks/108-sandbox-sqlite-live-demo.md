---
id: 108-sandbox-sqlite-live-demo
feature: sqlite-modal
status: pending
depends_on: ["102-durable-effect-barriers","104-sandbox-sqlite-conversations","105-sandbox-sqlite-executions","106-sandbox-event-pagination","107-incremental-event-sync"]
---

# Task 108: Imagem SQLite com tarefa real

**Descrição:** Publicar a nova imagem do sandbox e provar uma tarefa real através do frontend e runtime local com dispatch habilitado.

**Critérios de aceitação:**

- [ ] Imagem versionada inclui os stores SQLite e helper Pi; manter limite de dez sandboxes do produto e capacidade um na prova isolada.
- [ ] Tarefa real produz atividade, resposta que atende ao pedido, manifest persistido e liberação da reserva; confirmar checks executados.
- [ ] Repetição após restart do runtime não duplica execução/mensagem/PR; registrar URL, task_id, image e boundary comprovado.

**Verificação:**

- [ ] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_modal_image.py; teste live opt-in: uv run --no-editable pytest backend/tests/test_modal_sandbox_live.py -m modal`.
- [ ] Demo/check operacional: Usar local-stack atualizada para SQLite e sessão Google; tarefa em repo autorizado com alteração verificável e PR draft pelo Pi. A especificação prevalece sobre instruções obsoletas de Postgres/chave administrativa da local-stack; documentar init SQLite e sessão Google no demo antes da limpeza final 122.
- [ ] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [102-durable-effect-barriers](102-durable-effect-barriers.md), [104-sandbox-sqlite-conversations](104-sandbox-sqlite-conversations.md), [105-sandbox-sqlite-executions](105-sandbox-sqlite-executions.md), [106-sandbox-event-pagination](106-sandbox-event-pagination.md), [107-incremental-event-sync](107-incremental-event-sync.md).

**Arquivos prováveis:**

- `backend/gg/runtime/modal_image.py`
- `sandboxes/Dockerfile`
- `backend/tests/test_modal_image.py`
- `backend/tests/test_modal_sandbox_live.py`
- `tasks/evidence/108-sandbox-demo.md (novo)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
