# Corte Supabase/Railway para SQLite/Modal

Destino publicado:
https://giordanowrk-sqlite-111-proof--gg-runtime-runtime.us-east.modal.direct.
Apesar do nome do ambiente de prova, é o destino autorizado pelo usuário
para a ativação atual; não confundir com Modal `main`.

O corte já foi aceito. Recuperação usa os checkpoints Modal e as chaves do
Secret. Voltar ao banco antigo não é rollback.

Em 2026-10-12 o usuário autorizou apagar o que não é mais usado:

- Projeto Supabase `GGAgenteServer` (`xmqpgubedtjirohntdwg`) excluído.
- Projetos Railway `gg-agent-main-railpack`
  (`1ed15135-c389-44de-9298-d1672f13b3c8`) e `gg-agent-server`
  (`9546078e-3ae0-4c9e-99d2-000e005de338`) excluídos, inclusive o runtime
  que ainda estava em execução em `gg-runtime-production.up.railway.app`.
- Não foram alterados os projetos Railway `empowering-art` e
  `fulfilling-enthusiasm`, nem o projeto Supabase `wpp-agent`.

## Dados e recuperação

O produto usa dados SQLite novos. Não importar usuários, sessões, tarefas
ou credenciais do Postgres antigo. Após a primeira gravação nova, recuperação
usa restore/repair dos checkpoints Modal e código compatível. Guardar chaves
do Secret separadamente dos snapshots.

Usar `recreate` e o protocolo de lease de operações da aplicação para manter
um escritor. O comportamento de recreate está descrito em
[Managing deployments](https://modal.com/docs/guide/managing-deployments).

Estado do corte:
[124](tasks/evidence/124-recovery-and-metrics.md),
[125](tasks/evidence/125-legacy-backup.md),
[126](tasks/evidence/126-cutover-acceptance.md).
