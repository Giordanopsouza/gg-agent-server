---
id: 091-sqlite-transactions
feature: sqlite-modal
status: done
depends_on: []
---

# Task 091: Transações SQLite do runtime

**Descrição:** Criar o mecanismo único de conexão, escrita e versionamento SQLite usado por todos os stores centrais. Entregar um demo de banco temporário antes de substituir o runtime ativo.

**Critérios de aceitação:**

- [x] WAL, synchronous=FULL, foreign_keys=ON e busy_timeout=10000 aplicados por conexão; SQL parametrizado e transações curtas com rollback.
- [x] PRAGMA user_version avança por migrações sequenciais transacionais; versões futuras e migração interrompida são rejeitadas.
- [x] Toda escrita bem-sucedida incrementa uma revisão na mesma transação; concorrência entre conexões não perde alterações.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_sqlite_db.py`.
- [x] Demo/check operacional: Abrir duas conexões sobre o mesmo arquivo temporário e demonstrar commit, rollback, lock e reabertura.

**Dependências:** Nenhuma.

**Arquivos prováveis:**

- `backend/gg/runtime/sqlite_db.py (novo)`
- `backend/gg/runtime/sqlite_migrations.py (novo)`
- `backend/tests/test_sqlite_db.py (novo)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

## Log

### [SWE] 2026-10-07 13:40 PDT — implementação

Implementados `sqlite_db.py` e `sqlite_migrations.py`: conexões WAL/FULL/FK/timeout 10 s, transações BEGIN IMMEDIATE, revisão atômica e rollback em BaseException. Leitura usa query_only; stores não podem fazer commit, mudar PRAGMAs nem alterar metadata por dentro da transação. Criação é explícita, e versões inválidas/futuras ou schemas incompletos falham fechado. A lease local mantida por SQLiteDB prepara a exclusão de operações administrativas da 093.

Prova: `uv run --no-editable pytest backend/tests/test_sqlite_db.py` (12 casos no conjunto final). Demo automatizado usa duas conexões e 22 inserts concorrentes: lock aguarda commit, rollback não incrementa revisão, reabertura conserva conteúdo e revisão. Morte abrupta de subprocesso durante DDL/PRAGMA reverte schema e versão. SQL parametrizado preserva valor com aspas.

Referências conferidas: [sqlite3 Python 3.12](https://docs.python.org/3.12/library/sqlite3.html), [PRAGMA SQLite](https://www.sqlite.org/pragma.html).

### [Tester] 2026-10-07 13:40 PDT — testes automatizados e build

Validação conjunta final: 37 testes focados passaram. Sequência concluída em ordem: `make format-fix`, `make lint-fix`, `make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests`; `make build` também passou para SDK/backend/sandbox. Tanto pre-commit quanto unit-tests: 258 passed, 92 skipped, 2 deselected, 1 warning de depreciação Starlette/httpx. A suíte legada requer URL Postgres local para parte dos casos; não foi alegada cobertura integral desses casos. Todos os testes novos SQLite executaram sem skips.

As provas são da fundação isolada prevista no plano. O runtime ativo segue seu wiring anterior; a integração SQLite só ocorre na 101, portanto o fluxo UI + gg.runtime com dispatch real ainda não exercita estes módulos. Nenhum deploy ou corte de infraestrutura foi feito. O ambiente não editável precisou de `uv sync --no-editable --reinstall-package gg-backend` depois de editar o pacote; evidências finais usam a instalação atualizada.
