---
id: 104-sandbox-sqlite-conversations
feature: sqlite-modal
status: done
depends_on: ["091-sqlite-transactions"]
---

# Task 104: Conversas SQLite no sandbox

**Descrição:** Criar banco por sandbox com journal DELETE e portar metadados, base state, eventos e recibos, mantendo workspace e arquivos internos do Pi.

**Critérios de aceitação:**

- [x] Uma conexão configurada por operação/componente usa foreign_keys e espera por lock, com transações curtas; journal DELETE.
- [x] Metadados, eventos e recibos persistem após restart do processo no mesmo filesystem e mantêm modelos/ordem atuais.
- [x] Nenhum JSON de estado da aplicação continua como fonte de verdade neste caminho; arquivos nativos do Pi e código/artefatos continuam intactos.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest sandboxes/tests/test_event_log.py sandboxes/tests/test_local_conversation.py`.
- [x] Demo/check operacional: Reabrir conversa com o mesmo DB após interrupção e verificar metadados, eventos, recibos e diretório do Pi.

**Dependências:** [091-sqlite-transactions](091-sqlite-transactions.md).

**Arquivos prováveis:**

- `sandboxes/gg/server/sqlite_state.py (novo)`
- `sandboxes/gg/server/agent/event_log.py`
- `sandboxes/gg/server/agent/local_conversation.py`
- `sandboxes/tests/test_event_log.py`
- `sandboxes/tests/test_local_conversation.py`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

## Resultado — 2026-10-08

Implementação e provas automatizadas na worktree 091. Ver
[provas 103–105](evidence/103-105-sqlite-sandbox-verification.md).

Aceite operacional concluído com frontend/runtime e Pi/OpenRouter no Modal.
Reinício central e recriação do sandbox no mesmo Volume preservaram conversa,
eventos, recibos, sessão Pi, manifests e arquivo solicitado. Replay não duplicou
execução; a limpeza confirmou zero reservas e zero tarefas pendentes. Helper e
queda após admissão foram verificados em processos independentes na imagem real.
Timeout/reconciliação de PR usam Git local e gh controlado; nenhuma PR GitHub
real foi criada. Detalhes e limites estão nas provas vinculadas acima.
