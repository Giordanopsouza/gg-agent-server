---
id: 062-task-ownership-and-idempotency
feature: mvp-web
status: pending
depends_on: [061-google-login-and-sessions]
---

# Ownership, migração e idempotência por usuário

## Migration preflight

Ler o [plano do MVP](../mvp-web-plan.md), os ADRs [0001](../adr/0001-modal-background-tasks.md), [0002](../adr/0002-general-background-tasks.md) e [0003](../adr/0003-remove-legacy-learning-surfaces.md), o AGENTS.md do componente e as tasks diretamente dependentes/consumidoras. Registrar estado final, pontes temporárias com legado, responsável pela remoção e teste que protege a fronteira. Inspecionar contratos em `gg.sdk`, ledger, rotas e serviço de tarefas. Registrar como o novo escopo substitui a premissa de acesso global dos ADRs, sem criar um segundo ciclo de execução.

## Scope

Aplicar identidade do proprietário à admissão e a todas as superfícies de tarefas, preservando o acesso administrativo separado.

## Acceptance criteria

- [ ] Preencher owner_id no servidor a partir da sessão; ignorar/rejeitar tentativa do cliente de escolher outro proprietário.
- [ ] Migrar tarefas e deduplicação antigas para escopo administrativo explícito; nenhum login recebe automaticamente registros legados.
- [ ] Autorizar lista, detalhe, eventos/polling, streams, resultado, mensagem, recibo, cancelamento e retry, inclusive referências indiretas e registros expirados.
- [ ] Garantir unicidade de idempotência por proprietário e comparação integral do payload; incluir modelo e continuação quando seus contratos forem introduzidos.
- [ ] Reenvio concorrente da mesma chave/payload retorna a mesma tarefa; payload divergente conflita e dois usuários podem usar a mesma chave.
- [ ] Manter chave de operador fora dos contratos web e garantir que autenticação administrativa ausente/inválida não seja substituída por sessão web.
- [ ] Provar com duas contas que nenhuma leitura ou mutação cruzada revela dados ou altera tarefas; testar também migração e regressão do cliente CLI.

## Validation

Testes HTTP/stream com duas sessões, migração de banco legado e reenvio concorrente; executar a verificação de fronteira de imports do SDK. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Organizações, compartilhamento de tarefas e papéis de equipe.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.
