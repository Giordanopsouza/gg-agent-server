---
id: 110-remove-node-production-proxy
feature: sqlite-modal
status: pending
depends_on: ["109-fastapi-react-serving"]
---

# Task 110: Remover proxy Node de produção

**Descrição:** Simplificar scripts/build frontend para Vite/React, removendo o servidor Node de produção. Manter proxy Vite apenas para desenvolvimento local.

**Critérios de aceitação:**

- [ ] Remover server.ts/server.test.ts e tsconfig.server.json; npm test/build não dependem mais do proxy de produção.
- [ ] Build gera dist consumido pelo FastAPI; frontend usa origem relativa para HTTP/WebSocket/cookies.
- [ ] Login, onboarding, tarefa, eventos e sessão expirada mantêm comportamento pelos testes existentes.

**Verificação:**

- [ ] Teste/comando focado: `make frontend-test; make frontend-build`.
- [ ] Demo/check operacional: Servir dist pelo FastAPI sem Node em execução e abrir fluxo de navegação/reload no navegador.
- [ ] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [109-fastapi-react-serving](109-fastapi-react-serving.md).

**Arquivos prováveis:**

- `frontend/package.json`
- `frontend/server/ (remover dois arquivos)`
- `frontend/tsconfig.server.json (remover)`
- `frontend/src/api.test.ts`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
