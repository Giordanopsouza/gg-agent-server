---
id: 062-task-ownership-and-idempotency
feature: mvp-web
status: pending
depends_on: [061-google-login-and-sessions, 078-runtime-postgres-migration]
---

# Ownership, migração e idempotência por usuário

## Scope

Aplicar identidade do proprietário à admissão e a todas as superfícies de tarefas, preservando o acesso administrativo separado.

## Acceptance criteria

- [ ] Preencher owner_id no servidor a partir da identidade Supabase validada; ignorar/rejeitar tentativa do cliente de escolher outro proprietário.
- [ ] Migrar tarefas e deduplicação antigas para escopo administrativo explícito; nenhum login recebe automaticamente registros legados.
- [ ] Autorizar lista, detalhe, eventos/polling, streams, resultado, mensagem, recibo, cancelamento e retry, inclusive referências indiretas e registros expirados.
- [ ] Garantir unicidade de idempotência por proprietário e comparação integral do payload; incluir modelo e continuação quando seus contratos forem introduzidos.
- [ ] Reenvio concorrente da mesma chave/payload retorna a mesma tarefa; payload divergente conflita e dois usuários podem usar a mesma chave.
- [ ] Manter chave de operador fora dos contratos web e garantir que autenticação administrativa ausente/inválida não seja substituída por sessão web.
- [ ] Provar com duas contas que nenhuma leitura ou mutação cruzada revela dados ou altera tarefas; testar também migração e regressão do cliente CLI.

- [ ] Usar UUID Supabase para ownership; registros administrativos legados permanecem explicitamente sem proprietário web. Aplicar autorização também no acesso SQL do runtime; credencial privilegiada pode ignorar RLS e não substitui filtros de proprietário. Testar Data API como anon e usuário comum, sem usar service_role como prova de isolamento.

## Validation

Testes HTTP/stream com duas sessões Supabase, Postgres real, migração de banco legado e reenvio concorrente em conexões distintas; executar a verificação de fronteira de imports do SDK. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Organizações, compartilhamento de tarefas e papéis de equipe.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.

### [PA] 2026-09-25 — Revisão para produção com Supabase

Plano atualizado por solicitação do usuário: Supabase Auth/Postgres, isolamento e provas no ambiente publicado. Critérios continuam pendentes; esta revisão não implementa nem valida o serviço.
