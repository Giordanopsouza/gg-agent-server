---
id: 125-legacy-final-backup
feature: sqlite-modal
status: pending
depends_on: ["124-modal-recovery-measurements"]
---

# Task 125: Backup final do produto antigo

**Descrição:** Preparar o corte pausando admissões antigas, drenando/reconciliando trabalho e exportando dados da aplicação e Auth com restore isolado comprovado.

**Critérios de aceitação:**

- [ ] Identificar projeto/environment/services antigos por IDs e manter escopo separado do Modal; novas admissões antigas bloqueadas.
- [ ] Trabalho pendente concluído ou reconciliado; backup final inclui app_private/runtime_private/vault_private e auth, roles/permissões necessárias.
- [ ] Backup offline com checksum, localização restrita, chaves de recuperação separadas e restauração isolada verificada; nada importado no novo banco.

**Verificação:**

- [ ] Teste/comando focado: `Restaurar dump final em Postgres isolado; verificar contagens/constraints/identidades e possibilidade de decifrar amostra sem imprimir conteúdo`.
- [ ] Demo/check operacional: Usar docs atuais Supabase e tools autorizadas; não confiar só em um backup gerenciado nem deletar nada nesta etapa.
- [ ] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [124-modal-recovery-measurements](124-modal-recovery-measurements.md).

**Arquivos prováveis:**

- `docs/sqlite-modal-cutover.md (novo)`
- `tasks/evidence/125-legacy-backup.md (novo)`

**Escopo estimado:** Pequeno (1–2 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
