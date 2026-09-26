---
id: 061-google-login-and-sessions
feature: mvp-web
status: pending
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

Testes HTTP determinísticos mais integração com Supabase Auth local e login/logout Google real na URL HTTPS publicada, com conta autorizada e sem fixtures sintéticas em produção; incluir reload e refresh. Evidência com mocks não comprova OAuth real. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Tela de login (068), ownership (062), outros provedores de identidade.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.

### [PA] 2026-09-25 — Revisão para produção com Supabase

Plano atualizado por solicitação do usuário: Supabase Auth/Postgres, isolamento e provas no ambiente publicado. Critérios continuam pendentes; esta revisão não implementa nem valida o serviço.
