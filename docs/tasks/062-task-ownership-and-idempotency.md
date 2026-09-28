---
id: 062-task-ownership-and-idempotency
feature: mvp-web
status: in-progress
depends_on: [061-google-login-and-sessions, 078-runtime-postgres-migration]
---

# Ownership, migração e idempotência por usuário

## Scope

Aplicar identidade do proprietário à admissão e a todas as superfícies de tarefas, preservando o acesso administrativo separado.

## Acceptance criteria

- [x] Preencher owner_id no servidor a partir da identidade Supabase validada; ignorar/rejeitar tentativa do cliente de escolher outro proprietário.
- [x] Migrar tarefas e deduplicação antigas para escopo administrativo explícito; nenhum login recebe automaticamente registros legados.
- [x] Autorizar lista, detalhe, eventos/polling, streams, resultado, mensagem, recibo, cancelamento e retry, inclusive referências indiretas e registros expirados.
- [x] Garantir unicidade de idempotência por proprietário e comparação integral do payload; incluir modelo e continuação quando seus contratos forem introduzidos.
- [x] Reenvio concorrente da mesma chave/payload retorna a mesma tarefa; payload divergente conflita e dois usuários podem usar a mesma chave.
- [x] Manter chave de operador fora dos contratos web e garantir que autenticação administrativa ausente/inválida não seja substituída por sessão web.
- [x] Provar com duas contas que nenhuma leitura ou mutação cruzada revela dados ou altera tarefas; testar também migração e regressão do cliente CLI.

- [x] Usar UUID Supabase para ownership; registros administrativos legados permanecem explicitamente sem proprietário web. Aplicar autorização também no acesso SQL do runtime; credencial privilegiada pode ignorar RLS e não substitui filtros de proprietário. Testar Data API como anon e usuário comum, sem usar service_role como prova de isolamento.

## Validation

Testes HTTP/stream com duas sessões Supabase, Postgres real, migração de banco legado e reenvio concorrente em conexões distintas; executar a verificação de fronteira de imports do SDK. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Organizações, compartilhamento de tarefas e papéis de equipe.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.

### [PA] 2026-09-25 — Revisão para produção com Supabase

Plano atualizado por solicitação do usuário: Supabase Auth/Postgres, isolamento e provas no ambiente publicado. Critérios continuam pendentes; esta revisão não implementa nem valida o serviço.

### [SWE] 2026-09-27 21:53 -03 — Implementação e validação local

Migração 062 adiciona owner_id UUID a tarefas e tombstones, preserva linhas anteriores sem proprietário web e indexa idempotência por proprietário. O runtime deriva UUID da sessão Supabase validada, filtra consultas SQL por proprietário e protege HTTP, polling, WebSocket, mensagens, recibos, cancelamento, resultado e retry. A chave de operador mantém caminho separado; chave inválida não usa cookie como fallback. Testes com duas identidades e conexões Postgres distintas passaram; smoke com duas sessões Auth reais locais confirmou isolamento, mutações cruzadas negadas e Data API fechada para anon e usuário comum. O cliente CLI continua funcionando. `make format-fix`, `make lint-fix`, `make format-check`, `make lint-check`, `make pre-commit` e `make unit-tests` passaram (354 testes, 6 pulados, 2 excluídos). Demo local-stack com dispatch desativado confirmou proxy frontend, admissão 201, leitura de eventos/resultado e 401 sem autenticação. A migração foi aplicada apenas ao Postgres local: a publicação aguarda o corte da 078 e a revisão/aceite da task. O teste pgTAP local teve 34/35 asserções aprovadas; a única falha foi uma permissão preexistente de `gg_runtime` em `vault_private`, fora do escopo desta task.
