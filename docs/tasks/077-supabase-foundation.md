---
id: 077-supabase-foundation
feature: mvp-web
status: pending
depends_on: []
---

# Fundação Supabase e migrações reproduzíveis

## Scope

Preparar Supabase local, staging e produção como ambientes separados e a base Postgres usada por identidade e runtime. Entregar primeiro um ambiente reproduzível, sem depender do frontend completo.

## Acceptance criteria

- [ ] Versionar configuração e migrações; reproduzir schema do zero e upgrade a partir da versão anterior com dados sintéticos. Fixar versões de ferramentas/dependências e lockfiles.
- [ ] Supabase Auth é dono de auth.users/sessões. Modelar perfil pelo UUID, sem autorização por email ou user_metadata. Schema privado para dados do runtime/cofre; nenhuma tabela do produto precisa ser exposta à Data API no MVP.
- [ ] Revogar acesso de anon/authenticated a schemas privados. Qualquer tabela exposta exige grants mínimos e RLS testada; não criar políticas abertas para fazer testes passar. Registrar matriz de papéis e verificar advisors.
- [ ] Configurar conexão TLS, pool limitado, timeouts e usuário runtime de privilégio mínimo separado do migrador; provar compatibilidade com o modo de conexão/pool escolhido.
- [ ] Adicionar targets no Makefile raiz para subir/resetar ambiente local e executar integração; reset destrutivo só no projeto local/de teste com identificação explícita.
- [ ] Documentar variáveis por ambiente, callback Supabase/Google e responsabilidade dos segredos; nenhum secret/service_role, senha de banco ou chave de cifra no cliente.

## Validation

Integração local real de Auth/Postgres, migração vazia/upgrade e consultas sob cada papel; readiness de staging autenticado sem publicar dados de teste em produção. Seguir QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Billing, organizações e alta disponibilidade.

## Log

### [PA] 2026-09-25 — Revisão para produção com Supabase

Plano atualizado por solicitação do usuário: Supabase Auth/Postgres, isolamento e provas no ambiente publicado. Critérios continuam pendentes; esta revisão não implementa nem valida o serviço.
