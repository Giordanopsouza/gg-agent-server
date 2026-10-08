---
id: 109-fastapi-react-serving
feature: sqlite-modal
status: pending
depends_on: ["101-sqlite-runtime-wiring"]
---

# Task 109: React servido pelo FastAPI

**Descrição:** Servir assets e fallback de navegação React no mesmo processo FastAPI, com origem pública explicitamente configurada.

**Critérios de aceitação:**

- [ ] Rotas API/auth/webhook/health/ready e WebSocket têm precedência; endpoint API inexistente não retorna index.html.
- [ ] Assets válidos e deep links servem build; paths inválidos/traversal são rejeitados; cache não vaza respostas de sessão.
- [ ] URL/callbacks usam web_origin HTTPS; hostname encaminhado aceito somente quando corresponde à origem configurada.

**Verificação:**

- [ ] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_static_web.py`.
- [ ] Demo/check operacional: Abrir deep link, recarregar, consultar /auth/session e testar header forwarded/host forjado com o build real.
- [ ] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [101-sqlite-runtime-wiring](101-sqlite-runtime-wiring.md).

**Arquivos prováveis:**

- `backend/gg/runtime/app.py`
- `backend/gg/runtime/static_web.py (novo)`
- `backend/gg/runtime/config.py`
- `backend/tests/test_static_web.py (novo)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
