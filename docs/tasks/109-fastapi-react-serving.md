---
id: 109-fastapi-react-serving
feature: sqlite-modal
status: done
depends_on: ["101-sqlite-runtime-wiring"]
---

# Task 109: React servido pelo FastAPI

**Descrição:** Servir assets e fallback de navegação React no mesmo processo FastAPI, com origem pública explicitamente configurada.

**Critérios de aceitação:**

- [x] Rotas API/auth/webhook/health/ready e WebSocket têm precedência; endpoint API inexistente não retorna index.html.
- [x] Assets válidos e deep links servem build; paths inválidos/traversal são rejeitados; cache não vaza respostas de sessão.
- [x] URL/callbacks usam web_origin HTTPS; hostname encaminhado aceito somente quando corresponde à origem configurada.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_static_web.py`.
- [x] Demo/check operacional: Abrir deep link, recarregar, consultar /auth/session e testar header forwarded/host forjado com o build real.

**Dependências:** [101-sqlite-runtime-wiring](101-sqlite-runtime-wiring.md).

**Arquivos prováveis:**

- `backend/gg/runtime/app.py`
- `backend/gg/runtime/static_web.py (novo)`
- `backend/gg/runtime/config.py`
- `backend/tests/test_static_web.py (novo)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

## Evidência de conclusão

Implementação, QA, demos reais, restore/recreate e limites documentados em
[109–111: verificação](evidence/109-111-verification.md). Onboarding público
Google permanece no escopo da 123; nenhum corte de produção realizado.
