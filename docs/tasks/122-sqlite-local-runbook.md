---
id: 122-sqlite-local-runbook
feature: sqlite-modal
status: done
depends_on: ["108-sandbox-sqlite-live-demo","112-modal-state-operations","120-remove-legacy-db-tooling","121-sqlite-architecture-record"]
---

# Task 122: Atualizar execução local

**Descrição:** Atualizar runbooks, comandos de QA e instruções locais para SQLite/Google, incluindo diferenças entre gg.server:8000 e gg.runtime:8001.

**Critérios de aceitação:**

- [x] Completar limpeza de comandos backend/exemplos locais iniciada na 120; frontend npm mantém build/testes sem servidor Node.
- [x] local-stack usa SQLite explicitamente inicializado, sessões Google e credenciais individuais; sem chave administrativa em localStorage.
- [x] Documentar requisitos live, callback local, proxy Vite explícito e sequência QA; manter tracker anterior com status/tarefas incompletas preservados.

**Verificação:**

- [x] Teste/comando focado: `make help; make frontend-test; make frontend-build; git diff --check`.
- [x] Demo/check operacional: Inicialização SQLite e health HTTP do runtime real; skill atualizada na worktree e versionada, conforme [evidência 121–122](evidence/121-122-verification.md).
- [x] Sem mudança de código nesta task; resultados e limite do login humano em [evidência 121–122](evidence/121-122-verification.md).

**Dependências:** [108-sandbox-sqlite-live-demo](108-sandbox-sqlite-live-demo.md), [112-modal-state-operations](112-modal-state-operations.md), [120-remove-legacy-db-tooling](120-remove-legacy-db-tooling.md), [121-sqlite-architecture-record](121-sqlite-architecture-record.md).

**Arquivos prováveis:**

- `backend/Makefile`
- `frontend/README.md`
- `docs/sqlite-modal-operations.md (novo)`
- `.agents/skills/local-stack/SKILL.md (local ignorada; sincronizar no handoff)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
