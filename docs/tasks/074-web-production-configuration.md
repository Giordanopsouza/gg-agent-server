---
id: 074-web-production-configuration
feature: mvp-web
status: pending
depends_on: [065-github-account-and-app-connection, 072-web-continuation-history, 073-per-user-runtime-limits]
---

# Configuração de produção do MVP web

## Migration preflight

Ler o [plano do MVP](../mvp-web-plan.md), os ADRs [0001](../adr/0001-modal-background-tasks.md), [0002](../adr/0002-general-background-tasks.md) e [0003](../adr/0003-remove-legacy-learning-surfaces.md), o AGENTS.md do componente e as tasks diretamente dependentes/consumidoras. Registrar estado final, pontes temporárias com legado, responsável pela remoção e teste que protege a fronteira. Inspecionar docs/single-host-production.md e configuração de deploy vigente, respeitando alterações locais. Não recriar templates operacionais removidos sem necessidade da implantação escolhida.

## Scope

Documentar e exercitar a montagem web/API na mesma origem com HTTPS, migrações e recuperação segura do estado do MVP.

## Acceptance criteria

- [ ] Servir build web e API na mesma origem, com callbacks Google/GitHub coerentes, cookie Secure, CSRF e roteamento de reload funcionando.
- [ ] Documentar variáveis públicas/privadas, cliente OAuth, App/webhook/permissões, chave de criptografia, imagem/app Modal e repo de teste autorizado.
- [ ] Atualizar runbook de migração, operação administrativa, revogação e rotação de credenciais; não distribuir chave administrativa ao browser.
- [ ] Cobrir backup/restore de usuários, ownership, sessões, referências e credenciais cifradas; guardar chave de criptografia separadamente e definir invalidação de sessões restauradas.
- [ ] Exercitar restart, readiness, autorização, recuperação de reservas e limpeza sem perder identidade da PR ou liberar capacidade incerta.
- [ ] Registrar limites realmente configurados e o que foi validado; não apresentar a antiga task 060 ausente como evidência de capacidade.
- [ ] Manter configuração segura em exemplos e validar bundle/artefatos sem segredos.

## Validation

Production-smoke-tests e demo reproduzível de web/API com configuração de produção; registrar limitações externas restantes. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Migração de banco/provedor, alta disponibilidade e recriação automática de infraestrutura excluída.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.
