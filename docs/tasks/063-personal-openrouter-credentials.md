---
id: 063-personal-openrouter-credentials
feature: mvp-web
status: pending
depends_on: [061-google-login-and-sessions]
---

# Cofre pessoal OpenRouter

## Scope

Permitir validar, salvar, substituir e remover a chave OpenRouter de cada usuário por uma API autenticada.

## Acceptance criteria

- [ ] Validar a chave no backend via GET /api/v1/key e distinguir chave inválida, indisponibilidade e limite do provedor; falha não destrói uma chave válida já salva.
- [ ] Persistir no Supabase Postgres segredo cifrado e versão/referência de credencial por proprietário; responder apenas status e máscara.
- [ ] Substituição e remoção são autorizadas pela sessão e protegidas contra CSRF; uma conta não consulta nem altera a credencial de outra.
- [ ] Documentar que validação não reserva saldo nem garante disponibilidade de todos os modelos.
- [ ] Definir rotação/remoção para novas execuções e comportamento de execuções ativas, sem prometer revogação instantânea de segredo já entregue.
- [ ] Aplicar redação nos erros e logs dessa API; impedir segredo em URL, resposta, localStorage ou payload público de tarefa.
- [ ] Testar isolamento, cifragem em repouso, erro do provedor, substituição, remoção e ausência do segredo nas saídas.

- [ ] Negar acesso ao cofre pela Data API e pelos papéis anon/authenticated; chave de criptografia e secret/service_role ficam fora do banco e do bundle. Testar permissões reais além da API FastAPI.

## Validation

Testes da API com OpenRouter controlado e inspeção do Postgres comprovando ausência de chave em texto simples. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Dispatch (064), cobrança, múltiplos provedores e gerenciamento de saldo.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.

### [PA] 2026-09-25 — Revisão para produção com Supabase

Plano atualizado por solicitação do usuário: Supabase Auth/Postgres, isolamento e provas no ambiente publicado. Critérios continuam pendentes; esta revisão não implementa nem valida o serviço.
