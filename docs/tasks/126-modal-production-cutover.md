---
id: 126-modal-production-cutover
feature: sqlite-modal
status: pending
depends_on: ["125-legacy-final-backup"]
---

# Task 126: Corte para o novo produto

**Descrição:** Direcionar uso para Modal com evidências de aceitação e um ponto explícito em que recuperações deixam de usar o banco antigo.

**Critérios de aceitação:**

- [ ] Conferir nova URL/origins, Google/GitHub, capacidade e checkpoints; usuários entram novamente e reconectam contas.
- [ ] Validar fluxo real e recuperação com dados novos; registrar aceitação humana do produto publicado antes de desativação.
- [ ] Documentar que após dados novos rollback é restore/repair de checkpoints Modal; retornar ao banco antigo perde dados e não é rollback válido.

**Verificação:**

- [ ] Teste/comando focado: `Reexecutar smoke/fluxo real publicado e comparar reservas/evidência/checkpoint com checklist de aceitação`.
- [ ] Demo/check operacional: Registrar horário, versão, URL, backup final e pessoa que aceitou; manter sistema antigo sem admissões até aceite.
- [ ] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [125-legacy-final-backup](125-legacy-final-backup.md).

**Arquivos prováveis:**

- `docs/sqlite-modal-cutover.md`
- `tasks/evidence/126-cutover-acceptance.md (novo)`

**Escopo estimado:** Pequeno (1–2 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
