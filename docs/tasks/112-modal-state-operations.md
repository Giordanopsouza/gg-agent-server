---
id: 112-modal-state-operations
feature: sqlite-modal
status: done
depends_on: ["093-sqlite-recovery-cli","111-modal-runtime-server"]
---

# Task 112: Comandos operacionais Modal

**Descrição:** Expor inicialização, migração, backup, restauração e deploy por Makefiles, usando comandos remotos isolados quando o estado está no Volume.

**Critérios de aceitação:**

- [x] Root delega comandos documentados ao backend; init explícito cria snapshot inicial antes de primeiro deploy e nunca sobrescreve Volume inicializado.
- [x] Migrate/restore de produção exigem servidor parado e escritor exclusivo; backup ativo passa pelo coordenador, sem abrir outro escritor.
- [x] Deploy e rollover fixam recreate; falha de build preserva versão anterior; confirmar versão/health/ready e revision após deploy.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_db_cli.py backend/tests/test_modal_runtime.py; make help`.
- [x] Demo/check operacional: Init → deploy → backup → parada → restore/migrate → deploy; reproduzir no ambiente isolado usando a CLI instalada e --help.
- [x] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [093-sqlite-recovery-cli](093-sqlite-recovery-cli.md), [111-modal-runtime-server](111-modal-runtime-server.md).

**Arquivos prováveis:**

- `Makefile`
- `backend/Makefile`
- `backend/gg/runtime/db_cli.py`
- `backend/gg/runtime/modal_runtime.py`
- `backend/tests/test_db_cli.py`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.

**Resultado (2026-10-08):** 27 testes focados aprovados; ciclo operacional
real no ambiente isolado sqlite-111-proof, replay sem duplicação e snapshot
final revisão 1370. QA agregado: 456 passed, 3 skips legados, 2 deselected.
Ver [provas e limites](evidence/112-114-verification.md).
