# Tasks

Tracker em arquivos (`TRACKER_MODE: file`): **um Markdown por task atômica**, versionado no repositório. O campo `status:` é a fonte de verdade; a pasta indica prioridade/arquivamento.

O plano ativo é o [MVP web — Google, OpenRouter, GitHub e Pi](../mvp-web-plan.md). O fluxo de entrega é **Google → OpenRouter pessoal → GitHub → tarefa → PR pelo Pi → ajuste na mesma PR**. As tasks abaixo estão `pending`; o índice não comprova implementação.

## Próximos passos do MVP

Começar pela **077** (fundação Supabase); depois **061** (Auth) e **078** (runtime Postgres), que podem avançar independentemente. A **062** exige ambas. Antecipar **074** após 061/078 para exercitar o ambiente local e a configuração de produção antes do frontend completo. A tabela está em ordem sugerida; `depends_on` nos arquivos define os bloqueios reais. Após sessão e ownership, o shell web pode avançar enquanto as integrações são construídas; após o cofre, modelo/dispatch e conexão GitHub podem avançar de forma independente. Cada task deve ser revisável e entregável isoladamente; superfícies incompletas ficam indisponíveis ao usuário até seus contratos e autorização estarem prontos.

| Task | Depende de | Prova principal |
|---|---|---|
| [077 — Fundação Supabase](077-supabase-foundation.md) | — | Auth/Postgres local, migrações e permissões reais |
| [078 — Runtime Postgres](078-runtime-postgres-migration.md) | [077](077-supabase-foundation.md) | Importação, concorrência e recuperação sem SQLite em produção |
| [061 — Login Google via Supabase Auth](061-google-login-and-sessions.md) | [077](077-supabase-foundation.md) | Login/logout e rejeição de sessão/callback inválido |
| [062 — Ownership, migração e idempotência por usuário](062-task-ownership-and-idempotency.md) | [061](061-google-login-and-sessions.md), [078](078-runtime-postgres-migration.md) | Duas contas isoladas e migração de dados antigos |
| [063 — Cofre pessoal OpenRouter](063-personal-openrouter-credentials.md) | [061](061-google-login-and-sessions.md) | API de cofre sem segredo em respostas ou banco em texto simples |
| [064 — Modelo e credencial do usuário até o Pi](064-user-model-and-credential-dispatch.md) | [062](062-task-ownership-and-idempotency.md), [063](063-personal-openrouter-credentials.md) | Chave/modelo corretos até sandbox e Pi |
| [065 — Conexão da conta GitHub e instalação da App](065-github-account-and-app-connection.md) | [061](061-google-login-and-sessions.md), [063](063-personal-openrouter-credentials.md) | Conta/instalação verificadas e webhook autenticado |
| [066 — Repositórios autorizados e token restrito da tarefa](066-authorized-repositories-and-task-tokens.md) | [062](062-task-ownership-and-idempotency.md), [065](065-github-account-and-app-connection.md) | Repo privado autorizado; request forjado rejeitado |
| [067 — Publicação pelo Pi e reconciliação da PR](067-pi-owned-pr-publication.md) | [064](064-user-model-and-credential-dispatch.md), [066](066-authorized-repositories-and-task-tokens.md) | PR pelo Pi verificada, sem duplicata após timeout |
| [068 — Shell responsivo, login e navegação](068-responsive-web-shell-and-login.md) | [062](062-task-ownership-and-idempotency.md) | Login e histórico acessíveis em quatro larguras |
| [069 — Onboarding e criação de tarefa pelo navegador](069-web-onboarding-and-task-creation.md) | [064](064-user-model-and-credential-dispatch.md), [066](066-authorized-repositories-and-task-tokens.md), [068](068-responsive-web-shell-and-login.md) | Onboarding e envio idempotente pelo navegador |
| [070 — Conversa, atividade e ações da tarefa](070-task-chat-and-live-actions.md) | [067](067-pi-owned-pr-publication.md), [069](069-web-onboarding-and-task-creation.md) | Mensagem, recibo, cancelamento e reload |
| [071 — Continuação durável na mesma branch e PR](071-durable-task-continuation.md) | [067](067-pi-owned-pr-publication.md) | Novo run na mesma PR sem concorrência na branch |
| [072 — Continuação e histórico de execuções na UI](072-web-continuation-history.md) | [070](070-task-chat-and-live-actions.md), [071](071-durable-task-continuation.md) | Pedido de ajuste e histórico agrupado na UI |
| [073 — Limites por usuário e proteção de capacidade](073-per-user-runtime-limits.md) | [062](062-task-ownership-and-idempotency.md), [071](071-durable-task-continuation.md) | Quota por usuário e teto global preservados |
| [074 — Configuração de produção do MVP web](074-web-production-configuration.md) | [061](061-google-login-and-sessions.md), [078](078-runtime-postgres-migration.md) | Web/API na mesma origem e smoke operacional |
| [075 — Aceite ponta a ponta do MVP web](075-mvp-web-end-to-end-acceptance.md) | [074](074-web-production-configuration.md), [065](065-github-account-and-app-connection.md), [072](072-web-continuation-history.md), [073](073-per-user-runtime-limits.md) | Demo live, evidências de aceite e limpeza |

## Relação com os incrementos do plano

| Incremento | Tasks |
|---|---|
| 0. Fundação e migração Postgres | 077–078; ambiente local e configuração de produção na 074 |
| 1. Supabase Auth, sessão e ownership | 061–062 |
| 2. OpenRouter pessoal e modelo | 063–064 |
| 3. GitHub App e seleção de repo/branch | 065–066; interface em 069 |
| 4. Pi publica e runtime reconcilia | 067 |
| 5. Shell, onboarding e conversa responsivos | 068–070 |
| 6. Continuação e fechamento | 071–075 |

Manter React/Vite, FastAPI e execução existente; Supabase Auth administra identidade/sessões e Supabase Postgres substitui SQLite como persistência de produção; `gg.sdk` nunca importa `gg.server`, e `gg.runtime` acessa o servidor do sandbox por contrato HTTP. A tarefa geral sem repositório continua válida. O fluxo web usa credenciais pessoais e autorização por proprietário; o acesso de CLI/operador permanece separado. Não recuperar superfícies legadas removidas pelo ADR 0003.

A publicação pelo Pi e o acesso por usuário mudam premissas dos ADRs anteriores. As tasks afetadas seguem o plano vigente, sem tratar o comportamento legado como requisito do MVP.

## Dependências externas e limite do aceite

Configurar Supabase local e o projeto de produção existente, Google via Supabase Auth com domínio/callback, GitHub App com callback/webhook/permissões, chave de criptografia fora do banco, HTTPS, runtime Modal e repo de teste autorizado. O usuário dispensou um projeto staging separado após o limite de projetos gratuitos impedir sua criação; fixtures sintéticas ficam restritas ao ambiente local. Implementação e testes controlados podem avançar antes disso; a task 075 só termina com a demonstração real e limpeza comprovada.

O plano menciona a antiga **060 — aceitação de dez sandboxes**, mas seu arquivo está ausente no estado atual do workspace. O número permanece reservado; não recriar nem marcar como concluída. Capacidade de dez execuções simultâneas **não está comprovada** e não é um bloqueio artificial para iniciar o MVP. A 073 protege os limites configurados; a 075 comprova apenas a capacidade efetivamente exercitada.

Automações, memória, organizações, billing, ambientes avançados, terminal, previews e editor de diff ficam fora deste ciclo, conforme a seção “Depois do MVP” do plano.

## Pastas e numeração

- `tasks/*.md`: plano ativo, mais este índice.
- `tasks/backlog/*.md`: trabalho válido fora do plano atual; mover para a raiz ao priorizar.
- `tasks/done/*.md`: histórico concluído.

Formato: `<NNN>-<slug>.md`, com contador monotônico de três dígitos, sem reutilizar ids históricos/removidos. O id **076** está reservado à revisão deste planejamento (worktree 076-supabase-mvp-plan); implementação nova usa 077–078. Próximo id: **079**. Links de dependências usam ids completos em `depends_on`, mesmo quando os arquivos forem arquivados. Ao mover arquivos, corrigir links Markdown relativos dos índices afetados.

## Formato de uma task

```markdown
---
id: 079-example
feature: mvp-web
status: pending
depends_on: []
---

# Título

## Scope
Uma unidade pequena, concreta e independentemente entregável.

## Acceptance criteria
- [ ] Comportamento verificável da superfície real.

## Validation
Teste automatizado ou demo executável, com comando e evidência esperada.

## Out of scope
Trabalho explicitamente adiado.

## Log
### [PA] YYYY-MM-DD HH:MM TZ — Grooming
Escopo e dependências definidos.
```

## Validação e conclusão

Cada implementação termina em teste automatizado ou demo executável da superfície real. A matriz final de aceite é consolidada na 075; isso não adia os testes de cada incremento.

Seguir o AGENTS.md: `make format-fix`, `make lint-fix`, `make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests`, nessa ordem. Adicionar testes/build web quando houver mudança web e `make -C backend production-smoke-tests` para mudanças operacionais. A 068 integra comandos web ao Makefile raiz; a 075 integra a demo. Fora de targets Makefile, usar `uv run --no-editable ...`.

Aplicar a [matriz de testes para produção](../mvp-production-tests.md). Testes de persistência/autorização usam Supabase/Postgres real local; SQLite não prova comportamento de produção. Testes comuns não provisionam recursos pagos. Demos reais exigem opt-in e registram configuração, resultado e limpeza, sem segredos. Mock não comprova Google/GitHub/OpenRouter/Modal reais.

## Ciclo de vida

- **PA** cria a task com `status: pending`.
- **SWE** inicia e muda para `status: in-progress`.
- Após **Tester** aprovar e a task ser commitada, mudar para `status: done`; arquivar em `done/` quando sair do plano ativo.

Seguir uma task/branch/PR por incremento. A entrega do MVP só está pronta quando o fluxo completo passa, mesmo que PRs preparatórias já estejam integradas.

Cada agente **acrescenta**, sem reescrever o histórico, uma entrada em `## Log`: `### [ROLE] YYYY-MM-DD HH:MM TZ — assunto`. Papéis: `PA`, `SWE`, `Tester`, `PR Reviewer`, `On-Call`.
