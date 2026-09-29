---
id: 067-pi-owned-pr-publication
feature: mvp-web
status: in-progress
depends_on: [064-user-model-and-credential-dispatch, 066-authorized-repositories-and-task-tokens]
---

# Publicação pelo Pi e reconciliação da PR

## Scope

Permitir que o Pi faça commit/push e abra ou atualize draft PR, enquanto o runtime verifica e reconcilia a publicação.

## Acceptance criteria

- [x] Entregar ao Pi apenas a credencial da tarefa; remover a proibição de GH_TOKEN de forma restrita ao novo fluxo sem encaminhar o token global.
- [x] Pi executa alteração, testes, commit, push e criação/atualização da draft PR com branch e marcador persistentes da tarefa.
- [x] Persistir intenção/identidade e consultar PR existente antes de criar ou após resposta incerta; reinício/timeout não gera publicação duplicada.
- [x] Runtime verifica repository, head, base e URL no GitHub antes de registrar a PR; uma URL no chat não é prova de publicação.
- [x] Ausência de PR solicitada é resultado explícito, sem segunda publicação pelo host; investigação/no_changes pode concluir sem PR.
- [x] Preservar PR criada se o run depois falhar/cancelar; apresentar checks executados, falhos e not_run sem inferir CI verde de completed.
- [x] Adotar draft PR e merge manual; documentar que instrução ao Pi não impede tecnicamente merge com token de escrita.
- [x] Testar timeout depois da criação, reinício, conflito de identidade, no_changes e cancelamento após publicação.

## Validation

Testes de reconciliação com falhas injetadas e demo opt-in em repo descartável com URL verificada da PR criada pelo Pi. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Merge automático, editor de diff e nova infraestrutura genérica de publicação.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.

### [SWE] 2026-09-29 11:00 -03 — Pi publica e o runtime reconcilia

O sandbox entrega ao Pi só o token de instalação da tarefa (`GH_TOKEN`) quando `GG_PI_OWNS_PUBLICATION=1`, e remove o token global. O comando `python -m gg.server.task_supervisor.pi_publication` persiste a identidade, faz commit/push e cria ou atualiza uma draft PR. O runtime consulta o GitHub e não abre outra PR. A instrução de não fazer merge não é barreira de permissão; isso está no prompt e em [ADR 0007](../adr/0007-pi-owned-draft-pr.md). A demo opt-in em repositório real continua fora desta suíte.
