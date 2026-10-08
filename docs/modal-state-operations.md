# Operações SQLite no Modal

Executar da raiz, na worktree dedicada. Usar um ambiente isolado para ensaios.
O Volume é `gg-runtime-state` e o Secret é `gg-runtime-config` no ambiente
selecionado. O Secret precisa das configurações de runtime, origem pública e
credenciais da aplicação; não incluir valores em logs/documentação.

```sh
export MODAL_ENVIRONMENT=sqlite-112-proof
# GG_RUNTIME_API_KEY deve corresponder ao Secret desse ambiente.
make modal-init
make modal-deploy
# Copiar a URL real que deploy imprime; não inventar hostname.
export MODAL_URL=https://URL-DESCOBERTA
make modal-verify
make modal-backup MODAL_SNAPSHOT=/caminho/privado/backup.snapshot
make modal-stop
make modal-restore MODAL_SNAPSHOT=/caminho/privado/backup.snapshot
make modal-migrate
make modal-deploy
make modal-rollover
```

`modal-init` é explícito, cria um Volume ausente e publica o snapshot inicial
antes do primeiro deploy. Recusa snapshot existente; não reinicializa o estado.
`modal-migrate` e `modal-restore` recusam runtime ativo ou containers restantes.
O comando espera a parada efetiva, não só o retorno de `modal app stop`.

Todos os comandos mutáveis adquirem um sandbox nomeado `state-writer` no App
estável `gg-runtime-operations`, no mesmo ambiente. Modal impede nomes de
sandboxes ativos duplicados nesse App. A exclusividade engloba deploy, rollover,
stop e operações offline. A lease é liberada no finally; timeout de 30 minutos
encerra um sandbox abandonado. Não executar comandos crus por fora desse fluxo:
nem locks de arquivo nem o Volume substituem uma trava distribuída. Restringir
credenciais Modal de operação aos responsáveis por esse protocolo.

Init/migrate/restore executam o módulo instalado em uma Function Modal isolada,
sob a lease do sandbox nomeado. A Function tem autorização nativa para
Volume.commit(); nenhum token de operação é enviado ao sandbox.
SQLite ativo fica em `/tmp`, nunca no Volume. Antes de substituir o snapshot
válido, migrate/restore guardam `runtime.previous`; a publicação só é confirmada
após `Volume.commit()`. Restore valida a cópia local e remota. Não importar DB
Postgres ou dados de produção para o ensaio.

Backup ativo chama `POST /ops/backup`, autenticado com `X-API-Key`. O coordenador
existente publica e confirma o snapshot; o cliente valida integridade e revisão
antes de criar o arquivo local com permissão 0600. Recusa sobrescrever backup.
Não abrir um segundo escritor nem usar db_cli backup contra o runtime remoto.

Deploy e rollover fixam `recreate`. Build falho não para a versão atual, conforme
[o contrato de deployments Modal](https://modal.com/docs/guide/managing-deployments).
O comando verifica `/health`, `/ready`, versão do código da imagem e revisão
confirmada, e imprime o histórico Modal para confirmar a versão do deployment.
Falha de health/ready é erro do comando, sem alegar sucesso. Deploy no-op pode
preservar a versão Modal; para recarregar Secret sem mudar código, usar rollover.

A readiness exige dispatch habilitado e reconciliado. Não usar ready=200 como
prova de tarefa completa: verificar atividade, resposta e manifest na demo.

Para conferir argumentos sem acesso cloud:

```sh
uv run --no-editable python -m gg.runtime.modal_operations --help
uv run --no-editable python -m gg.runtime.db_cli --help
make help
```
