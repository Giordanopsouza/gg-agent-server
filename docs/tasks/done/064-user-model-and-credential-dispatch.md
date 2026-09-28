---
id: 064-user-model-and-credential-dispatch
feature: mvp-web
status: done
depends_on: [062-task-ownership-and-idempotency, 063-personal-openrouter-credentials]
---

# Modelo e credencial do usuário até o Pi

## Scope

Transportar o modelo escolhido e resolver a chave pessoal no dispatch até o processo Pi no sandbox correspondente.

## Acceptance criteria

- [x] Oferecer um modelo padrão e catálogo pequeno de modelos verificados; validar escolha no servidor e persistir o identificador efetivo na tarefa.
- [x] Incluir modelo na comparação de idempotência e propagá-lo por contrato tipado até PiAgentConfig, eliminando o padrão implícito que perde a seleção.
- [x] Resolver referência/versionamento da credencial do proprietário no dispatch; não copiar segredo para a fila nem usar chave global como fallback de tarefa web.
- [x] Bloquear execução sem chave válida com erro recuperável; tratar falhas de autenticação, saldo e limite também durante o run.
- [x] Reenvio/retry resolve a credencial conforme a política de rotação, mantendo visível o modelo efetivamente usado.
- [x] Redigir segredos antes de persistir ou retornar logs, eventos, transcript e evidências; documentar limites de proteção quando o próprio agente usa a credencial.
- [x] Testar duas tarefas com usuários/modelos distintos até a fronteira de criação do sandbox e configuração real do supervisor; segredo de A nunca é entregue a B.

## Validation

Teste de integração runtime → contrato HTTP do supervisor → configuração do Pi com execução controlada e varredura das saídas persistidas. Seguir os comandos de QA do [índice](../README.md#validação-e-conclusão).

## Política e limites

`GET /tasks/models` publica o catálogo fixo. A tarefa armazena o modelo efetivo e o retry mantém esse modelo. No dispatch, o runtime lê a versão corrente da chave do proprietário e a valida novamente no OpenRouter. Uma substituição ou remoção vale para a próxima criação de sandbox; uma execução já ativa continua com a chave entregue ao seu processo até o encerramento. Falha de chave, saldo ou limite gera estado recuperável por retry depois da correção.

O segredo não integra o payload público, a fila ou o contrato HTTP do supervisor. Eventos do Pi e manifestos de evidência são redigidos antes da persistência e resposta. O próprio agente recebe a chave em seu ambiente e pode lê-la, enviá-la a uma ferramenta/rede ou gravá-la em arquivos do workspace; a redação de logs e evidências não constitui isolamento contra um agente malicioso. Revogar a chave no OpenRouter é necessário para invalidar imediatamente uma chave já entregue.

Catálogo verificado em 2026-09-28 nas páginas do OpenRouter para [GLM 5.3 FlashX](https://openrouter.ai/z-ai/glm-5.3-flashx) e [Claude Sonnet 4.5](https://openrouter.ai/anthropic/claude-sonnet-4.5).

## Out of scope

Fallback automático de modelos, múltiplos agentes e seleção livre de provedores.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.

### [SWE] 2026-09-28 — Implementação e validação local

Modelo validado, persistido na tarefa/tombstone e enviado por contrato HTTP até PiAgentConfig; migração Alembic 0002 aplicada e testada em Postgres local. Chave por proprietário resolvida e validada no dispatch, com versão registrada sem segredo durável na fila. Testes controlados cobriram isolamento de dois usuários, chave removida/revogada, rotação por nova criação, modelo no supervisor, erros do Pi e varredura de eventos e manifesto. Suíte unitária em schema Postgres descartável: 360 testes aprovados, 2 excluídos pela marcação. Alembic testou criação, adoção, drift e rollback. Smoke da API local: catálogo 200, tarefa 201 com modelo selecionado, replay 200, conflito de modelo 409 e cancelamento 200. A demo usou dispatch desativado; não provisionou Modal nem consumiu crédito OpenRouter.
