---
id: 075-mvp-web-end-to-end-acceptance
feature: mvp-web
status: pending
depends_on: [074-web-production-configuration, 065-github-account-and-app-connection, 072-web-continuation-history, 073-per-user-runtime-limits]
---

# Aceite ponta a ponta do MVP web

## Scope

Consolidar a entrega com demo opt-in real e evidência rastreável de todos os critérios de aceite do plano.

## Acceptance criteria

- [ ] Integrar ao Makefile raiz um comando documentado da demo, com opt-in explícito, pré-requisitos, repo descartável, limites e limpeza mesmo em falha.
- [ ] Demonstrar na URL HTTPS publicada, em navegador limpo e a partir de rede externa, Google via Supabase → OpenRouter → GitHub → repo/branch/modelo → prompt → atividade → draft PR verificada → novo prompt na mesma PR após sandbox encerrado.
- [ ] Usar duas contas para comprovar isolamento e credenciais/modelos corretos; registrar idempotência, mensagem com recibo, cancelamento, reload e erros recuperáveis.
- [ ] Cobrir checks executados/falhos/not_run, no_changes, PR preservada em falha e conflitos de continuação; separar evidência automatizada e live.
- [ ] Exercitar 360, 390, 768 e 1440px com teclado/foco, histórico e composer acessíveis; anexar evidência sem segredos.
- [ ] Varrer URL, localStorage, logs públicos, transcript, API e build por segredos de teste; nunca incluir credenciais reais na evidência.
- [ ] Registrar URL da PR, ids dos runs, modelo, ambiente, data e confirmação de limpeza dos sandboxes; recursos pagos não rodam na suíte padrão.
- [ ] Executar QA na ordem do AGENTS.md, testes/build web e production-smoke-tests; manter checklist do plano atualizado e não declarar entrega pronta com validação real pendente.

- [ ] Executar a matriz de [testes para produção](../mvp-production-tests.md): CI rápido, integração Supabase/Postgres local, browser na URL HTTPS publicada com contas autorizadas e smoke pós-deploy. Falha crítica bloqueia abertura do produto; pendência live não vira aceite por mock.
- [ ] Provar persistência após redeploy sem volume SQLite, isolamento entre duas contas, migração/restore ensaiados e falhas de Auth/banco com comportamento seguro. Registrar build/commit, versão de schema, URL e resultados sanitizados.
- [ ] Verificar o conteúdo da PR e os testes executados pelo Pi contra o prompt. Status succeeded, HTTP 200 e existência de uma PR isoladamente não comprovam atendimento.

## Validation

Demo real opt-in e matriz critério → teste/evidência, com comandos/resultados reproduzíveis e dependências externas pendentes identificadas. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Dez sandboxes simultâneos como requisito implícito, funcionalidades pós-MVP e merge/deploy automático da entrega.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.

### [PA] 2026-09-25 — Revisão para produção com Supabase

Plano atualizado por solicitação do usuário: Supabase Auth/Postgres, isolamento e provas no ambiente publicado. Critérios continuam pendentes; esta revisão não implementa nem valida o serviço.
