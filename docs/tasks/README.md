# Tasks

Tracker em arquivos (`TRACKER_MODE: file`): **um Markdown por task atômica**, versionado no repositório. O campo `status:` é a fonte de verdade; a pasta indica prioridade/arquivamento.

## Pastas e numeração

- `docs/tasks/*.md`: tasks ainda no índice ativo.
- `docs/tasks/backlog/*.md`: trabalho válido fora do ciclo atual; mover para a raiz ao priorizar.
- `docs/tasks/done/*.md`: histórico concluído.
- `docs/tasks/evidence/`: provas das tasks.

Formato: `<NNN>-<slug>.md`, com contador monotônico de três dígitos, sem reutilizar ids já usados. O maior id presente é **128**. Links de dependências usam ids completos em `depends_on`, mesmo quando os arquivos forem arquivados.

## Formato de uma task

```markdown
---
id: 131-example
feature: sqlite-modal
status: pending
depends_on: []
---

# Título

## Scope
Uma unidade pequena, concreta e independentemente entregável.

## Acceptance criteria
- [ ] Comportamento verificável da superfície real.

## Validation
Teste automatizado ou demo executável, com comando e evidência esperada.

## Out of scope
Trabalho explicitamente adiado.

## Log
### [PA] YYYY-MM-DD HH:MM TZ — Grooming
Escopo e dependências definidos.
```

## Validação e conclusão

Cada implementação termina em teste automatizado ou demo executável da superfície real.

Seguir o AGENTS.md: `make format-fix`, `make lint-fix`, `make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests`, nessa ordem. Adicionar testes/build web quando houver mudança web. Fora de targets Makefile, usar `uv run --no-editable ...`.

Testes de persistência usam SQLite. Demos reais exigem opt-in e registram configuração, resultado e limpeza, sem segredos. Mock não comprova Google/GitHub/OpenRouter/Modal reais.

## Ciclo de vida

- **PA** cria a task com `status: pending`.
- **SWE** inicia e muda para `status: in-progress`.
- Após **Tester** aprovar e a task ser commitada, mudar para `status: done`; arquivar em `done/` quando sair do plano ativo.

Seguir uma task/branch/PR por incremento.

Cada agente **acrescenta**, sem reescrever o histórico, uma entrada em `## Log`: `### [ROLE] YYYY-MM-DD HH:MM TZ — assunto`. Papéis: `PA`, `SWE`, `Tester`, `PR Reviewer`, `On-Call`.
