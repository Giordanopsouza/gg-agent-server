---
id: 101-sqlite-runtime-wiring
feature: sqlite-modal
status: in-progress
depends_on: ["093-sqlite-recovery-cli","096-sqlite-task-evidence","098-google-direct-oidc","099-sqlite-openrouter-vault","100-sqlite-github-connections"]
---

# Task 101: API local com Google e SQLite

**Descrição:** Trocar o wiring FastAPI pelo candidato SQLite completo e validar o caminho autenticado até criar e consultar tarefa. Remover o ledger Postgres substituído sem manter uma matriz permanente de backends.

**Critérios de aceitação:**

- [x] Lifespan abre stores no mesmo banco; modelos/rotas existentes continuam válidos; erros SQLite viram respostas sanitizadas.
- [x] Todas as mutações HTTP usam barreira por revisão, incluindo sessão, credenciais, mensagens e webhook; resposta positiva não precede durabilidade.
- [x] Cookies autenticam HTTP/WebSocket e ownership em todas as rotas; chave administrativa permanece exclusiva de clientes administrativos.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_sqlite_runtime_api.py`.
- [ ] Demo/check operacional: Login real local de duas contas → conexões individuais → criar/consultar tarefa com dispatch desabilitado. Registrar que esta prova termina na admissão.
- [x] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [093-sqlite-recovery-cli](093-sqlite-recovery-cli.md), [096-sqlite-task-evidence](096-sqlite-task-evidence.md), [098-google-direct-oidc](098-google-direct-oidc.md), [099-sqlite-openrouter-vault](099-sqlite-openrouter-vault.md), [100-sqlite-github-connections](100-sqlite-github-connections.md).

**Arquivos prováveis:**

- `backend/gg/runtime/app.py`
- `backend/gg/runtime/web_sessions.py (remover após wiring de local_sessions.py)`
- `backend/gg/runtime/ledger.py (substituir pelo candidato 094–096)`
- `backend/gg/runtime/sqlite_ledger.py (remover após incorporação)`
- `backend/tests/test_sqlite_runtime_api.py (novo)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.

## Evidência — 2026-10-08

Implementação e limites registrados em
[provas 100–102](evidence/100-102-runtime-verification.md).

Código integrado e cinco testes API aprovados. Demo com duas contas humanas
aguarda configuração OAuth Google; primeiro bloqueio: `GG_GOOGLE_CLIENT_ID`
ausente. Prova real administrativa no Modal passou, incluindo restart e mensagem
idempotente; ela não substitui a prova de login humano exigida acima.
