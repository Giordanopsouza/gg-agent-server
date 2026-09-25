---
id: 072-web-continuation-history
feature: mvp-web
status: pending
depends_on: [070-task-chat-and-live-actions, 071-durable-task-continuation]
---

# Continuação e histórico de execuções na UI

## Migration preflight

Ler o [plano do MVP](../mvp-web-plan.md), os ADRs [0001](../adr/0001-modal-background-tasks.md), [0002](../adr/0002-general-background-tasks.md) e [0003](../adr/0003-remove-legacy-learning-surfaces.md), o AGENTS.md do componente e as tasks diretamente dependentes/consumidoras. Registrar estado final, pontes temporárias com legado, responsável pela remoção e teste que protege a fronteira. Consumir o contrato de 071 e manter distintas as ações enviar instrução, retry e continuar; não deduzir vínculos apenas por URL da PR.

## Scope

Permitir pedir ajustes após conclusão e acompanhar execuções vinculadas como uma conversa, preservando a PR original.

## Acceptance criteria

- [ ] Agrupar runs vinculados com seus prompts, estados, resultados e PR; permitir reload e navegação sem perder a execução selecionada.
- [ ] Composer terminal envia novo prompt por continuação e acompanha o novo run; não reenvia automaticamente o prompt anterior.
- [ ] Preservar rascunho e chave idempotente em timeout; refletir conflito de branch ocupada sem disparar outra execução.
- [ ] Tratar PR fechada/mergeada com opção explícita de nova tarefa e explicar limitações de contexto expirado/mudanças não publicadas.
- [ ] Exibir modelo usado por execução, erros recuperáveis e vínculo com a PR original mesmo após falha/cancelamento.
- [ ] Testar ajuste após conclusão, reload, conflito e nova tarefa em desktop/mobile, mantendo foco e composer acessíveis.

## Validation

Testes de UI/API e demo de conversa com dois runs; a prova live da mesma PR é consolidada na 075. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Busca avançada, múltiplas abas de conversa e compartilhamento.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.
