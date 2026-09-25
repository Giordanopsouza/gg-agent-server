---
id: 065-github-account-and-app-connection
feature: mvp-web
status: pending
depends_on: [061-google-login-and-sessions, 063-personal-openrouter-credentials]
---

# Conexão da conta GitHub e instalação da App

## Migration preflight

Ler o [plano do MVP](../mvp-web-plan.md), os ADRs [0001](../adr/0001-modal-background-tasks.md), [0002](../adr/0002-general-background-tasks.md) e [0003](../adr/0003-remove-legacy-learning-surfaces.md), o AGENTS.md do componente e as tasks diretamente dependentes/consumidoras. Registrar estado final, pontes temporárias com legado, responsável pela remoção e teste que protege a fronteira. Inspecionar o cliente GitHub e a configuração do runtime. Guardar chave privada da App apenas no host e proteger os tokens pessoais necessários ao vínculo usando o padrão de cofre da 063.

## Scope

Vincular a identidade GitHub à sessão Google e registrar instalações verificadas da GitHub App.

## Acceptance criteria

- [ ] Implementar início/callback de autorização com state vinculado à sessão e associação por identidade verificada, nunca por coincidência de email.
- [ ] Verificar no GitHub a relação entre usuário e instalação; installation_id enviado pelo browser não concede acesso.
- [ ] Expor status da conexão, instalações disponíveis e desconexão/reconexão sem retornar tokens; preservar isolamento entre contas.
- [ ] Tratar autorização de organização pendente, instalação removida e autorização revogada com estado recuperável.
- [ ] Verificar assinatura e deduplicar entregas dos webhooks usados para invalidar acesso; definir comportamento quando chegam fora de ordem.
- [ ] Documentar callbacks, webhook, permissões mínimas e o fato de operações com token de instalação aparecerem atribuídas à App.
- [ ] Testar callbacks forjados, vínculo de outra conta, webhook inválido/repetido e desconexão.

## Validation

Testes HTTP com GitHub controlado e roteiro opt-in de conexão real da App; não requerer instalação paga nos testes comuns. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Seleção de repositório/branch e emissão do token da tarefa (066), GitLab e contas de equipe.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.
