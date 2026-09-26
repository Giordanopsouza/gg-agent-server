---
id: 077-supabase-foundation
feature: mvp-web
status: in-progress
depends_on: []
---

# Fundação Supabase e migrações reproduzíveis

## Scope

Preparar Supabase local e o projeto de produção existente como ambientes separados e a base Postgres usada por identidade e runtime. O usuário optou por não criar staging nesta task após o limite de projetos gratuitos impedir a criação. Entregar primeiro um ambiente reproduzível, sem depender do frontend completo.

## Acceptance criteria

- [x] Versionar configuração e migrações; reproduzir schema do zero e upgrade a partir da versão anterior com dados sintéticos. Fixar versões de ferramentas/dependências e lockfiles.
- [x] Supabase Auth é dono de auth.users/sessões. Modelar perfil pelo UUID, sem autorização por email ou user_metadata. Schema privado para dados do runtime/cofre; nenhuma tabela do produto precisa ser exposta à Data API no MVP.
- [x] Revogar acesso de anon/authenticated a schemas privados. Qualquer tabela exposta exige grants mínimos e RLS testada; não criar políticas abertas para fazer testes passar. Registrar matriz de papéis e verificar advisors.
- [x] Configurar conexão TLS, pool limitado, timeouts e usuário runtime de privilégio mínimo separado do migrador; provar compatibilidade com o modo de conexão/pool escolhido.
- [x] Adicionar targets no Makefile raiz para subir/resetar ambiente local e executar integração; reset destrutivo só no projeto local/de teste com identificação explícita.
- [x] Documentar variáveis por ambiente, callback Supabase/Google e responsabilidade dos segredos; nenhum secret/service_role, senha de banco ou chave de cifra no cliente.

## Validation

Integração local real de Auth/Postgres, migração vazia/upgrade e consultas sob cada papel; readiness de produção autenticado e somente leitura, sem publicar dados de teste. Seguir QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Billing, organizações e alta disponibilidade.

## Log

### [PA] 2026-09-25 — Revisão para produção com Supabase

Plano atualizado por solicitação do usuário: Supabase Auth/Postgres, isolamento e provas no ambiente publicado. Critérios continuam pendentes; esta revisão não implementa nem valida o serviço.

### [SWE] 2026-09-25 21:11 -03 — Fundação local e bloqueio de staging

Configuração CLI fixada, schemas privados, papel runtime e perfil UUID implementados. Integração local de Auth, grants, migração vazia/upgrade e conexão direta em andamento. Usuário identificou `xmqpgubedtjirohntdwg` como produção; criação do staging separado foi rejeitada pelo limite de dois projetos gratuitos ativos da organização. Não aplicar migrações nem fixtures em produção antes da prova em staging.

### [SWE] 2026-09-25 21:24 -03 — Produção autorizada sem staging

Por decisão do usuário, seguir apenas com Supabase local e projeto de produção `xmqpgubedtjirohntdwg`. Três migrações aplicadas no projeto publicado após validação local; nomes locais alinhados ao histórico remoto. Consultas somente leitura confirmaram grants, RLS e papel runtime. Advisor de performance sem findings; aviso de senha vazada permanece por recurso Pro-only. Nenhuma fixture foi escrita na produção.

### [SWE] 2026-09-25 21:34 -03 — Session pooler IPv4 validado até Auth

Dashboard confirmou `aws-0-us-west-2.pooler.supabase.com:5432` para Session pooler. Teste TLS `verify-full` com CA baixada do projeto alcançou a autenticação; falha esperada porque `gg_runtime` ainda não tem senha. CA pública incluída no pacote servidor. Integração local completa passou (20 asserções pgTAP, Auth real, upgrade, pool e advisor). Revisão automática rejeitou `ALTER ROLE ... PASSWORD` em produção por criar acesso persistente sem aprovação explícita neste escopo; nenhuma variável de banco foi gravada no Railway. Critério de conexão autenticada de produção permanece pendente.

### [SWE] 2026-09-25 21:39 -03 — Login autenticado de produção aprovado

Usuário aprovou explicitamente senha do papel `gg_runtime`, URL server-only no Railway e teste autenticado. Senha aleatória aplicada fora das migrações; `GG_RUNTIME_DATABASE_URL` e `GG_DB_POOL_MAX=4` salvos no serviço `gg-runtime` com redeploy desativado. Smoke somente leitura da máquina de desenvolvimento passou com Session pooler, `verify-full`, CA empacotada, papel/timeout e isolamento RLS. Não houve fixture nem reset na produção. Teste a partir do host Railway e enforcement global de SSL ficam para o cutover da task 078.
