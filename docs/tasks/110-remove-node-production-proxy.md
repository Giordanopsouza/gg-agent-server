---
id: 110-remove-node-production-proxy
feature: sqlite-modal
status: done
depends_on: ["109-fastapi-react-serving"]
---

# Task 110: Remover proxy Node de produção

**Descrição:** Simplificar scripts/build frontend para Vite/React, removendo o servidor Node de produção. Manter proxy Vite apenas para desenvolvimento local.

**Critérios de aceitação:**

- [x] Remover server.ts/server.test.ts e tsconfig.server.json; npm test/build não dependem mais do proxy de produção.
- [x] Build gera dist consumido pelo FastAPI; frontend usa origem relativa para HTTP/WebSocket/cookies.
- [x] Login, onboarding, tarefa, eventos e sessão expirada mantêm comportamento pelos testes existentes.

**Verificação:**

- [x] Teste/comando focado: `make frontend-test; make frontend-build`.
- [x] Demo/check operacional: Servir dist pelo FastAPI sem Node em execução e abrir fluxo de navegação/reload no navegador.

**Dependências:** [109-fastapi-react-serving](109-fastapi-react-serving.md).

**Arquivos prováveis:**

- `frontend/package.json`
- `frontend/server/ (remover dois arquivos)`
- `frontend/tsconfig.server.json (remover)`
- `frontend/src/api.test.ts`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

## Evidência de conclusão

Implementação, QA, demos reais, restore/recreate e limites documentados em
[109–111: verificação](evidence/109-111-verification.md). Onboarding público
Google permanece no escopo da 123; nenhum corte de produção realizado.
