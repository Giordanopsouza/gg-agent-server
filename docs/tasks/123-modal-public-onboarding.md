---
id: 123-modal-public-onboarding
feature: sqlite-modal
status: pending
depends_on: ["108-sandbox-sqlite-live-demo","111-modal-runtime-server","112-modal-state-operations","118-remove-postgres-dependencies","121-sqlite-architecture-record","122-sqlite-local-runbook"]
---

# Task 123: Onboarding na URL Modal

**Descrição:** Configurar recursos reais e callbacks na URL HTTPS descoberta do Modal, depois validar login e conexões do produto publicado.

**Decisão do usuário — 2026-10-08:** Manter Google OAuth com público External
e status **Testing** enquanto o produto é usado apenas pelo proprietário.
A publicação do OAuth e a preparação de documentos para o lançamento público
ficam adiadas. Isso não impede configurar callbacks Modal nem executar as
provas reais de login, conexões e tarefas. O login atual pede apenas
`openid email`, abrangidos pela exceção do Google para autenticação básica:
usuários não precisam constar da lista de testes. A task continua pendente;
esta decisão não comprova os demais critérios abaixo. Ver
[evidência e regra oficial](evidence/123-modal-onboarding.md).

**Critérios de aceitação:**

- [ ] Google OAuth externo/publicado admite contas fora da lista de teste; origins/callbacks e GitHub webhook apontam exatamente à URL Modal.
- [ ] Login de duas contas, logout/revogação, OpenRouter/GitHub e repo privado funcionam com cookies Secure e isolamento.
- [ ] Tarefa pelo frontend publicado produz atividade HTTP/WebSocket, resposta correta, manifest/checks e liberação de reserva.

**Verificação:**

- [ ] Teste/comando focado: `make frontend-test; make frontend-build; smoke HTTP autenticado e prova live documentados no arquivo de evidência`.
- [ ] Demo/check operacional: Confirmar configuração com read-back sem segredos; login humano das duas contas é pré-requisito operacional, não substituído por mocks.
- [ ] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [108-sandbox-sqlite-live-demo](108-sandbox-sqlite-live-demo.md), [111-modal-runtime-server](111-modal-runtime-server.md), [112-modal-state-operations](112-modal-state-operations.md), [118-remove-postgres-dependencies](118-remove-postgres-dependencies.md), [121-sqlite-architecture-record](121-sqlite-architecture-record.md), [122-sqlite-local-runbook](122-sqlite-local-runbook.md).

**Arquivos prováveis:**

- `tasks/evidence/123-modal-onboarding.md (novo)`
- `docs/sqlite-modal-operations.md`
- `backend/tests/test_production_operations.py`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
