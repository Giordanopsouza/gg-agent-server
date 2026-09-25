---
id: 074-web-production-configuration
feature: mvp-web
status: pending
depends_on: [061-google-login-and-sessions, 078-runtime-postgres-migration]
---

# Configuração de produção do MVP web

## Scope

Documentar e exercitar a montagem web/API na mesma origem com HTTPS, migrações e recuperação segura do estado do MVP.

## Acceptance criteria

- [ ] Servir build web e API na mesma origem, com callbacks Supabase/Google e configuração GitHub coerentes, cookie Secure, CSRF e roteamento de reload funcionando.
- [ ] Documentar variáveis públicas/privadas, cliente OAuth, App/webhook/permissões, chave de criptografia, imagem/app Modal e repo de teste autorizado.
- [ ] Atualizar runbook de migração, operação administrativa, revogação e rotação de credenciais; não distribuir chave administrativa ao browser.
- [ ] Ensaiar backup/restore do Postgres em ambiente isolado, cobrindo ownership, referências e credenciais cifradas. Definir RPO/RTO, verificar cobertura de Auth no método contratado e forçar nova autenticação após recuperação; guardar chave de criptografia separadamente. Se houver objetos no Storage, testar backup/restore deles separadamente.
- [ ] Exercitar restart, readiness, autorização, recuperação de reservas e limpeza sem perder identidade da PR ou liberar capacidade incerta.
- [ ] Registrar limites realmente configurados e o que foi validado; não apresentar a antiga task 060 ausente como evidência de capacidade.
- [ ] Manter configuração segura em exemplos e validar bundle/artefatos sem segredos.

- [ ] Disponibilizar staging desde o início, com projeto Supabase e credenciais separados de produção, mesma imagem/build e migrações versionadas. Features ainda incompletas ficam fechadas. A 075 valida depois a configuração final com todas as integrações.
- [ ] Publicar entrada HTTPS com domínio e certificado válido apontando para o IP do servidor; IP/porta isolados não são o critério de entrega. Configurar proxy, redirects permitidos, cookies, CORS/Origin, callback Supabase e OAuth Google real; nenhuma conexão pública direta ao banco.
- [ ] Pipeline aplica migrações uma vez, executa readiness e smoke na URL publicada, e promove o mesmo artefato aprovado. Ensaiar rollback da aplicação com schema compatível; não restaurar snapshot antigo sobre novas escritas como rollback automático.
- [ ] Disponibilizar logs estruturados com correlação request/task, métricas de erro/fila/latência, alertas acionáveis e procedimento para interromper admissões; comprovar uma falha e sua detecção sem vazar prompts ou segredos.

## Validation

Production-smoke-tests e demo reproduzível de web/API com configuração de produção; registrar limitações externas restantes. Seguir os comandos de QA do [índice](README.md#validação-e-conclusão).

## Out of scope

Implementação da migração (078), alta disponibilidade e recriação automática de infraestrutura excluída.

## Log

### [PA] 2026-09-25 16:16 -03 — Grooming

Task derivada do plano do MVP web. Escopo, dependências e prova de conclusão definidos; implementação ainda não iniciada.

### [PA] 2026-09-25 — Revisão para produção com Supabase

Plano atualizado por solicitação do usuário: Supabase Auth/Postgres, isolamento e provas no ambiente publicado. Critérios continuam pendentes; esta revisão não implementa nem valida o serviço.
