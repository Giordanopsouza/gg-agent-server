---
id: 068-responsive-web-shell-and-login
feature: mvp-web
status: pending
depends_on: [062-task-ownership-and-idempotency]
---

# Shell responsivo, login e navegação

## Migration preflight

Ler o [plano do MVP](../mvp-web-plan.md), os ADRs [0001](../adr/0001-modal-background-tasks.md), [0002](../adr/0002-general-background-tasks.md) e [0003](../adr/0003-remove-legacy-learning-surfaces.md), o AGENTS.md do componente e as tasks diretamente dependentes/consumidoras. Registrar estado final, pontes temporárias com legado, responsável pela remoção e teste que protege a fronteira. Inspecionar App.tsx, api.ts e styles.css. Remover o fluxo de chave administrativa/localStorage; reutilizar React/Vite e identidade visual existentes.

## Scope

Adaptar o frontend existente à sessão web, com login, navegação de histórico e layout utilizável no celular.

## Acceptance criteria

- [ ] Navegador sem sessão mostra login Google com falha/cancelamento legíveis; logout limpa estado de conta e dados em cache.
- [ ] Sessão expirada solicita autenticação e preserva rascunho para a mesma conta, sem mostrá-lo a outra conta que entre depois.
- [ ] Criar sidebar desktop e gaveta mobile com botão de histórico sempre acessível; não esconder a única navegação abaixo de 650px.
- [ ] Mostrar histórico por repositório com título curto, estado e data; tratar loading, vazio, erro e tarefa selecionada após reload.
- [ ] Garantir foco/teclado, rótulos acessíveis, composer com teclado mobile aberto e ausência de overflow nas larguras 360, 390, 768 e 1440px.
- [ ] Remover chave administrativa do bundle, formulários, cliente HTTP e persistência do browser; descartar valor legado sem enviá-lo.
- [ ] Integrar testes/build web em targets delegados pelo Makefile raiz e documentar execução.

## Validation

Testes de sessão/navegação com API controlada, build web e roteiro reproduzível de browser nas quatro larguras. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Onboarding de credenciais (069), módulos futuros e redesenho completo da identidade visual.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.
