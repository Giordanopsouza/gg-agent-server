---
id: 061-google-login-and-sessions
feature: mvp-web
status: in-progress
depends_on: [077-supabase-foundation]
---

# Login Google via Supabase Auth e sessão web

## Scope

Usar Supabase Auth como autoridade de identidade e sessão, com Google como provedor. O FastAPI intermedeia login e sessão para o React/Vite; não implementar um provedor OIDC próprio.

## Acceptance criteria

- [ ] Usar o fluxo Google do Supabase Auth com PKCE e callback vinculado ao navegador; validar state/retorno conforme o fluxo escolhido. Identificar o usuário por auth.users.id (sub do JWT Supabase), nunca por email ou user_metadata.
- [ ] Manter identidades e sessões no Supabase Auth; perfil da aplicação no Postgres vinculado ao UUID de auth.users. Não duplicar senhas ou implementar tabela própria como autoridade de login. FastAPI mantém tokens em cookies HttpOnly/Secure ou armazenamento privado cifrado, nunca localStorage.
- [ ] Disponibilizar início/callback de login, consulta da sessão e logout; tratar cancelamento, callback inválido e sessão expirada sem expor tokens.
- [ ] Usar cookie HttpOnly, Secure em produção e SameSite explícito; proteger mutações por CSRF/Origin e restringir redirecionamentos de retorno.
- [ ] Manter as rotas de tarefas fechadas à sessão web até a autorização por proprietário da task 062; login sozinho não habilita acesso global.
- [ ] Testar callback válido/repetido/forjado, UUID estável, expiração, refresh concorrente, logout, conta desativada e origem indevida pelo app HTTP. Validar assinatura, issuer, audience e expiração dos JWTs recebidos; não confiar apenas em decodificação ou getSession.

- [ ] Documentar logout/revogação: limpar cookies e revogar refresh; JWT já emitido pode continuar válido até expirar. Ações sensíveis verificam sessão ativa e conta habilitada no servidor; provar rejeição após revogação, sem prometer invalidação imediata só por apagar usuário.

## Validation

Testes HTTP determinísticos mais integração com Supabase Auth local e login/logout Google real no staging HTTPS; incluir reload e refresh. Evidência com mocks não comprova OAuth real. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Tela de login (068), ownership (062), outros provedores de identidade.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.

### [PA] 2026-09-25 — Revisão para produção com Supabase

Plano atualizado por solicitação do usuário: Supabase Auth/Postgres, isolamento e provas no ambiente publicado. Critérios continuam pendentes; esta revisão não implementa nem valida o serviço.

### [SWE] 2026-09-25 — Implementação iniciada

Plano Supabase incorporado ao worktree da 061. A implementação direta de Google OIDC/SQLite que estava em andamento será substituída pelo fluxo Supabase Auth. A fundação 077 permanece pré-requisito para migrações, permissões e integração real; rotas de tarefas continuam exclusivas da credencial de operador até a 062.

### [SWE] 2026-09-25 — Contrato HTTP e validação local

FastAPI inicia OAuth Google via Supabase Auth com PKCE, troca o código no callback e expõe sessão/logout com cookie cifrado HttpOnly, state vinculado ao navegador, verificação JWKS/claims e proteção de Origin. O endpoint público JWKS do projeto `xmqpgubedtjirohntdwg` anuncia ES256. Testes HTTP controlados passaram; `make pre-commit`, `make unit-tests` e `production-smoke-tests` passaram. Smoke local em `127.0.0.1:8011`: `/health` 200, `/tasks` sem chave 401, `/auth/session` sem cookie 401, logout com origem indevida 403 e início de login 303 para o projeto correto. O provedor Google real, Postgres privado da 077 e validação de revogação em `auth.sessions` ainda não foram exercitados; task permanece em progresso.

### [SWE] 2026-09-25 — Login Google real no ambiente local

Projeto Supabase `xmqpgubedtjirohntdwg`: provedor Google habilitado, Client ID correspondente ao cliente Google Cloud e callback do Google configurado para o Supabase. Site URL e redirect local de `127.0.0.1:8001` confirmados no painel. Como outra versão do runtime ocupava 8001, a versão desta worktree foi iniciada isoladamente em 8011, com redirect temporário adicionado e removido após o teste. No navegador, o fluxo chegou à seleção de conta Google, retornou ao callback do runtime e `/auth/session` respondeu 200 com o mesmo UUID após recarregar. `POST /auth/logout` respondeu 200 e a consulta seguinte à sessão respondeu 401. O runtime de teste foi encerrado. A integração Postgres da 077, a verificação de revogação em `auth.sessions` e o login em staging HTTPS ainda estão pendentes; a task permanece em progresso.
