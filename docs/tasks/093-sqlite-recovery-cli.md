---
id: 093-sqlite-recovery-cli
feature: sqlite-modal
status: done
depends_on: ["091-sqlite-transactions","092-sqlite-checkpoints"]
---

# Task 093: Inicialização explícita do banco

**Descrição:** Disponibilizar init, migrate, backup e restore locais; validar snapshots antes de abrir o runtime e impedir recriação silenciosa de um banco perdido.

**Critérios de aceitação:**

- [x] Init cria banco novo somente por comando explícito e recusa sobrescrever estado; startup normal nunca usa criação implícita.
- [x] Snapshot ausente, corrompido ou incompatível falha fechado; restore valida integridade, schema e revisão sem alterar a origem.
- [x] Backup inclui commits ainda no WAL; migrate/restore exigem runtime parado e produzem snapshot verificável.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_db_cli.py backend/tests/test_checkpoints.py`.
- [x] Demo/check operacional: Init → escrita no WAL → backup → restore em outro diretório → comparação de dados e revisão.

**Dependências:** [091-sqlite-transactions](091-sqlite-transactions.md), [092-sqlite-checkpoints](092-sqlite-checkpoints.md).

**Arquivos prováveis:**

- `backend/gg/runtime/db_cli.py (novo)`
- `backend/gg/runtime/checkpoints.py`
- `backend/gg/runtime/sqlite_migrations.py`
- `backend/tests/test_db_cli.py (novo)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

## Log

### [SWE] 2026-10-07 13:40 PDT — implementação

Implementado `python -m gg.runtime.db_cli {init,migrate,backup,restore} --db PATH --snapshot PATH`. Init e restore recusam destinos existentes; restore requer local novo e não altera a origem. SQLiteDB abre apenas arquivos existentes e com schema atual. Migração usa lease exclusiva e exige banco já inicializado; restore também exige lease exclusiva do destino. A lease protege processos locais que seguem esta API; não bloqueia ferramentas SQLite externas que a ignorem.

Prova: `uv run --no-editable pytest backend/tests/test_db_cli.py backend/tests/test_checkpoints.py` (25 casos no conjunto final). Demo invoca o CLI em subprocessos: init → commit ainda no WAL → backup → restore em outro caminho → dados e revisão iguais. Fonte mantém hash; snapshot ausente/corrompido/futuro, schema/revisão inválidos, FK quebrada e dependência de WAL são rejeitados. Migrate/restore falham enquanto SQLiteDB mantém sua lease.

Uso local (diretório deve existir):

```bash
uv run --no-editable python -m gg.runtime.db_cli init --db /tmp/runtime.db --snapshot /tmp/runtime.snapshot
uv run --no-editable python -m gg.runtime.db_cli backup --db /tmp/runtime.db --snapshot /tmp/runtime.snapshot
uv run --no-editable python -m gg.runtime.db_cli restore --db /tmp/runtime-restored.db --snapshot /tmp/runtime.snapshot
uv run --no-editable python -m gg.runtime.db_cli migrate --db /tmp/runtime-restored.db --snapshot /tmp/runtime-migrated.snapshot
```

Se publicar o snapshot falhar após init/migrate, o commit local pode já existir; não interpretar o erro como rollback. Corrigir o destino e executar backup novamente. Restore recusa sobrescrever o banco; a seleção operacional do novo caminho fica no runbook da 112/122.

### [Tester] 2026-10-07 13:40 PDT — testes automatizados e build

Validação conjunta final: 37 testes focados passaram. Sequência concluída em ordem: `make format-fix`, `make lint-fix`, `make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests`; `make build` também passou para SDK/backend/sandbox. Tanto pre-commit quanto unit-tests: 258 passed, 92 skipped, 2 deselected, 1 warning de depreciação Starlette/httpx. A suíte legada requer URL Postgres local para parte dos casos; não foi alegada cobertura integral desses casos. Todos os testes novos SQLite executaram sem skips.

As provas são da fundação isolada prevista no plano. O runtime ativo segue seu wiring anterior; a integração SQLite só ocorre na 101, portanto o fluxo UI + gg.runtime com dispatch real ainda não exercita estes módulos. Nenhum deploy ou corte de infraestrutura foi feito. O ambiente não editável precisou de `uv sync --no-editable --reinstall-package gg-backend` depois de editar o pacote; evidências finais usam a instalação atualizada.
