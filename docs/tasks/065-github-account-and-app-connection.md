---
id: 065-github-account-and-app-connection
feature: mvp-web
status: in-progress
depends_on: [061-google-login-and-sessions, 063-personal-openrouter-credentials]
---

# Conexão da conta GitHub e instalação da App

## Scope

Vincular a identidade GitHub à sessão Google e registrar instalações verificadas da GitHub App.

## Acceptance criteria

- [x] Implementar início/callback de autorização com state vinculado à sessão e associação por identidade verificada, nunca por coincidência de email.
- [x] Verificar no GitHub a relação entre usuário e instalação; installation_id enviado pelo browser não concede acesso.
- [x] Expor status da conexão, instalações disponíveis e desconexão/reconexão sem retornar tokens; preservar isolamento entre contas.
- [x] Tratar autorização de organização pendente, instalação removida e autorização revogada com estado recuperável.
- [x] Verificar assinatura e deduplicar entregas dos webhooks usados para invalidar acesso; definir comportamento quando chegam fora de ordem.
- [x] Documentar callbacks, webhook, permissões mínimas e o fato de operações com token de instalação aparecerem atribuídas à App.
- [x] Testar callbacks forjados, vínculo de outra conta, webhook inválido/repetido e desconexão.

- [x] Persistir vínculos, instalações e deduplicação de webhook no Supabase Postgres por UUID do usuário; tokens cifrados em schema privado. Login Google via Supabase não concede acesso a instalações GitHub.

## Validation

Testes HTTP com GitHub controlado e roteiro opt-in de conexão real da App; não requerer instalação paga nos testes comuns. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Seleção de repositório/branch e emissão do token da tarefa (066), GitLab e contas de equipe.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.

### [PA] 2026-09-25 — Revisão para produção com Supabase

Plano atualizado por solicitação do usuário: Supabase Auth/Postgres, isolamento e provas no ambiente publicado. Critérios continuam pendentes; esta revisão não implementa nem valida o serviço.

### [SWE] 2026-09-28 19:34 -03 — Implementação e validação local

Fluxo OAuth da GitHub App com PKCE, state persistido para uso único e sessão Supabase ativa; identidade numérica GitHub vinculada ao UUID do usuário, com unicidade entre contas. `GET /user/installations` confirma instalações e ignora `installation_id` do browser. Token de usuário cifrado em `vault_private`, snapshot e deduplicação de webhook em `app_private`, RLS por proprietário e função restrita para invalidar eventos assinados. Status, desconexão e reconexão documentados em `docs/github-app-connection.md`; Vite encaminha `/auth` ao runtime.

Testes HTTP controlados (2) cobrem callback forjado/entre contas/repetido, instalação pendente/suspensa, webhook inválido/repetido e desconexão. Alembic criou, adotou, verificou drift e reverteu o schema em banco isolado; contrato Postgres usou `gg_runtime` real para provar isolamento, ciphertext, unicidade, invalidação e deduplicação. `make pre-commit` passou (283 aprovados, 82 ignorados, 2 excluídos); frontend passou 3 testes e build. Smoke local do runtime/Vite confirmou `/auth` e assinatura/deduplicação em HTTP. A prova opt-in com GitHub App real permanece pendente porque client ID/secret, webhook secret e callback público não estão configurados neste ambiente.
