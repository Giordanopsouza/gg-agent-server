---
id: 100-sqlite-github-connections
feature: sqlite-modal
status: done
depends_on: ["097-sqlite-local-sessions","098-google-direct-oidc"]
---

# Task 100: Conexão GitHub SQLite

**Descrição:** Portar conexão, instalação, OAuth flow e deduplicação de webhook GitHub para SQLite, mantendo autorização de repositórios e token restrito por tarefa.

**Critérios de aceitação:**

- [x] Flows vinculados a usuário/sessão, expiração e consumo único; conexões cifradas e instalações preservam constraints existentes.
- [x] Webhook autenticado é deduplicado; alterações, callbacks e desconexões usam revisão/checkpoint antes de confirmação.
- [x] Dois usuários isolados; autorização de repo ocorre no servidor e token entregue à tarefa mantém escopo limitado.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_github_connection.py backend/tests/test_repository_authorization.py`.
- [x] Demo/check operacional: Repetir webhook/callback e forjar owner/repository em request; verificar rejeição e ausência de vazamento.
- [x] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [097-sqlite-local-sessions](097-sqlite-local-sessions.md), [098-google-direct-oidc](098-google-direct-oidc.md).

**Arquivos prováveis:**

- `backend/gg/runtime/github_connection.py`
- `backend/gg/runtime/sqlite_migrations.py`
- `backend/gg/runtime/repository_authorization.py`
- `backend/tests/test_github_connection.py`
- `backend/tests/test_repository_authorization.py`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.

## Evidência — 2026-10-08

Implementação e limites registrados em
[provas 100–102](evidence/100-102-runtime-verification.md).

Testes focados e QA aprovados; barreiras e recuperação exercitadas com
falhas controladas e tarefa real no Modal. Ver provas para o limite Google/PR/Volume.
