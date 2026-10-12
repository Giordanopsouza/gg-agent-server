---
id: 106-sandbox-event-pagination
feature: sqlite-modal
status: done
depends_on: ["104-sandbox-sqlite-conversations"]
---

# Task 106: Eventos do sandbox por cursor

**Descrição:** Adicionar after e limit opcionais à leitura HTTP de eventos, sem alterar o formato da resposta. O consumo pela supervisão fica na 107; contratos SDK não precisam mudar.

**Critérios de aceitação:**

- [x] Sem query params, resposta e ordem atuais permanecem; after é exclusivo e limit válido limita a consulta SQL.
- [x] Parâmetros inválidos são rejeitados; páginas contíguas não omitem nem duplicam eventos.
- [x] HTTP/WebSocket/Pydantic e imports do SDK mantêm fronteiras; clientes antigos continuam funcionando.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest sandboxes/tests/test_event_routes.py sandboxes/tests/test_event_websocket.py packages/gg-sdk/tests/test_sdk_importable.py`.
- [x] Demo/check operacional: Comparar várias páginas com leitura sem parâmetros; importar SDK independentemente do servidor.

**Dependências:** [104-sandbox-sqlite-conversations](104-sandbox-sqlite-conversations.md).

**Arquivos prováveis:**

- `sandboxes/gg/server/event_routes.py`
- `sandboxes/gg/server/conversation_service.py`
- `sandboxes/gg/server/agent/event_log.py`
- `sandboxes/tests/test_event_routes.py`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

## Resultado — 2026-10-08

Implementação e aceite automatizado concluídos na worktree 091.
Ver [provas 106–107](evidence/106-107-verification.md).
