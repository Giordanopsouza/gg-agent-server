# 126 — ativação e aceite

Destino: ambiente Modal `sqlite-111-proof`, app `gg-runtime`.
URL: https://giordanowrk-sqlite-111-proof--gg-runtime-runtime.us-east.modal.direct.
Versão de código: `c147a4e634914c27`; deployment v1 em 2026-10-08 15:45:45 PDT.

## Executado

- Usuário autorizou explicitamente copiar Google OAuth e GitHub App do `.env`
  local para `gg-runtime-config` neste ambiente e publicar o runtime SQLite.
  Secret configurado com origem Modal e cookies Secure. Valores ficaram fora
  de logs e Git; configuração local privada com permissão 0600.
- Deploy via `gg.runtime.modal_operations`, lease e recreate; health/readiness,
  versão e revisão confirmada passaram. Read-back em 2026-10-09 também passou.
- Google Cloud, projeto `gglabs-504618`, cliente `GGAgent server`: adicionado
  callback Modal `/auth/google/callback`, mantendo callback local existente.
  Console mostrou “OAuth client saved”. Em 2026-10-09 o login real no
  navegador integrado do Codex retornou à interface autenticada do SQLite.
- GitHub App: homepage, callback Modal e webhook `/webhooks/github` atualizados.
  GitHub mostrou “Your GitHub App has been updated”; read-back mostrou os
  três endereços Modal, SSL verification habilitada e wildcard desabilitado.
  Callback local preservado. OAuth retornou `github=connected` e a UI listou
  repositórios autorizados, incluindo repositórios privados.
- Usuário salvou a chave OpenRouter na UI; read-back mostrou chave mascarada.
- Primeira tarefa pela UI: `393187bb-c767-4955-9061-17b4b5e5bd22`, repositório
  privado, branch master. Falhou antes de criar sandbox com `invalid GitHub
  App private key`; reserva liberada, cleanup `confirmed_absent`.
  `GH_PRIVATE_KEY` local não era PEM válido. Usuário autorizou copiar a chave
  existente no Railway para o mesmo Secret Modal. PEM validado e Secret
  corrigido, sem imprimir chave; rollover v2 em 2026-10-09 09:29:06 PDT.
- Task `89e942a9-871e-4484-92ba-955ca61a73bf` executada pela UI no repositório
  privado: prompt cumprido, manifest no_changes, sem commits/PRs,
  evidence_complete=true. Follow-up de recuperação executou comando Python
  de 90 segundos, entregando `338350` e `SQLITE_MODAL_RECREATE_OK` após recreate
  durante running. Sessão e credenciais recuperadas, HTTP/WS com 21 cursores
  únicos correspondentes. Snapshot contendo credenciais e reserva restaurado
  isoladamente. Sandbox de teste encerrado; tarefa sleeping, reserva zero,
  cleanup confirmed_absent. Detalhes e limites estão na evidência 124.
- Histórico antigo descartado conforme autorização na evidência 125.

## Aceite e corte em 2026-10-09

O usuário Giordano aceitou explicitamente a versão apresentada na URL Modal:
“Aceito e autorizo parar os antigos”, em resposta à confirmação que enumerava
login, conexões, repositório privado, execução, recuperação e reserva liberada.
Autorização incluiu parar os dois serviços Railway e preservar Supabase.

`railway down --project ... --environment ... --service ... --yes` executado
para `gg-runtime` e depois `gg-web` nos IDs da evidência 125. Em 09:39–09:40 PDT,
URL antiga respondeu HTTP 404 em GET `/health` e POST `/tasks`.
Modal health `ok`, readiness `ready`, versão `c147a4e634914c27`, dispatch
habilitado/reconciliado, zero reservas e zero pendências. Serviços, Volume
Railway e projeto Supabase preservados; deployments ativos antigos parados.

Depois de dados novos, recuperação usa os checkpoints Modal e suas chaves;
voltar ao banco antigo não é rollback válido. Ver runbook de corte.

O corte operacional e o aceite da tarefa 126 estão concluídos. Isso não fecha
as medições/injeções de falha ainda pendentes em 124 nem afirma um backup
final Postgres em 125. A mudança de escopo do histórico foi autorizada; nenhum
dump antigo foi importado. A remoção do projeto Supabase não foi executada.
