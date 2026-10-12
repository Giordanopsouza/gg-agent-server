---
id: 098-google-direct-oidc
feature: sqlite-modal
status: done
depends_on: ["097-sqlite-local-sessions"]
---

# Task 098: Login Google direto

**Descrição:** Implementar provedor Google OIDC e rotas atuais com Code+PKCE, substituindo Supabase na aplicação candidata; testar callbacks com tokens assinados controlados.

**Critérios de aceitação:**

- [x] state, nonce, PKCE e vínculo ao navegador; fluxo de dez minutos consumido atomicamente uma vez, inclusive com callbacks concorrentes.
- [x] Validar assinatura/JWKS, emissor, audiência, expiração, nonce e email_verified; sub determina identidade; aceitar qualquer conta Google válida.
- [x] Preservar rotas, redirect seguro e cookies HttpOnly/Secure/SameSite=Lax; callback, start persistente e logout só respondem após checkpoint, com 503 e retry seguro.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_google_auth.py backend/tests/test_web_auth.py`.
- [x] Demo/check operacional: Testar sucesso, replay, expiração, falta de browser binding, claims inválidas, rotação de JWKS e falha de persistência.

**Dependências:** [097-sqlite-local-sessions](097-sqlite-local-sessions.md).

**Arquivos prováveis:**

- `backend/gg/runtime/google_auth.py (novo)`
- `backend/gg/runtime/web_auth.py`
- `backend/gg/runtime/config.py`
- `backend/tests/test_web_auth.py`
- `backend/tests/test_google_auth.py (novo)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

## Evidência — 2026-10-08

- `GoogleAuth` implementa Code+PKCE S256, state/nonce e cookie de vínculo ao navegador. Migração 6 persiste fluxo de dez minutos; claim SQLite precede a troca de código e passa pelo checkpoint. Perfil e sessão são gravados juntos na conclusão.
- RS256/JWKS, emissor, audiência/azp, expiração, nonce, sub e email_verified são verificados. Rotação de JWKS também funciona imediatamente após um cache válido. Não há restrição por domínio nem refresh Google nas consultas de sessão.
- 26 testes novos cobrem rotas HTTP com JWTs RSA controlados, concorrência com duas instâncias do provedor, assinatura falsa, claims inválidas, binding, expiração, cancelamento, redirect seguro, cookies, replay após sucesso/restore e falhas dos checkpoints start/claim/conclusão/logout.
- Retry de conclusão não confirmada recupera o mesmo token opaco, derivado de um segredo aleatório do navegador; DB contém somente seu hash. Callback já confirmado ou restaurado é rejeitado. Se o processo interrompe após claim, iniciar novo login: nunca repetir a troca de um código cujo consumo é incerto. Uma confirmação posterior por outro checkpoint também pode exigir novo login.
- Arquivos de implementação/teste: `google_auth.py`, `web_auth.py`, `config.py`, `sqlite_migrations.py`, `test_google_auth.py` (5). Rotas legadas preservadas até a 101.
- Configuração nova: `GG_GOOGLE_CLIENT_ID`, `GG_GOOGLE_CLIENT_SECRET` e `GG_WEB_ORIGIN`. Contrato conferido na [documentação Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect).
- Grupo 097–099: 30 testes novos aprovados. QA executado em ordem: `make format-fix`, `make lint-fix`, `make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests`; resultado amplo **314 passed, 92 skipped, 2 deselected**. Skips legados dependem de Postgres ausente; não são prova de compatibilidade completa com o backend antigo.
- `make build` aprovou sdist/wheel de gg-sdk, gg-backend e gg-sandbox; `git diff --check` limpo. Instalação não editável foi reconstruída antes do QA para incorporar módulos novos.
- Limite da prova: candidato SQLite e HTTP in-process com transportes controlados, snapshots locais e fronteira de despacho simulada. Sem login Google humano, Volume real ou tarefa frontend→runtime→Modal. Primeiro pré-requisito ausente para esse E2E é o wiring SQLite da 101, que depende também da conexão GitHub SQLite da 100. A skill local-stack foi consultada; o app publicado continua usando o wiring antigo. A autorização condicional para 101 fica registrada, mas não foi necessário antecipá-la para comprovar estas três fatias.
