---
id: 102-durable-effect-barriers
feature: sqlite-modal
status: done
depends_on: ["092-sqlite-checkpoints","095-sqlite-task-effects","101-sqlite-runtime-wiring"]
---

# Task 102: Barreiras antes de efeitos externos

**Descrição:** Integrar checkpoint de intenções ao ciclo de provisão, início de execução, mensagem e publicação, incluindo bloqueio da admissão durante falhas e reconciliação de startup. Trocar também os tratamentos de erro Postgres de modal_sandbox.py por erros SQLite sanitizados.

**Critérios de aceitação:**

- [x] Persistir e confirmar intenção antes de criar sandbox/iniciar run/entregar mensagem/autorizar publicação; nenhum efeito novo se checkpoint falhar.
- [x] Startup restaura e reconcilia provider/reservas antes de admissão; reusa identidades diante de resposta perdida.
- [x] Readiness mostra recuperação/falha de persistência; 503 sanitizado; retry não duplica sandbox, execução, mensagem ou PR.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_durable_effects.py`.
- [x] Demo/check operacional: Injetar queda antes/depois de cada efeito e falha de commit; medir chamadas ao provider e verificar identidades reconciliadas.

**Dependências:** [092-sqlite-checkpoints](092-sqlite-checkpoints.md), [095-sqlite-task-effects](095-sqlite-task-effects.md), [101-sqlite-runtime-wiring](101-sqlite-runtime-wiring.md).

**Arquivos prováveis:**

- `backend/gg/runtime/modal_sandbox.py`
- `backend/gg/runtime/task_supervision/manager.py`
- `backend/gg/runtime/scheduler.py`
- `backend/gg/runtime/readiness.py`
- `backend/tests/test_durable_effects.py (novo)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

## Evidência — 2026-10-08

Implementação e limites registrados em
[provas 100–102](evidence/100-102-runtime-verification.md).

Testes focados e QA aprovados; barreiras e recuperação exercitadas com
falhas controladas e tarefa real no Modal. Ver provas para o limite Google/PR/Volume.
