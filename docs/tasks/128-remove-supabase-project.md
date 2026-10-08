---
id: 128-remove-supabase-project
feature: sqlite-modal
status: pending
depends_on: ["127-stop-railway-services"]
---

# Task 128: Excluir Supabase após aceite

**Descrição:** Excluir o projeto Supabase antigo e retirar configuração de produção obsoleta, conservando apenas história/documentação arquivada e backup offline.

**Critérios de aceitação:**

- [ ] Conferir project ref, restore 125 e aceite 126; nenhuma chamada/variável/certificado/conexão ativa ainda depende do projeto.
- [ ] Excluir projeto alvo e verificar ausência pelo serviço de gerenciamento; guardar backup e chaves separadas.
- [ ] Remover frontend/railway.json e configurações CLI antigas; auditar env/docs/skills locais e substituir instruções ativas de Supabase/Railway, sem apagar evidência histórica.

**Verificação:**

- [ ] Teste/comando focado: `Read-back do projeto; rg de referências ativas; make unit-tests; make frontend-test; make frontend-build`.
- [ ] Demo/check operacional: Conferir funcionamento Modal após remoção; preservar backup offline e registrar limpeza de configurações ignoradas fora do Git.
- [ ] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [127-stop-railway-services](127-stop-railway-services.md).

**Arquivos prováveis:**

- `frontend/railway.json (remover)`
- `docs/sqlite-modal-cutover.md`
- `tasks/evidence/128-supabase-removal.md (novo)`
- `configurações locais antigas Supabase/Railway (inventariar antes de remover)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
