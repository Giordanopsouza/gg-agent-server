# 125 — sistema antigo e decisão de descarte

## Escopo identificado

- Railway project `gg-agent-main-railpack`: `1ed15135-c389-44de-9298-d1672f13b3c8`.
- Environment `production`: `e3fd5d40-3aae-45ac-90d0-7678f6612aeb`.
- `gg-runtime`: `09db0714-b177-4725-a175-287f76460f6f`;
  deployment observado `7e3a2db6-a855-4e7c-9688-3344759a34e7`.
- `gg-web`: `c59e74a5-7f14-4cf4-b4c5-37e9f70a69bb`;
  deployment observado `3079d17c-5746-4f0b-9038-0e3989805084`.
- Supabase `GGAgenteServer`: `xmqpgubedtjirohntdwg`, Postgres 17,
  região us-west-2. Inventário confirmou app_private, runtime_private,
  vault_private e auth. Outros projetos não fazem parte deste corte.

## Mudança autorizada pelo usuário em 2026-10-08

“Pode apagar as tarefas antigas, nao precisamos manter nada.”
Foi explicitado antes da execução que contas, credenciais e dados Modal
seriam preservados. A instrução autoriza descarte do histórico de tarefas;
não é aceite do produto novo nem autorização para apagar o projeto inteiro.

Antes: 23 tarefas (5 failed, 8 completed, 10 sleeping), zero reservas.
Listagem Modal no ambiente antigo `main`: zero sandboxes ativos.
Exclusão em transação com lock e guarda contra novas tarefas ativas/reservas,
removendo dependentes antes das tarefas, sem desabilitar constraints.

Read-back após COMMIT: zero tarefas, reservas, eventos, resultados,
supervisões, sandbox_creations, publication_intents, message_receipts e
retention_tombstones. Preservados: 1 usuário, 1 perfil, 1 credencial
OpenRouter e 1 conexão GitHub. Nenhum dado importado para SQLite.

Não houve backup final desse histórico antes da exclusão autorizada.
Não existe dump final/restauração isolada Postgres comprovada nesta tarefa.
Em 2026-10-09, após aceite humano da versão Modal, o usuário autorizou parar
`gg-runtime` e `gg-web` antigos, preservando Supabase. Executado `railway down`
com project/environment/service IDs explícitos para cada serviço.
Read-back da URL antiga: GET `/health` e POST `/tasks` HTTP 404;
novas admissões por essa origem estão bloqueadas. Modal continua ready,
dispatch reconciliado, zero reservas. Task 125 permanece pendente quanto ao
backup final e restore Postgres; o histórico foi descartado por decisão humana,
e contas/credenciais restantes continuam no projeto Supabase preservado.

Referência consultada:
[Backup e restore Supabase](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore).
Caso contas/credenciais restantes devam ser preservadas antes de desativar
o projeto, o dump deve incluir Auth, roles/grants e chaves de recuperação
separadas; validar restore sem imprimir conteúdo de credenciais.
