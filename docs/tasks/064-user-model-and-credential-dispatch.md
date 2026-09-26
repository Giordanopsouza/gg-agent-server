---
id: 064-user-model-and-credential-dispatch
feature: mvp-web
status: pending
depends_on: [062-task-ownership-and-idempotency, 063-personal-openrouter-credentials]
---

# Modelo e credencial do usuário até o Pi

## Scope

Transportar o modelo escolhido e resolver a chave pessoal no dispatch até o processo Pi no sandbox correspondente.

## Acceptance criteria

- [ ] Oferecer um modelo padrão e catálogo pequeno de modelos verificados; validar escolha no servidor e persistir o identificador efetivo na tarefa.
- [ ] Incluir modelo na comparação de idempotência e propagá-lo por contrato tipado até PiAgentConfig, eliminando o padrão implícito que perde a seleção.
- [ ] Resolver referência/versionamento da credencial do proprietário no dispatch; não copiar segredo para a fila nem usar chave global como fallback de tarefa web.
- [ ] Bloquear execução sem chave válida com erro recuperável; tratar falhas de autenticação, saldo e limite também durante o run.
- [ ] Reenvio/retry resolve a credencial conforme a política de rotação, mantendo visível o modelo efetivamente usado.
- [ ] Redigir segredos antes de persistir ou retornar logs, eventos, transcript e evidências; documentar limites de proteção quando o próprio agente usa a credencial.
- [ ] Testar duas tarefas com usuários/modelos distintos até a fronteira de criação do sandbox e configuração real do supervisor; segredo de A nunca é entregue a B.

## Validation

Teste de integração runtime → contrato HTTP do supervisor → configuração do Pi com execução controlada e varredura das saídas persistidas. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Fallback automático de modelos, múltiplos agentes e seleção livre de provedores.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.
