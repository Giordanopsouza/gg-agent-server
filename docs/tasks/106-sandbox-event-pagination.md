---
id: 106-sandbox-event-pagination
feature: sqlite-modal
status: pending
depends_on: ["104-sandbox-sqlite-conversations"]
---

# Task 106: Eventos do sandbox por cursor

**Descrição:** Adicionar after e limit opcionais à leitura HTTP de eventos, sem alterar o formato da resposta. O consumo pela supervisão fica na 107; contratos SDK não precisam mudar.

**Critérios de aceitação:**

- [ ] Sem query params, resposta e ordem atuais permanecem; after é exclusivo e limit válido limita a consulta SQL.
- [ ] Parâmetros inválidos são rejeitados; páginas contíguas não omitem nem duplicam eventos.
- [ ] HTTP/WebSocket/Pydantic e imports do SDK mantêm fronteiras; clientes antigos continuam funcionando.

**Verificação:**

- [ ] Teste/comando focado: `uv run --no-editable pytest sandboxes/tests/test_event_routes.py sandboxes/tests/test_event_websocket.py packages/gg-sdk/tests/test_sdk_importable.py`.
- [ ] Demo/check operacional: Comparar várias páginas com leitura sem parâmetros; importar SDK independentemente do servidor.
- [ ] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [104-sandbox-sqlite-conversations](104-sandbox-sqlite-conversations.md).

**Arquivos prováveis:**

- `sandboxes/gg/server/event_routes.py`
- `sandboxes/gg/server/conversation_service.py`
- `sandboxes/gg/server/agent/event_log.py`
- `sandboxes/tests/test_event_routes.py`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
