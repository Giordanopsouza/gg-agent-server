# Task 123: onboarding publicado — estado em 2026-10-08

## Decisão operacional do usuário

Em 2026-10-08, o usuário decidiu manter Google OAuth **External / Testing**
enquanto somente ele utiliza o produto. Publicação do OAuth e preparação de
documentos para o lançamento público ficam adiadas; a configuração Modal e
as provas reais continuam no escopo. Termos de uso não serão adicionados nesta
etapa. Nenhuma mudança para **In production** foi executada.

Correção da interpretação anterior: `google_auth.py` solicita apenas
`openid email`. A [documentação oficial do Google](https://support.google.com/cloud/answer/15549945?hl=en)
explica que autenticação com esses escopos básicos é uma exceção às restrições
gerais de Testing: não exige inclusão na lista de testes, não apresenta o
aviso correspondente e não tem expiração de autorização após sete dias.
A mensagem genérica do console não prova que somente os dois test users podem
usar nosso login. Também não foi demonstrado que o campo de privacy policy,
isoladamente, causa o botão de publicação desabilitado.

## Destino verificado

- Ambiente Modal isolado `sqlite-111-proof`; URL obtida do deploy anterior:
  `https://giordanowrk-sqlite-111-proof--gg-runtime-runtime.us-east.modal.direct`.
- `modal app list --env sqlite-111-proof --json`: `gg-runtime` parado;
  `gg-runtime-operations` implantado. `modal app history gg-runtime` mostra
  versão mais recente v4 às 14:39 PDT. `GET /health` da URL de prova retorna
  HTTP 503 enquanto o app está parado. Não houve deploy nesta verificação.
- `modal environment list`: `main` e `sqlite-111-proof`; em `main` só a app
  `gg-agent-sandboxes` está implantada e não existe Secret de runtime. O
  Secret `gg-runtime-config` existe no ambiente de prova; valores não foram
  exibidos.

## Configuração externa ainda pendente

- Google Cloud, projeto `gglabs-504618`, app `GGlabs`: público **External**,
  status **Testing**, mantido por decisão do usuário. A tela mostra dois test
  users e desabilita **Publish app** até completar Branding; a exceção de
  autenticação básica descrita acima aplica-se aos escopos do código atual.
- Branding mostra app name e contato. `https://gglabs.ventures` foi salva como
  Application home page antes de 15:33 PDT; privacy policy e terms permanecem em
  branco conforme a orientação de não adicionar termos agora. Após salvar a
  homepage, **Publish app** continuou desabilitado com instrução de completar
  Branding. O cliente web `GGAgent server` tem somente o callback
  local `http://127.0.0.1:5174/auth/google/callback`; não consta a URL Modal.
  A URL pública correta para acrescentar é a origem acima mais
  `/auth/google/callback`. A configuração não foi salva.
- No Dia, GitHub Apps mostra `gg-agent-main-giordanopsouza`. A primeira
  verificação GitHub Mobile expirou; a confirmação posterior liberou sudo mode
  e permitiu ler a configuração. Homepage e webhook apontam para
  `https://gg-web-production.up.railway.app`; o único callback OAuth aponta
  para `http://127.0.0.1:5174/auth/github/callback`. Existe um webhook secret
  configurado. Nenhum endereço foi
  alterado enquanto o runtime Modal de prova está parado.
- A worktree recebeu alterações de código de outra atividade durante esta
  verificação. O deploy de uma árvore ainda em edição não foi iniciado.
- Um read-back isolado da presença de variáveis no Secret Modal foi iniciado,
  mas a Function não chegou a executar durante a janela de espera; a chamada
  foi cancelada e o app temporário `gg-runtime-config-check` terminou parado.
  Nenhum valor de Secret foi exibido. Esse read-back segue pendente.

## Provas disponíveis e próximo limite

- `make frontend-test`: 15 passed; `make frontend-build`: passou.
- Ainda faltam read-back de Secret sem valores, callbacks e webhook na URL
  Modal, duas sessões humanas,
  OpenRouter/GitHub com repo privado, e tarefa publicada com eventos HTTP/WS,
  resposta, manifest/checks e reserva liberada. Nenhuma dessas provas pode
  ser inferida do smoke local ou do estado anterior do ambiente de prova.
- Publicação do OAuth e documentos de lançamento foram adiados pelo usuário;
  a URL de privacy policy não é tratada como bloqueio para a prova atual em
  Testing. O acesso GitHub sudo mode foi resolvido; a troca do webhook aguarda runtime
  Modal ativo e verificado, para evitar entregas ao endpoint 503.
