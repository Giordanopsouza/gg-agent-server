---
id: 095-sqlite-task-effects
feature: sqlite-modal
status: done
depends_on: ["094-sqlite-task-admission"]
---

# Task 095: Identidades duráveis de execução

**Descrição:** Portar registros de criação de sandbox, supervisão, mensagens, cancelamento e publicação para o ledger SQLite. Esta etapa registra intenções; a barreira antes do efeito externo chega na 102.

**Critérios de aceitação:**

- [x] Intenções preservam sandbox_name/tags, provider_id, start_key, execution_id, branch, marcador de PR e versões de credencial.
- [x] Recibos por tarefa/mensagem são idempotentes; identidade conflitante é rejeitada; atualização parcial faz rollback.
- [x] Transições atuais de tarefa/workspace, cancelamento e publicação sobrevivem a restart sem introduzir novas funcionalidades de continuação.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_sqlite_task_effects.py`.
- [x] Demo/check operacional: Reabrir o banco entre intenção e confirmação simulada e demonstrar a recuperação das mesmas identidades.
- [x] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [094-sqlite-task-admission](094-sqlite-task-admission.md).

**Arquivos prováveis:**

- `backend/gg/runtime/sqlite_ledger.py`
- `backend/gg/runtime/sqlite_migrations.py`
- `backend/tests/test_sqlite_task_effects.py (novo)`
- `backend/tests/test_pi_owned_publication.py`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.

## Log — 2026-10-07

Schema versão 3 e candidato SQLite portam criação de sandbox, supervisão,
recibos, publicação, cancelamento e transições atuais de workspace. Intenções
preservam nome/tags/chave privada, versão de credencial, provider_id,
execution_id/start_key/conversa/branch e marcador/commit/PR. Replays de
criação/supervisão/publicação rejeitam identidades conflitantes. Alterações
simples e compostas passam pelo mesmo coordenador de revisão; não há commits
parciais. A barreira de checkpoint antes de efeitos externos permanece na 102.

Prova: 11 testes em `uv run --no-editable pytest
backend/tests/test_sqlite_task_effects.py`. O banco fecha entre intenção e
confirmação simulada; reabertura encontra exatamente as identidades originais.
Confirmações de provider/PR, versão de credencial e pedido de cancelamento
sobrevivem a outra reabertura. Replays não duplicam recibos; conflito de conteúdo
não altera o registro nem a revisão. Uma falha no update da tarefa reverte
junto o update da publicação. Também verificados conflito de start_key entre
tarefas, cancelamento queued, sleeping/wake, expiração de workspace e resultado
bem-sucedido preservado após perda do sandbox. Sem nova funcionalidade de continuação.

Arquivos de implementação: sqlite_ledger.py, sqlite_migrations.py e
 test_sqlite_task_effects.py; o ledger Postgres e seus consumidores permanecem ativos.

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
