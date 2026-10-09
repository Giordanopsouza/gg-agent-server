# Corte Supabase/Railway para SQLite/Modal

Destino publicado:
https://giordanowrk-sqlite-111-proof--gg-runtime-runtime.us-east.modal.direct.
Apesar do nome do ambiente de prova, é o destino autorizado pelo usuário
para a ativação atual; não confundir com Modal `main`.

## Ordem de execução

1. Publicar a worktree 091 pelos comandos de `modal-state-operations.md`.
   Conferir versão, readiness, dispatch e revisão confirmada.
2. Registrar callbacks Google e GitHub na origem publicada e webhook GitHub
   em `/webhooks/github`. Conferir read-back. Google permanece External/Testing
   conforme decisão anterior; publicar OAuth não é parte desta execução.
3. Entrar novamente, configurar OpenRouter pessoal e reconectar GitHub.
   Executar tarefa real, verificar eventos HTTP/WS, resposta ao prompt,
   manifest/checks e reserva liberada. Repetir após recreate e restore.
4. Registrar aceite humano da URL e da versão verificadas. O pedido de
   continuar/deploy não substitui aceite de um fluxo efetivamente observado.
5. Bloquear admissões nos serviços antigos identificados na evidência 125;
   verificar bloqueio pelo endpoint e ausência de trabalho ativo.
   A exclusão do histórico não bloqueia novas admissões.
6. Preservar contas/credenciais antigas conforme decisão específica de retenção
   antes de desativar serviços ou excluir o projeto. As etapas de desligamento
   e exclusão são distintas do descarte já autorizado das tarefas antigas.

## Dados e recuperação

O novo produto usa dados SQLite novos. Não importar usuários, sessões, tarefas
ou credenciais Postgres; usuários entram e reconectam contas novamente.
Após a primeira gravação nova, recuperação usa restore/repair dos checkpoints
Modal e código compatível. Voltar ao banco antigo perde dados novos e não é
rollback válido. Guardar chaves do Secret separadamente dos snapshots.

Usar `recreate` e o protocolo de lease de operações da aplicação para manter
um escritor. Medir indisponibilidade e perda de eventos de fundo; não presumir
zero downtime. O comportamento de recreate está descrito em
[Managing deployments](https://modal.com/docs/guide/managing-deployments).

Estado e pendências:
[124](tasks/evidence/124-recovery-and-metrics.md),
[125](tasks/evidence/125-legacy-backup.md),
[126](tasks/evidence/126-cutover-acceptance.md).
