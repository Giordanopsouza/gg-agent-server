---
id: 122-sqlite-local-runbook
feature: sqlite-modal
status: pending
depends_on: ["108-sandbox-sqlite-live-demo","112-modal-state-operations","120-remove-legacy-db-tooling","121-sqlite-architecture-record"]
---

# Task 122: Atualizar execução local

**Descrição:** Atualizar runbooks, comandos de QA e instruções locais para SQLite/Google, incluindo diferenças entre gg.server:8000 e gg.runtime:8001.

**Critérios de aceitação:**

- [ ] Completar limpeza de comandos backend/exemplos locais iniciada na 120; frontend npm mantém build/testes sem servidor Node.
- [ ] local-stack usa SQLite explicitamente inicializado, sessões Google e credenciais individuais; sem chave administrativa em localStorage.
- [ ] Documentar requisitos live, callback local, proxy Vite explícito e sequência QA; manter tracker anterior com status/tarefas incompletas preservados.

**Verificação:**

- [ ] Teste/comando focado: `make help; make frontend-test; make frontend-build; git diff --check`.
- [ ] Demo/check operacional: Aplicar runbook/skill SQLite no fluxo real; skill ignorada pelo Git exige localização/handoff registrados, sem editar checkout principal nesta task.
- [ ] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [108-sandbox-sqlite-live-demo](108-sandbox-sqlite-live-demo.md), [112-modal-state-operations](112-modal-state-operations.md), [120-remove-legacy-db-tooling](120-remove-legacy-db-tooling.md), [121-sqlite-architecture-record](121-sqlite-architecture-record.md).

**Arquivos prováveis:**

- `backend/Makefile`
- `frontend/README.md`
- `docs/sqlite-modal-operations.md (novo)`
- `.agents/skills/local-stack/SKILL.md (local ignorada; sincronizar no handoff)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
