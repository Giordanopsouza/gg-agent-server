---
id: 116-sqlite-auth-supervision-tests
feature: sqlite-modal
status: done
depends_on: ["113-sqlite-test-fixtures"]
---

# Task 116: Fixtures SQLite nos testes de supervisão

**Descrição:** Portar consumidores restantes de supervisão/publicação/login/GitHub para fixtures SQLite.

**Critérios de aceitação:**

- [x] Cinco consumidores usam helper SQLite; auth fixtures não criam profiles no Postgres.
- [x] Retomar intenção/recibo/publicação e rejeitar outro usuário continuam cobertos.
- [x] Tokens/provedores controlados permitem testes unitários sem login humano nem serviço externo.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_task_supervision_integration.py backend/tests/test_pi_owned_publication.py backend/tests/test_publication.py backend/tests/test_github_connection.py backend/tests/test_web_auth.py`.
- [x] Demo/check operacional: Testar callbacks/replay e restart da supervisão usando DB do mesmo caso.
- [x] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [113-sqlite-test-fixtures](113-sqlite-test-fixtures.md).

**Arquivos prováveis:**

- `backend/tests/test_task_supervision_integration.py`
- `backend/tests/test_pi_owned_publication.py`
- `backend/tests/test_publication.py`
- `backend/tests/test_github_connection.py`
- `backend/tests/test_web_auth.py`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.

**Resultado (2026-10-08):** Supervisão, publicação e auth usam arquivo SQLite
por caso; conexão GitHub já tinha teste SQLite de callback, replay e restore.
Provider e sessões são simulados. Ver [evidência 115–117](evidence/115-117-verification.md).
