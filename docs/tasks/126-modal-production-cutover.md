---
id: 126-modal-production-cutover
feature: sqlite-modal
status: done
depends_on: ["125-legacy-final-backup"]
---

# Task 126: Corte para o novo produto

**Descrição:** Direcionar uso para Modal com evidências de aceitação e um ponto explícito em que recuperações deixam de usar o banco antigo.

**Critérios de aceitação:**

- [x] Conferir nova URL/origins, Google/GitHub, capacidade e checkpoints; usuários entram novamente e reconectam contas.
- [x] Validar fluxo real e recuperação com dados novos; registrar aceitação humana do produto publicado antes de desativação.
- [x] Documentar que após dados novos rollback é restore/repair de checkpoints Modal; retornar ao banco antigo perde dados e não é rollback válido.

**Verificação:**

- [x] Teste/comando focado: `Reexecutar smoke/fluxo real publicado e comparar reservas/evidência/checkpoint com checklist de aceitação`.
- [x] Demo/check operacional: Horário, versão, URL e aceite registrados; histórico antigo descartado por autorização humana, Supabase preservado sem servir o produto. Backup final Postgres não realizado; limitação explícita na evidência 125.
- [x] QA/build e fluxo real registrados em [evidência de corte](evidence/126-cutover-acceptance.md), incluindo limites remanescentes em 124/125.

**Dependências:** [125-legacy-final-backup](125-legacy-final-backup.md).

**Arquivos prováveis:**

- `docs/sqlite-modal-cutover.md`
- `tasks/evidence/126-cutover-acceptance.md (novo)`

**Escopo estimado:** Pequeno (1–2 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
