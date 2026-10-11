# SQLite e Google direto no Modal, com remoção completa do Supabase

## Resultado esperado

O produto passa a funcionar em um único servidor Modal, entregando frontend React e API na mesma URL. SQLite será a persistência da aplicação, tanto no servidor central quanto nos sandboxes.

Decisões confirmadas:

- Login Google direto, aberto a qualquer conta Google, com dados privados por usuário.
- Banco novo, sem importar usuários, tarefas, histórico ou conexões antigos.
- Frontend e backend saem do Railway e passam para Modal.
- Após validar o novo produto e guardar um backup final, parar os serviços Railway e excluir o projeto Supabase.
- Os usuários entram novamente e reconectam GitHub e OpenRouter.

## Arquitetura e persistência

**Servidor central**

- Criar a aplicação Modal `gg-runtime`, com um servidor sempre ativo, um worker Uvicorn e `min_containers=1`, `max_containers=1`. Manter o limite atual de dez sandboxes simultâneos.
- Usar SQLite em disco local, separado do Modal Volume. Configurar `journal_mode=WAL`, `synchronous=FULL`, `foreign_keys=ON` e espera por lock de dez segundos.
- Usar `sqlite3` e SQL direto. Remover SQLAlchemy, Psycopg e Alembic; versionar o schema com migrações SQLite sequenciais e `PRAGMA user_version`.
- Preservar os contratos atuais de tarefas, reservas, supervisão, recibos, resultados, publicação e retenção. Manter idempotência por usuário e sequências monotônicas, inclusive após expirar registros.
- Guardar também usuários, sessões, fluxos OAuth, instalações GitHub e credenciais cifradas no mesmo banco. Todas as escritas passam pelo mesmo mecanismo transacional e de controle de alterações.
- Substituir as políticas Postgres por consultas explicitamente limitadas ao usuário autenticado. A chave de operador continua exclusiva dos clientes administrativos.

**Checkpoints**

- Criar o Volume `gg-runtime-state` e o Secret `gg-runtime-config`. O volume contém snapshots completos; o SQLite ativo permanece local.
- Produzir snapshots com `sqlite3.backup()`, arquivo temporário e publicação seguida de `Volume.commit()`. Serializar os checkpoints e conservar alterações feitas enquanto o commit está em andamento.
- Confirmar persistência antes de responder às operações que alteram estado, incluindo callbacks OAuth e logout. Fazer checkpoint de atividade de fundo a cada dois segundos quando houver alterações.
- Persistir intenções antes de criar sandboxes, iniciar execuções ou entregar mensagens. Preservar as identidades utilizadas para reconciliar efeitos externos sem duplicação.
- Se o checkpoint falhar, retornar `503` nas operações dependentes de persistência e suspender novos efeitos externos até recuperar.
- Inicializar o banco vazio por comando explícito, antes do primeiro deploy. Depois disso, snapshot ausente, corrompido ou incompatível bloqueia a inicialização.
- Na recuperação, restaurar o snapshot e reconciliar sandboxes e reservas antes de admitir trabalho novo.

Esse desenho segue a separação entre SQLite local e snapshots usada pelo Moyai. O WAL exige acesso no mesmo host. [Documentação do SQLite](https://www.sqlite.org/wal.html).

## Mudanças na aplicação

**Login e credenciais**

- Substituir o cliente Supabase Auth por Google OpenID Connect, preservando `/auth/google/start`, `/auth/google/callback`, `/auth/session` e `/auth/logout`.
- Usar Authorization Code com PKCE, `state`, `nonce` e vínculo com o navegador. Fluxos expiram em dez minutos e são consumidos uma única vez.
- Validar assinatura, emissor, audiência, expiração, nonce e email verificado. Identificar a conta pelo `sub` do Google, associado a um UUID local; email não determina propriedade.
- Criar sessões locais de sete dias, com token aleatório no cookie e somente seu hash no SQLite. Preservar cookies `HttpOnly`, `Secure`, `SameSite=Lax` e verificação de origem nas mutações.
- Validar requisições autenticadas pelo SQLite, sem consultar Google a cada chamada. Logout revoga a sessão local.
- Preservar a cifra Fernet, versões das credenciais, autorização de repositórios e tokens GitHub limitados à tarefa. Segredos ficam no Modal Secret, separados dos snapshots.

O login seguirá o fluxo oficial de [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect).

**Sandboxes e eventos**

- Criar um SQLite por sandbox para metadados das conversas, eventos, recibos, execuções, resultados e intenções de publicação atualmente mantidos em arquivos JSON.
- Usar journal `DELETE`, transações curtas, chaves estrangeiras e espera por lock. Gravar identidade de execução e vínculo com `start_key` atomicamente.
- Preservar os formatos HTTP/WebSocket e os modelos Pydantic compartilhados. Cada componente mantém sua implementação de persistência, respeitando a separação entre SDK, runtime e sandbox.
- Adicionar `after` e `limit` à leitura de eventos do sandbox. Sem parâmetros, preservar o comportamento atual; a supervisão passa a solicitar páginas de até 200 eventos novos.
- Persistir o cursor por tarefa e conversa. Inserir cada página no banco central em uma transação, mantendo deduplicação e limites de evidência.
- Consultar diretamente tarefas candidatas à execução e manutenção, evitando carregar todo o histórico a cada ciclo do scheduler.
- Código dos repositórios, artefatos e arquivos nativos do Pi continuam como arquivos. O SQLite substitui os registros de estado controlados pela aplicação; não modifica o formato interno do Pi.

**Frontend e ferramentas**

- Empacotar o build React no servidor FastAPI, preservando rotas da API, WebSocket e navegação da interface. Retirar o proxy Node usado em produção.
- Usar a URL HTTPS real do Modal como origem pública e callback. Aceitar o hostname encaminhado pelo proxy somente quando corresponder à origem configurada.
- Remover configurações, certificados, dependências e comandos ativos de Supabase/Postgres. Atualizar lockfile, documentação, instruções locais e ADRs.
- Disponibilizar comandos Makefile para inicialização, migração, backup, restauração e deploy Modal. Atualizar os testes para bancos SQLite temporários, sem serviços externos necessários aos testes unitários.

## Validação

- **Persistência:** concorrência entre conexões, rollback, reserva dentro da capacidade, idempotência por usuário, sequências, retenção e recuperação após reinício.
- **Autenticação:** callback válido, replay, fluxo expirado, token inválido, logout, sessão revogada e isolamento entre dois usuários.
- **Credenciais:** cifra e versões preservadas, usuário sem acesso às credenciais de outro e respostas sem conteúdo secreto.
- **Snapshots:** restauração com alterações presentes no WAL, falha de commit, escrita durante checkpoint e ausência de confirmação antes da persistência.
- **Sandboxes:** eventos e recibos preservados após reinício, leitura por cursor e ausência de duplicação de execução, mensagem ou PR.
- **Interface:** login, conexão GitHub/OpenRouter, criação de tarefa, eventos, resultado e WebSocket na mesma origem.
- Rodar a sequência obrigatória: `make format-fix`, `make lint-fix`, `make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests`; também os testes e build do frontend.
- Exercitar uma tarefa real com dispatch habilitado localmente e no Modal. Exigir atividade, resposta que cumpra o pedido, resultado persistido e liberação da reserva. Repetir após reiniciar o servidor.
- Medir consultas, tráfego de sincronização e latência de confirmação incluindo o checkpoint. Registrar os resultados, sem pressupor um ganho percentual.

## Implementação e corte

1. Trabalhar no worktree dedicado `091-sqlite-modal`, preservando as alterações atuais do checkout principal.
2. Implementar banco central e Google direto; provar o fluxo local com contas e credenciais individuais.
3. Implementar SQLite nos sandboxes e sincronização incremental; publicar a nova imagem e executar uma tarefa real.
4. Implementar checkpoints e servidor Modal; usar deploy `recreate` para impedir sobreposição de escritores. Haverá interrupção breve durante a substituição do servidor. [Estratégias de deploy Modal](https://modal.com/docs/guide/managing-deployments).
5. Configurar Google OAuth, callbacks e webhook GitHub para a nova URL. Validar login, conexões, tarefa real e recuperação no ambiente publicado.
6. Antes do corte, pausar admissões no sistema antigo, concluir ou reconciliar trabalho pendente e exportar backup de dados da aplicação e Auth. Guardar as chaves de recuperação separadamente e verificar a restauração em ambiente isolado.
7. Direcionar o uso para Modal. Após a aceitação, parar frontend e backend Railway, remover configurações antigas e excluir o projeto Supabase.
8. Guardar o backup antigo como arquivo offline, sem importação automática. Depois que o novo sistema aceitar dados, recuperações usam seus próprios checkpoints; voltar ao banco antigo não será um rollback válido.

A configuração inicial mantém um único servidor e os limites atuais de retenção. Registros confirmados exigem checkpoint concluído; eventos de fundo ainda não salvos podem ser perdidos numa queda abrupta. O intervalo de dois segundos é uma tentativa de salvamento, não uma garantia máxima durante falhas.
