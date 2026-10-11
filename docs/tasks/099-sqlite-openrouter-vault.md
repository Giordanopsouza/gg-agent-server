---
id: 099-sqlite-openrouter-vault
feature: sqlite-modal
status: done
depends_on: ["097-sqlite-local-sessions","098-google-direct-oidc"]
---

# Task 099: Cofre OpenRouter SQLite

**Descrição:** Mover credenciais OpenRouter para o banco central SQLite, preservando Fernet, versões e entrega da credencial correta à tarefa.

**Critérios de aceitação:**

- [x] Ciphertext, mask e versões mantêm o contrato; rotação/remover/reconectar não reutiliza versão.
- [x] Consultas/mutações limitadas ao usuário autenticado; respostas e logs não contêm chave ou ciphertext.
- [x] Salvar/remover só confirma após checkpoint; falha gera 503; chave de cifra vem do Secret, nunca do snapshot.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_sqlite_openrouter_vault.py backend/tests/test_model_credential_dispatch.py`.
- [x] Demo/check operacional: Usar duas contas com chaves distintas, reiniciar e verificar despacho da versão correspondente sem imprimir segredos.
- [x] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [097-sqlite-local-sessions](097-sqlite-local-sessions.md), [098-google-direct-oidc](098-google-direct-oidc.md).

**Arquivos prováveis:**

- `backend/gg/runtime/openrouter_vault.py`
- `backend/gg/runtime/sqlite_migrations.py`
- `backend/tests/test_model_credential_dispatch.py`
- `backend/tests/test_sqlite_openrouter_vault.py (novo)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.

## Evidência — 2026-10-08

- `SQLiteOpenRouterVault` mantém as interfaces sync `status/resolve/replace/remove`; migração 7 guarda ciphertext Fernet, mask e contador por UUID local. Chave Fernet é argumento externo ao banco/snapshot, destinado ao Secret no wiring posterior.
- Rotas aguardam `ensure_durable()` após operação; 503 não confirma sucesso. Retry de salvar/remover pode avançar novamente o contador e nunca reutiliza versões. Consumidores diretos da interface sync precisam chamar a barreira antes de confirmar uma mutação; integração das demais barreiras fica em 101/102.
- Dois testes novos comprovam versões 1→5, duas contas via HTTP, respostas sem segredo, erros de checkpoint, restore com a chave externa e execução de `ModalSandboxLifecycle.create` recebendo somente a chave/versão do owner. Provider Modal é simulado; não há criação de sandbox remoto.
- Arquivos de implementação/teste: `openrouter_vault.py`, `sqlite_migrations.py`, `test_sqlite_openrouter_vault.py` (3). Quatro testes existentes de despacho também passaram.
- Grupo 097–099: 30 testes novos aprovados. QA executado em ordem: `make format-fix`, `make lint-fix`, `make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests`; resultado amplo **314 passed, 92 skipped, 2 deselected**. Skips legados dependem de Postgres ausente; não são prova de compatibilidade completa com o backend antigo.
- `make build` aprovou sdist/wheel de gg-sdk, gg-backend e gg-sandbox; `git diff --check` limpo. Instalação não editável foi reconstruída antes do QA para incorporar módulos novos.
- Limite da prova: candidato SQLite e HTTP in-process com transportes controlados, snapshots locais e fronteira de despacho simulada. Sem login Google humano, Volume real ou tarefa frontend→runtime→Modal. Primeiro pré-requisito ausente para esse E2E é o wiring SQLite da 101, que depende também da conexão GitHub SQLite da 100. A skill local-stack foi consultada; o app publicado continua usando o wiring antigo. A autorização condicional para 101 fica registrada, mas não foi necessário antecipá-la para comprovar estas três fatias.
