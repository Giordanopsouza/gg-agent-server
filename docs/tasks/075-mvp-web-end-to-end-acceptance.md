---
id: 075-mvp-web-end-to-end-acceptance
feature: mvp-web
status: pending
depends_on: [074-web-production-configuration]
---

# Aceite ponta a ponta do MVP web

## Migration preflight

Ler o [plano do MVP](../mvp-web-plan.md), os ADRs [0001](../adr/0001-modal-background-tasks.md), [0002](../adr/0002-general-background-tasks.md) e [0003](../adr/0003-remove-legacy-learning-surfaces.md), o AGENTS.md do componente e as tasks diretamente dependentes/consumidoras. Registrar estado final, pontes temporárias com legado, responsável pela remoção e teste que protege a fronteira. Revisar tasks 061–074, plano do MVP e runbook. Mocks servem aos testes comuns; não registrar login, execução paga ou PR real como validados sem prova externa.

## Scope

Consolidar a entrega com demo opt-in real e evidência rastreável de todos os critérios de aceite do plano.

## Acceptance criteria

- [ ] Integrar ao Makefile raiz um comando documentado da demo, com opt-in explícito, pré-requisitos, repo descartável, limites e limpeza mesmo em falha.
- [ ] Demonstrar Google → OpenRouter → GitHub → repo/branch/modelo → prompt → atividade → draft PR verificada → novo prompt na mesma PR após sandbox encerrado.
- [ ] Usar duas contas para comprovar isolamento e credenciais/modelos corretos; registrar idempotência, mensagem com recibo, cancelamento, reload e erros recuperáveis.
- [ ] Cobrir checks executados/falhos/not_run, no_changes, PR preservada em falha e conflitos de continuação; separar evidência automatizada e live.
- [ ] Exercitar 360, 390, 768 e 1440px com teclado/foco, histórico e composer acessíveis; anexar evidência sem segredos.
- [ ] Varrer URL, localStorage, logs públicos, transcript, API e build por segredos de teste; nunca incluir credenciais reais na evidência.
- [ ] Registrar URL da PR, ids dos runs, modelo, ambiente, data e confirmação de limpeza dos sandboxes; recursos pagos não rodam na suíte padrão.
- [ ] Executar QA na ordem do AGENTS.md, testes/build web e production-smoke-tests; manter checklist do plano atualizado e não declarar entrega pronta com validação real pendente.

## Validation

Demo real opt-in e matriz critério → teste/evidência, com comandos/resultados reproduzíveis e dependências externas pendentes identificadas. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Dez sandboxes simultâneos como requisito implícito, funcionalidades pós-MVP e merge/deploy automático da entrega.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.
