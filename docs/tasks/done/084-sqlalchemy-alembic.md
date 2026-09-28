---
id: 084-sqlalchemy-alembic
feature: mvp-web
status: done
depends_on: [077-supabase-foundation, 078-runtime-postgres-migration]
---

# Adotar SQLAlchemy e Alembic no backend

## Scope

Substituir a infraestrutura de acesso Postgres do backend por SQLAlchemy 2.x
síncrono sobre psycopg e tornar Alembic a autoridade das futuras mudanças no
schema da aplicação. Supabase continua fornecendo Postgres e Auth; `gg.sdk`
permanece sem dependência do servidor.

## Acceptance criteria

- [x] Modelar as tabelas privadas atuais em metadata SQLAlchemy, preservando
  schemas, constraints, índices, RLS e grants existentes.
- [x] Usar um `Engine` limitado e compartilhado para ledger, sessões web e
  cofre, sem alterar os contratos HTTP nem as garantias transacionais.
- [x] Adicionar Alembic com baseline adotável por bancos existentes e capaz de
  criar o schema da aplicação em um Postgres/Supabase vazio.
- [x] Impedir dois fluxos de migração concorrentes: migrações Supabase antigas
  ficam congeladas; novas alterações da aplicação usam Alembic.
- [x] Provar upgrade, downgrade/stamp seguro, detecção de drift e os contratos
  concorrentes do ledger em Postgres real.
- [x] Atualizar comandos e documentação operacional, incluindo adoção sem
  reaplicar DDL no banco publicado.

## Validation

Rodar formatação, lint, testes unitários, integração Postgres/Alembic e o fluxo
real do frontend + runtime conforme `.agents/skills/local-stack/SKILL.md`.

## Out of scope

Trocar Supabase Auth, expor tabelas privadas pela Data API ou migrar o runtime
para I/O assíncrono.

## Log

### [SWE] 2026-09-28 — SQLAlchemy e Alembic validados localmente

SQLAlchemy 2.0 e Alembic passaram a usar versões fixadas; o backend compartilha
um `Engine` limitado entre ledger, sessões e cofre, preservando o SQL explícito
nas operações concorrentes. O baseline criou um banco descartável do zero,
adotou novamente o mesmo schema sem perder uma linha de prova, recusou downgrade
destrutivo e terminou com `alembic check` sem drift. A suíte Postgres passou com
351 testes e 2 exclusões; formatação, lint, 270 testes unitários, smokes reais
de pool/sessão/cofre e a stack local também passaram. No fluxo integrado em
`8012`/`5174`, uma tarefa entrou como `queued`, foi relida do Postgres e
cancelada. O Supabase de produção não foi alterado.
