---
id: 121-sqlite-architecture-record
feature: sqlite-modal
status: done
depends_on: ["102-durable-effect-barriers","107-incremental-event-sync","111-modal-runtime-server","118-remove-postgres-dependencies","120-remove-legacy-db-tooling"]
---

# Task 121: Registrar decisão SQLite

**Descrição:** Registrar ADR da substituição e atualizar documentação de arquitetura, preservando o conteúdo histórico das decisões anteriores.

**Critérios de aceitação:**

- [x] Novo ADR cobre SQLite local/snapshots, um escritor, durabilidade por revisão, Google sub e identidade externa.
- [x] ADRs 0005/0006 marcados como substituídos com link, sem apagar raciocínio histórico.
- [x] README e AGENTS.md descrevem fronteiras, comandos e persistência atual; novas instruções não mandam usar Postgres.

**Verificação:**

- [x] Teste/comando focado: `git diff --check`.
- [x] Demo/check operacional: Revisar decisões contra spec.md e comandos efetivamente implementados; carregar skill domain-modeling ao implementar ADR.
- [x] Sem mudança de código nesta task; resultados em [evidência 121–122](evidence/121-122-verification.md).

**Dependências:** [102-durable-effect-barriers](102-durable-effect-barriers.md), [107-incremental-event-sync](107-incremental-event-sync.md), [111-modal-runtime-server](111-modal-runtime-server.md), [118-remove-postgres-dependencies](118-remove-postgres-dependencies.md), [120-remove-legacy-db-tooling](120-remove-legacy-db-tooling.md).

**Arquivos prováveis:**

- `docs/adr/0008-sqlite-modal-google.md (novo)`
- `docs/adr/0005-runtime-postgres-ledger.md`
- `docs/adr/0006-sqlalchemy-alembic.md`
- `README.md`
- `AGENTS.md`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
