---
id: 069-web-onboarding-and-task-creation
feature: mvp-web
status: pending
depends_on: [064-user-model-and-credential-dispatch, 066-authorized-repositories-and-task-tokens, 068-responsive-web-shell-and-login]
---

# Onboarding e criação de tarefa pelo navegador

## Migration preflight

Ler o [plano do MVP](../mvp-web-plan.md), os ADRs [0001](../adr/0001-modal-background-tasks.md), [0002](../adr/0002-general-background-tasks.md) e [0003](../adr/0003-remove-legacy-learning-surfaces.md), o AGENTS.md do componente e as tasks diretamente dependentes/consumidoras. Registrar estado final, pontes temporárias com legado, responsável pela remoção e teste que protege a fronteira. Consumir os contratos de 063–066 via api.ts, sem duplicar regras de autorização no cliente nem persistir segredos no browser.

## Scope

Entregar configurações pessoais e composer que cria tarefas com repositório, branch e modelo autorizados.

## Acceptance criteria

- [ ] Conduzir Google → OpenRouter → GitHub com estados claros; explicar que salvar chave a envia ao backend para armazenamento protegido e validação.
- [ ] Permitir trocar/remover chave e conectar/desconectar/reconectar GitHub, mostrando status/máscara e política para execuções ativas.
- [ ] Selecionar repo/branch autorizados e modelo do catálogo; tratar lista vazia, instalação pendente e acesso revogado.
- [ ] Enviar prompt pelo contrato de criação e abrir a tarefa retornada; manter rascunho e escolhas quando houver erro recuperável.
- [ ] Reutilizar idempotency key após timeout/duplo clique do mesmo envio; criar outra chave quando o payload mudar.
- [ ] Exibir erros de autenticação, saldo, limite e GitHub sem expor segredo; não confundir validação da chave com garantia de execução.
- [ ] Testar onboarding, edição/remoção de chave e criação com timeout seguido de reenvio sem duplicação.

## Validation

Testes de componentes/API e demo local pelo browser contra o runtime; validação externa real fica registrada na 075. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Billing, múltiplos provedores, configurações avançadas por repositório.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.
