---
id: 071-durable-task-continuation
feature: mvp-web
status: pending
depends_on: [067-pi-owned-pr-publication]
---

# Continuação durável na mesma branch e PR

## Scope

Adicionar uma ação de continuação com novo prompt e execução vinculada, reutilizando contexto limitado e branch/PR após encerramento do sandbox.

## Acceptance criteria

- [ ] Definir contrato compartilhado com novo prompt, vínculo à execução anterior e identidade durável da conversa/PR; persistir contexto limitado e política de retenção.
- [ ] Autorizar predecessor, histórico e repo pelo proprietário; revalidar GitHub e resolver HEAD atual antes do novo run.
- [ ] Reutilizar branch e PR verificadas, criando novo sandbox sem depender da VM anterior; não restaurar implicitamente mudanças locais não publicadas.
- [ ] Impedir dois runs escrevendo na mesma branch com reserva durável/atômica, inclusive durante restart e cleanup incerto; liberar somente quando seguro.
- [ ] Rejeitar continuação de PR fechada/mergeada com conflito explícito e possibilidade de nova tarefa; não criar outra PR silenciosamente.
- [ ] Sem repo, permitir nova execução com contexto; se contexto expirou ou está incompleto, retornar comportamento explícito e testado.
- [ ] Incluir vínculo, prompt, modelo e repo na idempotência; timeout/reenvio não cria dois runs de continuação.
- [ ] Testar continuação após término do sandbox, ownership, concorrência, restart, HEAD alterado e PR fechada/mergeada.

## Validation

Testes HTTP com ledger real e corrida de duas continuações; demo opt-in registra dois runs e a mesma URL de PR. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

VM permanente, restauração genérica de arquivos não publicados e edição concorrente na mesma branch.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.
