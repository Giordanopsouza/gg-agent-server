---
id: 096-sqlite-task-evidence
feature: sqlite-modal
status: done
depends_on: ["094-sqlite-task-admission","095-sqlite-task-effects"]
---

# Task 096: Evidência e retenção SQLite

**Descrição:** Completar o ledger com eventos, resultados e retenção, incluindo cursores que não retrocedem quando registros são expirados.

**Critérios de aceitação:**

- [x] Deduplicação por tarefa/conversa/source_seq; cursor público monotônico e contador sobrevivem à expiração de evidência.
- [x] Resultados, recibos e efeitos remotos conservam limites atuais; retenção protege tarefas/reservas em uso.
- [x] Idempotência compacta por usuário e contadores são preservados além da remoção de payload/tombstones; payload antigo não é retido sem limite.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_sqlite_task_evidence.py`.
- [x] Demo/check operacional: Expirar tarefas/eventos, reiniciar e submeter novas tarefas/replays para verificar ausência de reuso de sequências.

**Dependências:** [094-sqlite-task-admission](094-sqlite-task-admission.md), [095-sqlite-task-effects](095-sqlite-task-effects.md).

**Arquivos prováveis:**

- `backend/gg/runtime/sqlite_ledger.py`
- `backend/gg/runtime/sqlite_migrations.py`
- `backend/gg/runtime/storage.py`
- `backend/tests/test_sqlite_task_evidence.py (novo)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

## Log — 2026-10-07

Schema versão 4 e candidato portam cópias de eventos, resultados e contagem
de evidência em bytes UTF-8. Cursor por tarefa e identidades de origem ficam
separados do payload expirável. Replays de eventos já copiados continuam
retornando dedup após remover payload e reiniciar; novos eventos não reutilizam
cursores. Os limites/truncamentos de storage.py são reutilizados sem alteração.

Retenção seleciona tarefas terminais sem reserva e remove os payloads numa
transação: prompt/repositório/base/ref/detalhes, eventos, recibos, resultados,
credenciais privadas de sandbox e intenções. Tarefas ativas/sleeping e reservas
são protegidas. Tombstone guarda somente o efeito remoto compacto até seu prazo;
depois são removidos tombstone e task. O registro compacto por owner/key, a
sequência original e os contadores sobrevivem, sem conservar o prompt antigo.
Inserções novas de evidência em payload expirado são recusadas. Esse registro
compacto e as identidades de dedup são metadados duráveis; não contêm payloads.

Prova: sete testes em `uv run --no-editable pytest
backend/tests/test_sqlite_task_evidence.py`. Expiração, purge e restart conservam
idempotência da mesma chave para dois usuários e operador; tarefa seguinte tem
seq 4. Remover uma página mantém o cursor seguinte em 4 e não aceita replay.
Resultado/recibo têm round-trip e medição UTF-8; pressão e truncamento preservam
as funções existentes. PR compacta expira sem manter detalhes antigos. Falhas
injetadas em expiração ou insert de evento revertem dados, identidade e contador.

Arquivos de implementação: sqlite_ledger.py, sqlite_migrations.py e
 test_sqlite_task_evidence.py. storage.py não precisou de alteração.

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
