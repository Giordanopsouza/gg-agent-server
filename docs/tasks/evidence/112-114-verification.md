# Tarefas 112–114 — operações Modal e fixtures SQLite (2026-10-08)

Worktree `091-sqlite-modal`, branch homônima; checkout principal preservado.

## Implementação

- Root delega oito comandos `modal-*` ao backend. Ambiente explícito obrigatório;
  URL e caminho de snapshot exigidos conforme a operação. Runbook:
  [modal-state-operations](../../modal-state-operations.md).
- Todos os comandos mutáveis adquirem um sandbox `state-writer` no App estável
  `gg-runtime-operations`, no ambiente selecionado. Duplicação do nome ativo
  é recusada pelo Modal. A liberação usa `terminate(wait=True)`; não presumir
  que retorno de terminate sem wait significa liberação. Deploy/rollover/stop
  compartilham a mesma lease das operações offline.
- Init/migrate/restore exigem runtime parado e zero containers. Uma Function
  efêmera isolada monta o Volume e usa o módulo instalado; SQLite fica em disco
  local temporário. A Function confirma Volume.commit antes de retornar revisão.
  Não enviar tokens operacionais para o sandbox; um sandbox comum não tem o
  contexto de autenticação necessário para chamar Volume.commit no Volume v1.
- Init gera snapshot inicial e recusa estado existente. Migrate aceita apenas
  snapshots anteriores válidos e conhecidos; restore/startup continuam rejeitando
  versões incompatíveis. Migrate/restore preservam `runtime.previous`.
- Backup ativo é `POST /ops/backup`, exclusivo do operador, pelo coordenador
  existente. Sem segundo escritor. Resposta tem revisão e no-store. Download
  validado, permissão 0600, sem sobrescrever arquivo anterior.
- Deploy/rollover fixam recreate. Health/ready, hash do código, revisão observada
  confirmada e histórico Modal são verificados. Verificação aguarda a revisão
  capturada no primeiro ready válido, sem perseguir escritas posteriores.
  Falha de build não chama stop nem reporta sucesso; teste cobre isso, sob o
  [contrato Modal de deployment](https://modal.com/docs/guide/managing-deployments).
- Autouse cria um arquivo SQLite por caso. new_ledger reabre o mesmo arquivo,
  registra conexões para cleanup e ignora URLs/paths de produção. Reexport antigo
  contém somente exports SQLite, para as tarefas 115–117.
- Cinco consumidores API/SDK usam sqlite_ledger. Ownership usa sessões locais
  opacas e arquivo compartilhado; preservados testes HTTP/WS, idempotência,
  isolamento, concorrência e reabertura. O teste existente de payload expirado
  revelou replay HTTP incorreto: agora retorna a identidade original.
- Antecipados apenas ajustes mínimos de fixture em três consumidores legados
  (modal_sandbox, production_operations, runtime_latency) que passaram a executar
  após remover o skip Postgres. Isso não conclui as tarefas 115/116.

## Testes e builds

- Comando focado 113–114 executado com `env -u GG_RUNTIME_DATABASE_URL`:
  **54 passed**, zero skips, sem serviço externo.
- `test_db_cli.py` + `test_modal_runtime.py`: **27 passed**. Inclui init,
  WAL/restore, versão antiga/futura, commit falho, autenticação de backup,
  recreate, build falho, término efetivo da lease e escritas durante verificação.
- QA root executada em ordem: format-fix, lint-fix, format-check, lint-check,
  pre-commit, unit-tests. Resultado final em ambas as suítes:
  **456 passed, 3 skipped, 2 deselected**. Os três skips são exclusivamente
  test_postgres_ledger_integration, ainda legado e fora de 113–114.
- Builds sdist/wheel dos três pacotes aprovados; frontend **15 passed** e
  build React aprovado. Helper test_support passou Ruff lint/format.
- CLI instalada modal_operations/db_cli --help e make help conferidos.

## Prova operacional real

Reutilizado somente `sqlite-111-proof`, com Volume/Secret previamente provisionados.
Nenhuma alteração de credenciais, produção Railway/Supabase ou import de dados.
URL descoberta anteriormente e confirmada no deploy:
https://giordanowrk-sqlite-111-proof--gg-runtime-runtime.us-east.modal.direct

Task `beec4867-cb8f-4855-8964-fb29f835f485`, execução
`79998aa72a07803786a42781346b3e29`, conversa
`64bfb172-d692-4750-92fe-7b6f7222ea02`, sandbox
`sb-aohd5l2RRxhq7zPXaZyp6t`.

O agente criou `/workspace/modal112-proof.txt` com
`SQLite operations 112 verified`, leu o arquivo e executou um shell check.
Há dez eventos e resposta final que confirma conteúdo/check. Manifest:
agent_outcome=succeeded, evidence_complete=true. check_outcome=not_run indica
que não houve check configurado do produto; o shell check está nos eventos.
Turno terminou idle, como workspace que aceita continuação.

Sequência comprovada no ambiente existente: deploy → tarefa real → migrate
recusado com servidor ativo → backup ativo → stop confirmado → init recusado
sem sobrescrita → restore → migrate → deploy → rollover recreate → replay 200
com mesma identidade, mesmos eventos e mesmo manifest. Backup/restore/migrate
confirmaram revisão **1022**. A inicialização de estado novo é comprovada pelos
casos locais de CLI/remote helper; este ensaio não inicializou outro Volume novo.

Prova final da versão **c0007e06736f9718**: health/ready aprovados; revisão
**1368**, confirmed_revision **1368**. Tentativa simultânea de segunda lease
administrativa retornou AlreadyExistsError. Encerrado apenas o sandbox criado
por esta prova; rollover reconciliou sleeping, **reserved=0, pending=0**,
manifest e dez eventos preservados. Backup final validado: revisão **1370**.
Runtime isolado parado ao final; Volume/Secret e snapshots preservados.

Boundary: comandos instalados → API/runtime com dispatch → Modal/Pi → atividade,
resposta e manifest → Volume confirmado → restauração/recreate/replay. Primeiro
pré-requisito não atendido para repetir pelo frontend público: client/secret Google
não provisionados nesse ambiente, conforme prova 109–111. Não alegar onboarding
Google completo; continua na 123. A orientação local-stack foi usada para exigir
atividade e cumprimento do prompt, além de rótulo de sucesso.

Uma tentativa de criar novo ambiente com upload de credenciais foi rejeitada
pela revisão automática por ausência de autorização explícita para esse destino.
A alternativa concluída reutilizou o ambiente isolado já autorizado/configurado,
sem enviar segredos para um destino novo. Nenhum novo ambiente foi criado.

Evidência bruta privada: `/tmp/gg-112-proof/` (backup inicial/final, logs,
eventos, manifest e resumos); QA em `/tmp/gg-112-*.log`. Não anexar config.json
ou arquivos com credenciais à documentação.
