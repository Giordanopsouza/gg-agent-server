# MVP: testes e critérios de liberação para produção

Status: especificação pendente de implementação. Targets novos devem ser criados nas tasks responsáveis; os nomes abaixo descrevem suítes, não comandos já disponíveis.

## Estratégia

Testar o caminho de uma pessoa usando o produto. Aumentar quantidade de testes unitários não substitui integração, browser e recuperação. Supabase local permite testar o mesmo tipo de banco sem gastar recursos por caso; staging separado comprova serviços externos e configuração publicada.

| Nível | Quando / responsável | Prova e bloqueio |
|---|---|---|
| Rápido e determinístico | Toda PR; cada task | Contratos HTTP, regras, UI, erros e fronteira SDK; provedores caros controlados. Falha bloqueia merge. |
| Integração Supabase local | Toda PR de Auth, dados ou runtime; 077/078/061/062 | Migração vazia e upgrade, Auth, permissões reais, constraints, concorrência em conexões distintas e restart. Falha bloqueia merge. |
| Browser no staging HTTPS | Candidato a release; 074/075 | Duas contas, onboarding, fluxo até PR e continuação, mobile e falhas. Mesma imagem e migrações de produção; dados/credenciais separados. Falha bloqueia promoção. |
| Smoke após deploy | Cada release; 074/075 | URL externa, assets/reload, readiness, login/sessão e leitura/escrita de conta sintética isolada. Falha interrompe promoção e aciona recuperação documentada. Execução paga requer opt-in. |

## Matriz mínima

| Risco | Teste da superfície real | Responsável |
|---|---|---|
| Login só funciona localmente | Google → Supabase → callback HTTPS → reload → refresh → logout; cancelamento e sessão expirada | 061, 074 |
| Vazamento entre contas | A cria tarefa; B tenta lista, detalhe, evento, resultado, recibo, mensagem, retry, cancel e continuação; testar Data API sem privilégio e cofre privado | 062, 063, 075 |
| Dados somem no deploy | Criar histórico, redeploy/restart sem SQLite/volume local e consultar o mesmo registro | 078, 074 |
| Duplicação e custo inesperado | Timeout/reenvio concorrente; um registro por chave; limite por conta/global, reserva incerta e limpeza | 062, 073, 078 |
| Callback e segredos expostos | CSRF/Origin, redirect indevido, cookie Secure/HttpOnly, conta revogada; inspeção de build, URL e logs com segredos sintéticos | 061, 063, 074 |
| Integração indisponível | Auth/Postgres/OpenRouter/GitHub falham; UI explica e preserva rascunho; nenhum fallback administrativo ou criação duplicada | Tasks da integração, 075 |
| PR não cumpre o pedido | Conferir diff e resultado de testes contra um prompt com comportamento observável; validar repo/head/base e ajuste na mesma PR | 067, 071, 075 |
| Recuperação aparente | Restaurar backup em ambiente isolado; conferir dados/relações, recuperar reserva e exigir nova sessão; medir RPO/RTO | 074, 078 |
| Interface inviável no celular | Browser em 360/390/768/1440 px, teclado/foco, histórico, composer, erros e reload | 068–072, 075 |
| Capacidade não medida | Carga HTTP em staging com limites definidos antes do ensaio; registrar p95, erros, conexões e fila; executar uma prova paga limitada separadamente | 073, 075 |

Não executar carga, resets ou fixtures destrutivas em produção. Testes Google reais podem exigir interação humana; registrar o roteiro e resultado, sem contornar desafios do provedor. Playwright pode cobrir o restante do browser com contas de teste Supabase, mas isso não comprova o fluxo Google.

## Eficiência e evidência

- Usar fixtures pequenas, dados sintéticos identificados por run e limpeza garantida em falha. Testes comuns não dependem de credenciais pessoais nem serviços pagos.
- Automatizar cenários determinísticos de maior risco; reservar poucas execuções reais para contratos externos, sandbox e qualidade da PR. Evitar sleeps fixos; aguardar estados com prazo e evidência de timeout.
- Executar QA do AGENTS.md e integrar suítes ao Makefile raiz. Na implementação de cada feature, usar local-stack e conferir eventos, resultado e cumprimento do prompt.
- Cada aceite liga critério → comando/roteiro → resultado → commit/build → ambiente/schema → data. Capturas/traces devem ser sanitizados. Mock, simulação e validação externa ficam identificados.
- Definir antes da carga os limites de lançamento e os valores aceitos de latência/erros, conforme infraestrutura configurada. Não inventar capacidade de dez sandboxes; reduzir o limite anunciado se a prova falhar.

## Porta de entrada do produto

Domínio HTTPS apontando para o IP de hospedagem, frontend/API na mesma origem e callbacks permitidos. Staging e produção têm projetos Supabase e segredos próprios. O produto só abre criação de tarefas após ownership, integrações e limites passarem. Billing e organizações ficam para depois; retenção, remoção de conta/dados e canal de suporte precisam de procedimento documentado antes da abertura pública, preservando a reconciliação de execuções ativas.
