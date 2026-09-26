---
id: 065-github-account-and-app-connection
feature: mvp-web
status: pending
depends_on: [061-google-login-and-sessions, 063-personal-openrouter-credentials]
---

# Conexão da conta GitHub e instalação da App

## Scope

Vincular a identidade GitHub à sessão Google e registrar instalações verificadas da GitHub App.

## Acceptance criteria

- [ ] Implementar início/callback de autorização com state vinculado à sessão e associação por identidade verificada, nunca por coincidência de email.
- [ ] Verificar no GitHub a relação entre usuário e instalação; installation_id enviado pelo browser não concede acesso.
- [ ] Expor status da conexão, instalações disponíveis e desconexão/reconexão sem retornar tokens; preservar isolamento entre contas.
- [ ] Tratar autorização de organização pendente, instalação removida e autorização revogada com estado recuperável.
- [ ] Verificar assinatura e deduplicar entregas dos webhooks usados para invalidar acesso; definir comportamento quando chegam fora de ordem.
- [ ] Documentar callbacks, webhook, permissões mínimas e o fato de operações com token de instalação aparecerem atribuídas à App.
- [ ] Testar callbacks forjados, vínculo de outra conta, webhook inválido/repetido e desconexão.

- [ ] Persistir vínculos, instalações e deduplicação de webhook no Supabase Postgres por UUID do usuário; tokens cifrados em schema privado. Login Google via Supabase não concede acesso a instalações GitHub.

## Validation

Testes HTTP com GitHub controlado e roteiro opt-in de conexão real da App; não requerer instalação paga nos testes comuns. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Seleção de repositório/branch e emissão do token da tarefa (066), GitLab e contas de equipe.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.

### [PA] 2026-09-25 — Revisão para produção com Supabase

Plano atualizado por solicitação do usuário: Supabase Auth/Postgres, isolamento e provas no ambiente publicado. Critérios continuam pendentes; esta revisão não implementa nem valida o serviço.
