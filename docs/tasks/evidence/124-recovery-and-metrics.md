# 124 — recuperação: provas e limites

## Verificações em 2026-10-08 e 2026-10-09

Worktree `091-sqlite-modal`; ambiente Modal `sqlite-111-proof`.
URL: https://giordanowrk-sqlite-111-proof--gg-runtime-runtime.us-east.modal.direct.

- 35 testes focados passaram: checkpoints, efeitos duráveis, scheduler recovery,
  operações, ledger, sessões locais e vault OpenRouter.
- Sequência raiz `format-fix`, `lint-fix`, `format-check`, `lint-check`,
  `pre-commit`, `unit-tests` passou; 428 testes unitários, 2 deselected.
  Frontend: 15 testes e build passaram. Alterações de autenticação que já
  estavam na worktree foram preservadas; a formatação não alterou arquivos.
- Usuário autorizou baixar o snapshot privado e validar restore isolado.
  Diretório `/private/tmp/gg-124-recovery-20261008` com modo 0700; snapshot
  0600. `gg.runtime.db_cli.restore` restaurou para `restored.db`, sem editar
  a origem. Validação de integridade: `ok`; zero violações de FK.
- Snapshot: revisão 1376, 282624 bytes, 69 páginas de 4096 bytes.
  SHA-256: `51e1b256018d600da59a1afc59d8c2db0a9526caa5a21d7fb08ae6f4dd8ca4f3`.
  Restore local, uma amostra: 2,722 ms. Contagens: 2 tarefas, 20 eventos,
  2 resultados, zero reservas, sessões, usuários ou credenciais.
  Isso prova restore dos registros presentes; não prova recuperação de
  sessões/credenciais humanas, que não existiam nesse snapshot.
- Deploy autorizado em 2026-10-08 15:45:45 PDT, estratégia `recreate`,
  código `c147a4e634914c27`, deployment v1. Verificação retornou `ready`,
  revisão confirmada 1381, dispatch reconciliado e zero capacidade não resolvida.
- Read-back em 2026-10-09: `/` e `/health` HTTP 200; readiness `ready`,
  revisão e revisão confirmada 32761, mesmo código, sem erro de persistência
  ou scheduler. A chamada `/auth/google/login` deu 404: esse caminho não é
  a rota de login da aplicação; não representa falha do OAuth.

## Ainda necessário para concluir

Em 2026-10-09 o fluxo humano foi exercitado no navegador integrado do Codex:
login Google, chave OpenRouter pessoal, GitHub conectado, repositório privado
`Giordanopsouza/background-sandbox-agents`, branch master. Task
`89e942a9-871e-4484-92ba-955ca61a73bf` entregou commit, contagem de 120 arquivos,
SHA-256 do README, compileall com exit 0 e `SQLITE_MODAL_CUTOVER_OK`.
Manifest: `no_changes`, zero arquivos alterados e `evidence_complete=true`.
`check_outcome=not_run`: a verificação manual do agente não é check configurado.

Rollover após confirmação: tarefa permaneceu idle. Outro rollover iniciou
com estado running confirmado durante um comando Python de 90 segundos;
após reconciliação continuou running e entregou `338350` e
`SQLITE_MODAL_RECREATE_OK`. O mesmo follow-up foi enviado duas vezes com ID
`124-recreate-proof-20261009`: um receipt no snapshot restaurado, uma execução
do comando nos eventos. 21 eventos com cursores únicos; replay WebSocket
corresponde exatamente aos cursores HTTP. Não foi observada perda nessa
sequência; isso não estabelece janela máxima de perda de eventos de fundo.

Snapshot antes do recreate: revisão 33480, 282624 bytes/69 páginas, 1 usuário,
1 sessão, 1 credencial OpenRouter, 1 conexão GitHub, 4 tarefas e 1 reserva;
restore isolado validou integridade. Após recreate: revisão 34023 restaurada
em arquivo novo; receita idempotente única preservada. A UI permaneceu
autenticada após reload e listou repositórios com a credencial restaurada.
Ao encerrar somente o sandbox de teste concluído, scheduler reconciliou
sleeping, zero reservas e cleanup `confirmed_absent`.

Medição real, 10 chamadas sequenciais `POST /ops/backup` autenticadas,
incluindo checkpoint e download: p50 2322,674 ms, p95/máximo 4567,200 ms
(nearest-rank; amostra pequena). Respostas somaram 2826240 bytes. Esse número
é tráfego HTTP de snapshots, não bytes transferidos por Volume.commit.
Confirmação de mensagem e replay: duas amostras, 9123,452 e 7983,794 ms;
amostra insuficiente para uma distribuição representativa de admissão.

Recreate após idle: operação 32,172 s; última amostra ready=200 a 9,037 s,
primeira 503 a 10,139 s, última 503 a 18,879 s, próxima 200 a 19,966 s.
Indisponibilidade amostrada delimitada aproximadamente entre 8,740 e 10,929 s.
Recreate durante running: operação 58,598 s; último 200 a 10,161 s,
primeiro 503 a 11,269 s, último 503 a 24,335 s, próximo 200 a 25,421 s;
intervalo aproximado de 13,066–15,260 s. Polling de cerca de 1 segundo,
com timeout HTTP de 5 s; limites aproximados, não timestamps do servidor.

Inventário posterior: um container `gg-runtime`, app
`ap-urxV7vWTEoWJepxQZBgzlA`. Deploys suportados usam lease e recreate, com
max_containers=1; não houve amostragem contínua dos escritores durante o corte.
Dados brutos privados em `/private/tmp/gg-124-recovery-20261008/`, sem Git.

Os testes locais de falha de commit e escrita concorrente não substituem
injeção real dessas falhas no Modal. Ainda falta instrumentar SQL, tráfego
interno do Volume e janela máxima de perda de eventos.

| Medição em produção | Estado |
| --- | --- |
| Consultas SQL por cenário | Não instrumentado |
| Tráfego efetivo de Volume.commit | Não medido; tamanho de snapshot não é tráfego |
| Confirmação fim a fim p50/p95/máximo | Backup/checkpoint HTTP medido acima; admissão não caracterizada |
| Duração isolada do checkpoint p50/p95/máximo | Não separada do download |
| Janela de perda de eventos de fundo | Não medida |
| Indisponibilidade de recreate e sobreposição de escritores | Readiness medida; sobreposição não amostrada continuamente |

Nenhuma melhora percentual é inferida. Task 124 continua pendente.
