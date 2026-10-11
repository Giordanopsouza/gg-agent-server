---
id: 092-sqlite-checkpoints
feature: sqlite-modal
status: done
depends_on: ["091-sqlite-transactions"]
---

# Task 092: Checkpoints por revisão

**Descrição:** Provar cedo a barreira de durabilidade com sqlite3.backup() e um adaptador mínimo de commit do Volume, usando falhas controladas sem deploy.

**Critérios de aceitação:**

- [x] Snapshot fechado, validado e publicado por arquivo temporário/rename antes de Volume.commit(); checkpoints são serializados.
- [x] Revisão confirmada corresponde ao conteúdo do backup; escrita durante commit continua pendente e exige novo checkpoint.
- [x] Falha ou cancelamento não confirma revisão nem libera waiters; retry recupera o estado sem descartar commit local.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_checkpoints.py`.
- [x] Demo/check operacional: Bloquear o commit simulado, escrever outra alteração e provar que o primeiro checkpoint não confirma a segunda.
- [x] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [091-sqlite-transactions](091-sqlite-transactions.md).

**Arquivos prováveis:**

- `backend/gg/runtime/checkpoints.py (novo)`
- `backend/gg/runtime/sqlite_db.py`
- `backend/tests/test_checkpoints.py (novo)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.

## Log

### [SWE] 2026-10-07 13:40 PDT — implementação

Implementado `checkpoints.py`: backup SQLite que inclui WAL, fechamento e validação (integridade, FK, schema, revisão e ausência de sidecars), fsync, publicação por arquivo temporário/rename e commit assíncrono injetável. A revisão vem da cópia pronta; confirmed_revision só avança após commit. Checkpoints são serializados, inclusive sob cancelamento repetido; alteração local continua pendente após falha.

Prova: `uv run --no-editable pytest backend/tests/test_checkpoints.py` (12 casos no conjunto final). Demo bloqueia commit, grava segunda alteração e comprova que somente o segundo checkpoint libera seu waiter. Falha de commit/rename, retry e cancelamento são exercitados; snapshot anterior sobrevive a erro de publicação. Destino não pode sobrescrever DB ativo nem seus arquivos auxiliares.

Boundary: função de commit simulada e sem deploy. A conexão ao `Volume.commit.aio`, agendamento periódico e barreiras HTTP/efeitos pertencem a 101/102/111. Um coordenador por runtime/Volume; lease de arquivo não é lock distribuído. A geração local do backup é síncrona; nenhuma medição de latência cloud foi alegada.

### [Tester] 2026-10-07 13:40 PDT — testes automatizados e build

Validação conjunta final: 37 testes focados passaram. Sequência concluída em ordem: `make format-fix`, `make lint-fix`, `make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests`; `make build` também passou para SDK/backend/sandbox. Tanto pre-commit quanto unit-tests: 258 passed, 92 skipped, 2 deselected, 1 warning de depreciação Starlette/httpx. A suíte legada requer URL Postgres local para parte dos casos; não foi alegada cobertura integral desses casos. Todos os testes novos SQLite executaram sem skips.

As provas são da fundação isolada prevista no plano. O runtime ativo segue seu wiring anterior; a integração SQLite só ocorre na 101, portanto o fluxo UI + gg.runtime com dispatch real ainda não exercita estes módulos. Nenhum deploy ou corte de infraestrutura foi feito. O ambiente não editável precisou de `uv sync --no-editable --reinstall-package gg-backend` depois de editar o pacote; evidências finais usam a instalação atualizada.
