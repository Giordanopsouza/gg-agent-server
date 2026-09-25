---
id: 078-runtime-postgres-migration
feature: mvp-web
status: pending
depends_on: [077-supabase-foundation]
---

# Migrar persistência durável do runtime para Postgres

## Scope

Mover a fonte de verdade do runtime de SQLite para Supabase Postgres antes de abrir o produto a usuários. Preservar o ciclo existente de fila e supervisão, sem adicionar broker ou dois bancos escrevendo o mesmo estado.

## Acceptance criteria

- [ ] Inventariar e migrar tarefas, eventos/mensagens/recibos, resultados/evidências duráveis, reservas, idempotência, publicação e continuação. Preservar IDs, ordenação, timestamps e relações; dados antigos mantêm escopo administrativo explícito.
- [ ] Usar transações/constraints Postgres para admissão, claim, quotas e publicação; testar disputa entre conexões, queda entre etapas e recuperação sem duplicar tarefa, sandbox ou PR.
- [ ] Fornecer importação SQLite → Postgres com dry-run, contagens e integridade referencial; ensaiar backup, pausa de admissões/dispatch, drenagem ou reconciliação de runs e corte sem escritores simultâneos. Migração parcial/repetida não duplica registros.
- [ ] Produção exige Postgres e falha de configuração não cai silenciosamente em SQLite. SQLite permanece só como fonte de importação/fixture legada, removendo caminho operacional após corte. JSON dentro do sandbox pode continuar como estado de execução; não é banco de usuários nem fonte durável do produto.
- [ ] Antes do corte, rollback pode reabrir o SQLite preservado sem novas escritas Postgres. Depois do corte, usar correção progressiva ou migração reversa ensaiada, nunca reabrir cópia antiga e perder dados.
- [ ] Revalidar backup/retenção e recuperação de reservas no Postgres; atualizar runbook e documentação operacional antes de remover a ponte. Implementação deve registrar a substituição das premissas SQLite nos ADRs/instruções vigentes.

## Validation

Rodar contratos do ledger em Postgres real e production-smoke-tests; demo local-stack que cria tarefa, reinicia o runtime e recupera eventos/resultado. Comparar fixture SQLite importada com os registros Postgres. Seguir QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Billing, organizações e alta disponibilidade.

## Log

### [PA] 2026-09-25 — Revisão para produção com Supabase

Plano atualizado por solicitação do usuário: Supabase Auth/Postgres, isolamento e provas no ambiente publicado. Critérios continuam pendentes; esta revisão não implementa nem valida o serviço.
