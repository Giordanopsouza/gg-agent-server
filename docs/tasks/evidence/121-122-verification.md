# Provas das tasks 121–122 — 2026-10-08

- Checkout: `.agents/worktrees/091-sqlite-modal`, branch `091-sqlite-modal`.
- `docs/adr/0008-sqlite-modal-google.md` registra SQLite local/WAL, um escritor
  Modal, snapshot completo confirmado por revisão, recuperação antes de
  admissão, Google `sub` associado a UUID local e identidades externas
  persistidas. Os ADRs 0005/0006 preservam o texto histórico e apontam ao
  substituto.
- `README.md`, `AGENTS.md`, `frontend/README.md` e
  `docs/sqlite-modal-operations.md` apontam os comandos existentes:
  `db_cli init`, `make run-runtime` (8001), `make run` (8000),
  `make frontend-dev` com proxy explícito e targets Modal do backend.
- `backend/Makefile` já não contém comandos de Postgres após a task 120;
  nenhum comando adicional precisou ser removido. `make help` passou.
- `make frontend-test`: 15 testes passaram. `make frontend-build`: Vite
  compilou o React (`31` módulos). O sandbox inicial recusou escrita no cache
  `frontend/node_modules/.vite-temp` com `EPERM`; ambos passaram ao repetir
  com acesso de escrita. `git diff --check` passou.
- Demo local com caminhos temporários privados: `python -m gg.runtime.db_cli
  init` criou DB e snapshot; `python -m gg.runtime --host 127.0.0.1 --port
  8001` respondeu `200 {"status":"ok"}` em `/health`. O processo foi parado e
  os arquivos temporários foram removidos.
- Demo do proxy com runtime SQLite e Vite temporários: `/health` direto em
  `127.0.0.1:8001`, `/health` pelo proxy em `127.0.0.1:5173` e `/` do Vite
  responderam HTTP 200. `VITE_DEV_API_PROXY` apontou explicitamente a 8001;
  ambos os processos foram parados ao final.
- O login humano e o despacho por Vite não foram usados como prova desta
  atualização documental. A prova completa publicada pertence à task 123.
- A skill `.agents/skills/local-stack/SKILL.md` foi atualizada **na worktree
  091**. Embora `.agents/` esteja na regra de ignore, esse arquivo já é
  rastreado pelo Git e sua atualização acompanha o commit. Não depende de
  cópia manual no handoff. Nenhuma edição foi feita no checkout principal.
