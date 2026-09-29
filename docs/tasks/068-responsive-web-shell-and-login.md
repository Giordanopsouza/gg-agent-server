---
id: 068-responsive-web-shell-and-login
feature: mvp-web
status: done
depends_on: [062-task-ownership-and-idempotency]
---

# Shell responsivo, login e navegação

## Scope

Adaptar o frontend existente à sessão web, com login e navegação de histórico para desktop. A aplicação não terá interface mobile nesta tarefa.

## Acceptance criteria

- [x] Navegador sem sessão mostra login Google com falha/cancelamento legíveis; logout limpa estado de conta e dados em cache.
- [x] Sessão expirada solicita autenticação e preserva rascunho para a mesma conta, sem mostrá-lo a outra conta que entre depois.
- [x] Manter sidebar desktop com histórico sempre acessível.
- [x] Mostrar histórico por repositório com título curto, estado e data; tratar loading, vazio, erro e tarefa selecionada após reload.
- [x] Garantir foco/teclado, rótulos acessíveis e ausência de overflow nas larguras desktop 768 e 1440px.
- [x] Remover chave administrativa do bundle, formulários, cliente HTTP e persistência do browser; descartar valor legado sem enviá-lo.
- [x] Integrar testes/build web em targets delegados pelo Makefile raiz e documentar execução.

## Validation

Testes de sessão/navegação com API controlada, build web e roteiro reproduzível de browser nas larguras desktop 768 e 1440px. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Onboarding de credenciais (069), módulos futuros e redesenho completo da identidade visual.
Layout e navegação mobile ficam fora do escopo por decisão de produto.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.

### 2026-09-29 — Desktop implementation

Escopo mobile removido conforme decisão de produto. Login, expiração de sessão,
rascunho por conta, histórico por repositório e targets frontend implementados.
Testes web com API controlada passaram. O shell foi exercitado no browser em
768px e 1440px com API mock local, incluindo reload da tarefa selecionada.
O fluxo OAuth real ficou sem exercício local porque Postgres/Docker não estavam
disponíveis neste ambiente; os testes de auth que exigem Postgres foram pulados.
