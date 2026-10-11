---
id: 111-modal-runtime-server
feature: sqlite-modal
status: done
depends_on: ["092-sqlite-checkpoints","093-sqlite-recovery-cli","102-durable-effect-barriers","108-sandbox-sqlite-live-demo","109-fastapi-react-serving","110-remove-node-production-proxy"]
---

# Task 111: Servidor único no Modal

**Descrição:** Criar app gg-runtime usando Modal Server com Uvicorn único, build React na imagem, Volume de snapshots e Secret separados.

**Critérios de aceitação:**

- [x] min_containers=1/max_containers=1, um worker, sem reload/autoscaling extra; público no proxy Modal e autenticado pela aplicação.
- [x] Restaurar snapshot validado ao disco local antes de servir/admitir; checkpoints de fundo a cada dois segundos quando dirty, via lifespan.
- [x] Volume gg-runtime-state e Secret gg-runtime-config; graceful shutdown drena efeitos e tenta checkpoint final; deploy recreate validado sem dois escritores.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_modal_runtime.py`.
- [x] Demo/check operacional: Deploy em ambiente isolado, descobrir URL real, inspecionar worker/container e reiniciar com snapshot confirmado.
- [x] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [092-sqlite-checkpoints](092-sqlite-checkpoints.md), [093-sqlite-recovery-cli](093-sqlite-recovery-cli.md), [102-durable-effect-barriers](102-durable-effect-barriers.md), [108-sandbox-sqlite-live-demo](108-sandbox-sqlite-live-demo.md), [109-fastapi-react-serving](109-fastapi-react-serving.md), [110-remove-node-production-proxy](110-remove-node-production-proxy.md).

**Arquivos prováveis:**

- `backend/gg/runtime/modal_runtime.py (novo)`
- `backend/gg/runtime/runtime_image.py (novo)`
- `backend/gg/runtime/__main__.py`
- `backend/gg/runtime/app.py`
- `backend/tests/test_modal_runtime.py (novo)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.

## Evidência de conclusão

Implementação, QA, demos reais, restore/recreate e limites documentados em
[109–111: verificação](evidence/109-111-verification.md). Onboarding público
Google permanece no escopo da 123; nenhum corte de produção realizado.
