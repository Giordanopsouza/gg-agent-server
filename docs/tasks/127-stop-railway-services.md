---
id: 127-stop-railway-services
feature: sqlite-modal
status: pending
depends_on: ["126-modal-production-cutover"]
---

# Task 127: Parar serviços Railway

**Descrição:** Parar frontend e backend antigos no Railway após aceitação, verificando o estado dos serviços e que Modal segue atendendo.

**Critérios de aceitação:**

- [ ] IDs exatos e backup/aceite conferidos; parar somente os dois serviços antigos, sem remover recursos compartilhados.
- [ ] Read-back comprova serviços/deploys parados e ausência de tráfego de aplicação dependente deles.
- [ ] Modal continua login/tarefa/checkpoint; registrar estado/IDs e efeitos da operação, sem relançar o produto antigo.

**Verificação:**

- [ ] Teste/comando focado: `Railway CLI/MCP: status antes e depois, escopo por IDs; smoke Modal após parada`.
- [ ] Demo/check operacional: Aplicar use-railway com intenção já confirmada nesta especificação e aceite 126 registrado; descobrir comandos de parada pelo --help.
- [ ] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [126-modal-production-cutover](126-modal-production-cutover.md).

**Arquivos prováveis:**

- `docs/sqlite-modal-cutover.md`
- `tasks/evidence/127-railway-shutdown.md (novo)`

**Escopo estimado:** Pequeno (1–2 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
