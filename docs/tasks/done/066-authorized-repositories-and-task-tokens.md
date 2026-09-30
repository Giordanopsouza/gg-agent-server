---
id: 066-authorized-repositories-and-task-tokens
feature: mvp-web
status: in-progress
depends_on: [062-task-ownership-and-idempotency, 065-github-account-and-app-connection]
---

# Repositórios autorizados e token restrito da tarefa

## Scope

Listar repositórios/branches autorizados e fornecer credencial GitHub restrita ao repositório na execução.

## Acceptance criteria

- [x] Listar a interseção entre acesso do usuário e da instalação, com permissão suficiente para modificar o repo; incluir repositórios privados autorizados.
- [x] Listar/validar branches do repo escolhido e resolver base ref/SHA no servidor; request forjado não contorna autorização.
- [x] Revalidar acesso na admissão e no dispatch; expor o mesmo serviço de autorização para retry e continuação, inclusive após reconectar.
- [x] Emitir token de instalação limitado ao repo da tarefa e às permissões necessárias para conteúdo/PR, sem repassar a chave privada ao sandbox.
- [x] Definir renovação do token de uma hora ou prazo de execução compatível com sua expiração, incluindo clone e publicação; cobrir expiração em teste.
- [x] Tratar remoção de repo, revogação e falha de clone sem recorrer ao token global; segredos não ficam em URLs persistidas, remotes ou logs públicos.
- [x] Provar que uma conta não consegue selecionar, clonar ou emitir token para repo não autorizado, mesmo alterando ids e payloads.

## Validation

Testes de API/admissão/dispatch com matriz de acesso e expiração; demo real de repo privado integrado à 075. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Configurações de ambiente, conjuntos de repositórios e herança de permissões.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.

### [SWE] 2026-09-28 — Implementação e validação automatizada

Serviço de autorização consulta GitHub ao listar repositórios e branches, admitir tarefas, despachar, continuar e publicar. Exige escrita do usuário e da instalação, resolve SHA no servidor e emite token de instalação com um único `repository_id` e permissões Contents/Pull requests write. O sandbox clona sem credencial na URL/remoto, remove o token do ambiente herdado pelo agente e usa prazo de 45 minutos; a publicação recebe token novo. Testes de matriz de acesso, API e bloqueio antes da criação do sandbox cobrem repo privado, outra conta, payload forjado, remoção, perda de escrita e expiração. Ruff e suíte unitária passaram (289 aprovados, 82 ignorados, 2 excluídos). A demo de GitHub App real e repo privado está prevista na 075; este ambiente não tem chave privada da App nem Supabase local ativo.
