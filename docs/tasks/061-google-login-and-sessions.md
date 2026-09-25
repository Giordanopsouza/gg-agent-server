---
id: 061-google-login-and-sessions
feature: mvp-web
status: pending
depends_on: []
---

# Login Google e sessão web

## Migration preflight

Ler o [plano do MVP](../mvp-web-plan.md), os ADRs [0001](../adr/0001-modal-background-tasks.md), [0002](../adr/0002-general-background-tasks.md) e [0003](../adr/0003-remove-legacy-learning-surfaces.md), o AGENTS.md do componente e as tasks diretamente dependentes/consumidoras. Registrar estado final, pontes temporárias com legado, responsável pela remoção e teste que protege a fronteira. Inspecionar a autenticação de `runtime/app.py` e separar explicitamente sessão web de credencial de operador. O acesso administrativo existente pode permanecer para CLI; não pode se tornar fallback de autenticação web.

## Scope

Entregar autenticação Google OIDC no runtime e uma sessão opaca persistida no servidor, com contratos HTTP utilizáveis pelo frontend.

## Acceptance criteria

- [ ] Usar biblioteca OIDC estabelecida e validar assinatura, issuer, audience, expiração, state e nonce; identificar a conta pelo sub do Google, nunca apenas pelo email.
- [ ] Persistir usuários e sessões em SQLite com migração repetível; definir expiração, revogação e armazenamento seguro do identificador de sessão.
- [ ] Disponibilizar início/callback de login, consulta da sessão e logout; tratar cancelamento, callback inválido e sessão expirada sem expor tokens.
- [ ] Usar cookie HttpOnly, Secure em produção e SameSite explícito; proteger mutações por CSRF/Origin e restringir redirecionamentos de retorno.
- [ ] Manter as rotas de tarefas fechadas à sessão web até a autorização por proprietário da task 062; login sozinho não habilita acesso global.
- [ ] Testar callback válido e rejeições, conta estável pelo sub, expiração, logout e mutação de origem indevida através do app HTTP.

## Validation

Testes HTTP com provedor OIDC controlado e roteiro opt-in de login/logout real; evidência com mocks não comprova OAuth real. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Tela de login (068), ownership (062), outros provedores de identidade.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.
