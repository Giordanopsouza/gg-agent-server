# Verificação 115–117 (2026-10-08)

Worktree: `091-sqlite-modal`. Os testes foram executados sem URL Postgres e
sem serviço externo. `UV_CACHE_DIR` e `RUFF_CACHE_DIR` apontaram para
`/private/tmp` porque os caches da worktree não eram graváveis no sandbox.

## Mapeamento do harness antigo

| Invariante Postgres antigo | Prova SQLite atual |
| --- | --- |
| Admissão idempotente concorrente, claim limitado e restart | `test_sqlite_ledger_integration.py::test_cross_connection_admission_claim_and_restart`, `test_sqlite_task_admission.py` |
| Lock entre conexões, rollback e revisão | `test_sqlite_db.py::test_concurrent_writers_and_lock`, `test_sqlite_db.py::test_pragmas_rollback_and_reopen`, `test_sqlite_ledger_integration.py::test_failed_write_rolls_back_and_evidence_survives_restart` |
| Eventos, recibos e intenção de publicação duráveis | `test_sqlite_ledger_integration.py::test_failed_write_rolls_back_and_evidence_survives_restart`, `test_sqlite_task_evidence.py`, `test_sqlite_task_effects.py` |
| Retenção e idempotência após expiração | `test_sqlite_task_evidence.py::test_retention_compact_owner_idempotency_after_purge_restart` |
| Configuração segura e versão futura | `test_sqlite_configuration.py`, `test_sqlite_db.py::test_migration_failure_is_atomic_and_retryable` |
| Backup, restore e falha segura de snapshot | `test_db_cli.py::test_real_cli_wal_backup_restore`, `test_db_cli.py::test_invalid_snapshot_fails_closed_without_changing_source` |

Os testes de parâmetros de URL, pool e CA do engine Postgres foram removidos
porque esse engine não é o runtime SQLite. A configuração atual exige caminhos
explícitos para banco e snapshot; abrir banco ausente ou com versão futura falha.

## Execução

- Testes focados de 115–116, com `-m 'not modal and not github'`: 81 passed,
  1 deselected, zero skips.
- Testes novos de configuração e integração SQLite: 4 passed.
- Sequência raiz: `make format-fix`, `make lint-fix`, `make format-check`,
  `make lint-check`, `make pre-commit`, `make unit-tests`: aprovada. O
  `make unit-tests` terminou com 446 passed, 2 deselected, zero skips.
- `import gg.sdk, gg.runtime, gg.server`: aprovado.
- Busca por `test_support.postgres_ledger` em `*.py`: nenhum resultado.
- `make build` foi tentado, mas parou na resolução de `setuptools>=61.0` e
  `wheel`: o ambiente não alcançou `pypi.org`. Nenhum build foi verificado.

Comparação com a evidência anterior 112–114: 456 passed, 3 skips legados,
2 deselected. A contagem mudou com a substituição dos testes exclusivos de
Postgres por quatro provas SQLite; os três skips Postgres desapareceram.

O teste Modal live permanece opt-in e os testes GitHub live continuam fora do
perfil unitário. Esta mudança troca somente testes e o tratamento de erro
SQLite na rota de auth; não requer execução de tarefa real no stack local.
