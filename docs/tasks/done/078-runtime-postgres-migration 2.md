---
id: 078-runtime-postgres-migration
feature: mvp-web
status: done
depends_on: [077-supabase-foundation]
---

# Migrar persistência durável do runtime para Postgres

## Scope

Mover a fonte de verdade do runtime de SQLite para Supabase Postgres antes de abrir o produto a usuários. Preservar o ciclo existente de fila e supervisão, sem adicionar broker ou dois bancos escrevendo o mesmo estado.

## Acceptance criteria

- [x] Inventariar tarefas, eventos/mensagens/recibos, resultados/evidências duráveis, reservas, idempotência, publicação e continuação no schema Postgres. O usuário dispensou a importação dos dados SQLite anteriores; o arquivo antigo fica offline e não aparece no novo runtime.
- [x] Usar transações/constraints Postgres para admissão, claim, quotas e publicação; testar disputa entre conexões, queda entre etapas e recuperação sem duplicar tarefa, sandbox ou PR.
- [x] Ensaiar backup, pausa de admissões/dispatch, drenagem ou reconciliação de runs e corte sem escritores simultâneos. Não criar importador SQLite.
- [x] Produção exige Postgres e falha de configuração não cai silenciosamente em SQLite. A fixture SQLite foi removida na tarefa 082. JSON dentro do sandbox pode continuar como estado de execução; não é banco de usuários nem fonte durável do produto.
- [x] Antes do corte, rollback pode reabrir o SQLite preservado sem novas escritas Postgres. Depois do corte, usar correção progressiva ou migração reversa ensaiada, nunca reabrir cópia antiga e perder dados.
- [x] Revalidar backup/retenção e recuperação de reservas no Postgres; atualizar runbook e documentação operacional antes de remover a ponte. Implementação deve registrar a substituição das premissas SQLite nos ADRs/instruções vigentes.

## Validation

Rodar contratos do ledger em Postgres real e production-smoke-tests; demo local-stack que cria tarefa, reinicia o runtime e recupera eventos/resultado. Seguir QA do [índice](../README.md#validação-e-conclusão).

## Out of scope

Billing, organizações e alta disponibilidade.

## Log

### [PA] 2026-09-25 — Revisão para produção com Supabase

Plano atualizado por solicitação do usuário: Supabase Auth/Postgres, isolamento e provas no ambiente publicado. Critérios continuam pendentes; esta revisão não implementa nem valida o serviço.

### [PA] 2026-09-27 — Sem importação SQLite

O usuário dispensou o importador SQLite porque o estado antigo não será usado. O corte preserva o arquivo antigo somente como arquivo offline; novos dados passam a existir apenas no Postgres.

### [PA] 2026-09-27 — Implementação e validação local

Schema `runtime_private` cobre tasks, sandbox intents, reservas, publicação, supervisão, eventos, recibos, resultados e tombstones. O app exige `GG_RUNTIME_DATABASE_URL`; os comandos legados de backup SQLite e os demos SQLite foram removidos. Os contratos Postgres local passaram com conexões concorrentes, rollback após queda, reinício, evidências e retenção. As 30 asserções pgTAP de permissões passaram. `make format-fix`, `make lint-fix`, `make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests` e `make -C backend production-smoke-tests` passaram. API local com dispatch desligado criou tarefa, reiniciou e leu evento/resultado persistidos; o resultado foi inserido pelo teste, sem execução Modal. `pg_dump`/`pg_restore` em banco local separado preservou a tarefa de ensaio; banco e registros temporários foram removidos. O projeto Supabase Free exige exportação lógica externa antes do corte, pois não tem backup diário gerenciado. Ainda falta aplicar a migração no projeto publicado e ensaiar o corte com admissões/dispatch pausados.

### [SWE] 2026-09-28 09:19 -03 — Task archived

Usuário confirmou a task como concluída. Entrada movida para `docs/tasks/done/`.
