---
id: 070-task-chat-and-live-actions
feature: mvp-web
status: pending
depends_on: [067-pi-owned-pr-publication, 069-web-onboarding-and-task-creation]
---

# Conversa, atividade e ações da tarefa

## Scope

Tornar a tela da tarefa uma conversa operacional com progresso durável, mensagens durante execução e cancelamento.

## Acceptance criteria

- [ ] Renderizar mensagens Markdown/código com conteúdo não confiável tratado com segurança, ferramentas recolhíveis, estados e erros recuperáveis.
- [ ] Reconectar por cursor, deduplicar eventos e recuperar histórico/progresso após reload; reduzir/parar polling de terminais preservando consulta de resultado/recibos pendentes.
- [ ] Enviar instrução ao Pi em execução e distinguir accepted, delivered_to_pi, failed e unknown; aceite HTTP não significa entrega ao agente.
- [ ] Cancelar tarefa e mostrar avanço da limpeza sem declarar sandbox encerrado antes da confirmação; lidar com corrida para estado terminal.
- [ ] Mostrar branch, URL verificada da PR, resumo de alterações e checks disponíveis; distinguir falha, no_changes, not_run e evidência incompleta.
- [ ] Expor retry como repetição do prompt em nova tarefa, sem chamá-lo de continuação; preservar vínculos retornados pelo backend.
- [ ] Provar criar/acompanhar/enviar instrução/cancelar/recarregar no desktop e mobile, incluindo erro de boot, clone e agente.

## Validation

Testes de interação com replay de eventos/recibos e demo local do fluxo HTTP; build web e QA de teclado/foco. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

WebSocket novo, terminal, canvas, editor de diff e ações de continuação (072).

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.
