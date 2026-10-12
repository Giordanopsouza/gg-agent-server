---
id: 105-sandbox-sqlite-executions
feature: sqlite-modal
status: done
depends_on: ["104-sandbox-sqlite-conversations"]
---

# Task 105: Execuções SQLite no sandbox

**Descrição:** Portar execuções, manifests e intenções de publicação ao mesmo banco do sandbox, inclusive o comando independente usado pelo Pi.

**Critérios de aceitação:**

- [x] execution_id/start_key são gravados atomicamente com uniqueness; corrida admite uma execução e rejeita conflito de identidade.
- [x] Manifest e intenção de PR ficam no SQLite; adaptar consumidores do Path retornado por save_manifest e do --intent-path, sem fonte JSON paralela.
- [x] Crash/restart e timeout preservam resultados/recibos/marcador; helper Pi consulta a intenção SQLite e reconcilia PR sem duplicar.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest sandboxes/tests/test_task_supervisor.py sandboxes/tests/test_pi_publication.py`.
- [x] Demo/check operacional: Interromper entre admissão e início; repetir start_key/mensagem/publicação e verificar uma execução e uma PR.

**Dependências:** [104-sandbox-sqlite-conversations](104-sandbox-sqlite-conversations.md).

**Arquivos prováveis:**

- `sandboxes/gg/server/task_supervisor/store.py`
- `sandboxes/gg/server/task_supervisor/service.py`
- `sandboxes/gg/server/task_supervisor/pi_publication.py`
- `sandboxes/tests/test_task_supervisor.py`
- `sandboxes/tests/test_pi_publication.py`

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
