---
id: 097-sqlite-local-sessions
feature: sqlite-modal
status: done
depends_on: ["091-sqlite-transactions","092-sqlite-checkpoints"]
---

# Task 097: Usuários e sessões locais

**Descrição:** Criar usuários identificados por Google sub e sessões locais opacas de sete dias, usando o mesmo banco e mecanismo transacional do ledger.

**Critérios de aceitação:**

- [x] sub único aponta para UUID local; troca de email não muda ownership; duas contas não compartilham dados.
- [x] Token aleatório fica apenas no cookie; banco guarda hash, expiração e revogação; consulta de sessão dispensa chamadas ao Google.
- [x] Criação/revogação passam por revisão e checkpoint; sessão expirada ou revogada é rejeitada também após restore.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_local_sessions.py`.
- [x] Demo/check operacional: Criar/revogar sessão, restaurar o snapshot e confirmar rejeição sem acesso de rede.
- [x] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [091-sqlite-transactions](091-sqlite-transactions.md), [092-sqlite-checkpoints](092-sqlite-checkpoints.md).

**Arquivos prováveis:**

- `backend/gg/runtime/local_sessions.py (novo)`
- `backend/gg/runtime/sqlite_migrations.py`
- `backend/tests/test_local_sessions.py (novo)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.

## Evidência — 2026-10-08

- `LocalSessions` usa o mesmo `SQLiteDB`/`CheckpointCoordinator`; migração 5 cria usuários por `google_sub` único e sessões por SHA-256 do token. UUID permanece estável quando o email muda.
- Dois testes novos comprovam duas identidades, tokens somente como hash, expiração de sete dias, barreira que espera o commit, 503 sanitizado e revogação repetível após falha. Snapshot restaurado rejeita tokens expirados/revogados/forjados sem chamar Google.
- Arquivos de implementação/teste: `local_sessions.py`, `sqlite_migrations.py`, `test_local_sessions.py` (3).
- Grupo 097–099: 30 testes novos aprovados. QA executado em ordem: `make format-fix`, `make lint-fix`, `make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests`; resultado amplo **314 passed, 92 skipped, 2 deselected**. Skips legados dependem de Postgres ausente; não são prova de compatibilidade completa com o backend antigo.
- `make build` aprovou sdist/wheel de gg-sdk, gg-backend e gg-sandbox; `git diff --check` limpo. Instalação não editável foi reconstruída antes do QA para incorporar módulos novos.
- Limite da prova: candidato SQLite e HTTP in-process com transportes controlados, snapshots locais e fronteira de despacho simulada. Sem login Google humano, Volume real ou tarefa frontend→runtime→Modal. Primeiro pré-requisito ausente para esse E2E é o wiring SQLite da 101, que depende também da conexão GitHub SQLite da 100. A skill local-stack foi consultada; o app publicado continua usando o wiring antigo. A autorização condicional para 101 fica registrada, mas não foi necessário antecipá-la para comprovar estas três fatias.
