---
id: 066-authorized-repositories-and-task-tokens
feature: mvp-web
status: pending
depends_on: [062-task-ownership-and-idempotency, 065-github-account-and-app-connection]
---

# Repositórios autorizados e token restrito da tarefa

## Scope

Listar repositórios/branches autorizados e fornecer credencial GitHub restrita ao repositório na execução.

## Acceptance criteria

- [ ] Listar a interseção entre acesso do usuário e da instalação, com permissão suficiente para modificar o repo; incluir repositórios privados autorizados.
- [ ] Listar/validar branches do repo escolhido e resolver base ref/SHA no servidor; request forjado não contorna autorização.
- [ ] Revalidar acesso na admissão e no dispatch; expor o mesmo serviço de autorização para retry e continuação, inclusive após reconectar.
- [ ] Emitir token de instalação limitado ao repo da tarefa e às permissões necessárias para conteúdo/PR, sem repassar a chave privada ao sandbox.
- [ ] Definir renovação do token de uma hora ou prazo de execução compatível com sua expiração, incluindo clone e publicação; cobrir expiração em teste.
- [ ] Tratar remoção de repo, revogação e falha de clone sem recorrer ao token global; segredos não ficam em URLs persistidas, remotes ou logs públicos.
- [ ] Provar que uma conta não consegue selecionar, clonar ou emitir token para repo não autorizado, mesmo alterando ids e payloads.

## Validation

Testes de API/admissão/dispatch com matriz de acesso e expiração; demo real de repo privado integrado à 075. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Configurações de ambiente, conjuntos de repositórios e herança de permissões.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.
