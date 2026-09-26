---
id: 067-pi-owned-pr-publication
feature: mvp-web
status: pending
depends_on: [064-user-model-and-credential-dispatch, 066-authorized-repositories-and-task-tokens]
---

# Publicação pelo Pi e reconciliação da PR

## Scope

Permitir que o Pi faça commit/push e abra ou atualize draft PR, enquanto o runtime verifica e reconcilia a publicação.

## Acceptance criteria

- [ ] Entregar ao Pi apenas a credencial da tarefa; remover a proibição de GH_TOKEN de forma restrita ao novo fluxo sem encaminhar o token global.
- [ ] Pi executa alteração, testes, commit, push e criação/atualização da draft PR com branch e marcador persistentes da tarefa.
- [ ] Persistir intenção/identidade e consultar PR existente antes de criar ou após resposta incerta; reinício/timeout não gera publicação duplicada.
- [ ] Runtime verifica repository, head, base e URL no GitHub antes de registrar a PR; uma URL no chat não é prova de publicação.
- [ ] Ausência de PR solicitada é resultado explícito, sem segunda publicação pelo host; investigação/no_changes pode concluir sem PR.
- [ ] Preservar PR criada se o run depois falhar/cancelar; apresentar checks executados, falhos e not_run sem inferir CI verde de completed.
- [ ] Adotar draft PR e merge manual; documentar que instrução ao Pi não impede tecnicamente merge com token de escrita.
- [ ] Testar timeout depois da criação, reinício, conflito de identidade, no_changes e cancelamento após publicação.

## Validation

Testes de reconciliação com falhas injetadas e demo opt-in em repo descartável com URL verificada da PR criada pelo Pi. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Merge automático, editor de diff e nova infraestrutura genérica de publicação.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.
