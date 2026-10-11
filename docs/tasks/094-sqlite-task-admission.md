---
id: 094-sqlite-task-admission
feature: sqlite-modal
status: done
depends_on: ["091-sqlite-transactions"]
---

# Task 094: Admissão de tarefas SQLite

**Descrição:** Portar o caminho submit/get/list/reserve/release para SQLite, preservando modelos e contratos atuais, com testes contra o candidato antes de trocar o wiring.

**Critérios de aceitação:**

- [x] Idempotência por owner_id, inclusive namespace administrativo explícito, e FIFO sobrevivem à reabertura.
- [x] Reserva concorrente respeita capacidade dez; decisão de capacidade e reserva são uma transação.
- [x] Sequência usa contador persistente, nunca MAX(seq)+1; UUID, timestamps e nulls preservam o contrato Pydantic.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_sqlite_task_admission.py`.
- [x] Demo/check operacional: Submeter a mesma chave para dois usuários e concorrer reservas com mais solicitantes que vagas.
- [x] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [091-sqlite-transactions](091-sqlite-transactions.md).

**Arquivos prováveis:**

- `backend/gg/runtime/sqlite_ledger.py (novo; candidato durante port)`
- `backend/gg/runtime/sqlite_migrations.py`
- `backend/tests/test_sqlite_task_admission.py (novo)`
- `backend/tests/test_task_ownership.py`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.

## Execução em etapas

Inventário antes de implementação: (a) compatibilidade da fundação em
`sqlite_db.py`, `sqlite_migrations.py`, `test_sqlite_db.py` (três arquivos);
(b) admissão em `sqlite_ledger.py`, schema versão 2 e
`test_sqlite_task_admission.py` (três arquivos). O registro nesta task e o
checkpoint do plano completam a documentação; não houve alteração de consumidores.
Os schemas das famílias 095/096 foram adicionados nas versões 3/4.

## Log — 2026-10-07

Implementado candidato `sqlite_ledger.TaskLedger`, sem import de Postgres,
SQLAlchemy, runtime ativo ou sandbox. Todas as mutações usam SQLiteDB.write;
BEGIN IMMEDIATE cobre a decisão de capacidade e a reserva. O contador `task_seq`
é persistente e incrementado na mesma transação do insert, sem MAX(seq).
UUIDs são parâmetros texto, datas UTC e nulls voltam aos modelos Pydantic.
Índices únicos distinguem owner_id de namespace administrativo NULL.

Prova: oito testes em `uv run --no-editable pytest
backend/tests/test_sqlite_task_admission.py`. Dois usuários e um operador
submetem a mesma chave e recuperam identidades distintas após fechar/reabrir.
24 replays concorrentes inserem uma tarefa. 18 conexões concorrentes disputam
10 vagas: as sequências 1–10 são reservadas, a 11 só após liberação. Falha
injetada entre reserva e estado reverte ambos e não avança revisão. Migração
1→4 preserva revisão, e índice ausente bloqueia abertura. Init novo começa
em revisão zero; upgrade de banco existente continua incrementando por versão.
Os testes da fundação agora usam SCHEMA_VERSION para versões sintéticas.

### Verificação conjunta e limite da prova

Sequência QA concluída **em ordem**: `make format-fix`, `make lint-fix`,
`make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests`.
Pre-commit e unit-tests: **284 passed, 92 skipped, 2 deselected**, um warning
legado Starlette/httpx. `make build` passou para SDK/backend/sandbox. Regressão
focada das tarefas 091–096: **63 passed**, sem skips; 26 casos novos de ledger.
Instalação atualizada com `uv sync --no-editable --reinstall-package gg-backend`
antes da prova final. `git diff --check` passou.

Conferida a skill local-stack: o primeiro pré-requisito ausente para provar este
candidato via frontend + gg.runtime com dispatch é o wiring SQLite da 101.
`backend/gg/runtime/app.py` ainda importa ledger.TaskLedger/RuntimePostgres e
exige GG_RUNTIME_DATABASE_URL. A prova cobre chamadas reais ao ledger candidato,
SQLite em arquivo, transações, concorrência, reabertura e retenção; não cobre UI,
provider Modal real ou Volume.commit. Não houve deploy nem mudança de recurso externo.
