---
id: 124-modal-recovery-measurements
feature: sqlite-modal
status: pending
depends_on: ["123-modal-public-onboarding"]
---

# Task 124: Recuperação e medições no Modal

**Descrição:** Exercitar falhas reais de restart/checkpoint e registrar consultas, bytes e latência fim a fim da confirmação, sem presumir melhora percentual.

**Critérios de aceitação:**

- [ ] Após restart/restauração, tarefa confirmada, sessão/credenciais e reservas recuperam; repetir tarefa completa com dispatch habilitado.
- [ ] Falha de commit dá 503 e suspende efeitos; escrita durante checkpoint persiste no próximo; requests replay não duplicam efeitos.
- [ ] Registrar cenário/tamanho DB/páginas, consultas, tráfego, checkpoint e latências p50/p95/máximo; incluir janela de perda de eventos de fundo e indisponibilidade de recreate.

**Verificação:**

- [ ] Teste/comando focado: `make format-fix → make lint-fix → make format-check → make lint-check → make pre-commit → make unit-tests; make frontend-test; make frontend-build`.
- [ ] Demo/check operacional: Recreate durante tarefa e após confirmação; verificar snapshot por restore isolado e zero sobreposição de escritores. Se faltar pré-requisito, registrar primeiro bloqueio e boundary exato.

**Dependências:** [123-modal-public-onboarding](123-modal-public-onboarding.md).

**Arquivos prováveis:**

- `backend/tests/test_production_operations.py`
- `backend/tests/test_checkpoints.py`
- `tasks/evidence/124-recovery-and-metrics.md (novo)`
- `docs/sqlite-modal-operations.md`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.
