# TAREFAS - Trabalho C3.A2 (Plataforma de IA como Servico)

Este e o projeto integrador. Reaproveite o que voce fez em C1.A2 e C2.A2.

**Entrega: 26/11/2026** (−0,5 ponto por dia de atraso). Fonte maior da verdade:
[docs/edital-c3a2.md](docs/edital-c3a2.md). Contexto e decisões: [CLAUDE.md](CLAUDE.md).
Diário: [docs/implementacao.md](docs/implementacao.md).

Os itens 1 a 10 são os do kit do professor, com a numeração original. O que foi
acrescentado (fases, subitens, critérios de aceite) serve para acompanhar a implementação.
`R…` é o requisito do edital.

**Como usar:** marque `[x]` só quando o critério de aceite estiver verificado. Cada tarefa
termina com testes passando, revisão do advisor (ajustes aplicados), este arquivo e o
diário atualizados, e commit.

## Ordem de execução

Ordem ajustada por decisão do usuário em 26/11/2026: o deploy vem depois do código, para o
gateway nunca ficar público sem autenticação e haver uma única parada para o usuário.

| Ordem | Tarefa | Por que nesta ordem |
|-------|--------|---------------------|
| 1 | F1 Base da arquitetura | tudo depende dos serviços |
| 2 | 3 Dockerfiles e 4 Compose | comando único funcionando cedo |
| 3 | 1 JWT e 2 Rate limit | protege antes de publicar |
| 4 | 6 Resiliência | R5 |
| 5 | 7 Observabilidade | R5 |
| 6 | 5 Deploy e 8 HTTPS | depende de ações do usuário no painel |
| 7 | 9 LGPD, 10 Trade-offs, F2 README | descrevem o sistema pronto |
| 8 | F3 Verificação final | critério de pronto do edital |

## Fase 0 - Ambiente (preparação)

- [x] Material em `docs/` versionado (edital e ebook)
- [x] Código reaproveitado do C1.A2 e C2.A2 copiado sem alterações
- [x] Projeto `uv` (Python 3.12), um grupo de dependências por serviço, testes de sanidade
- [x] Imagens base baixadas e instalação por grupo testada em Docker
- [x] `CLAUDE.md` (raiz e subdiretórios), `.env.example` e este arquivo

### Pendências do usuário (necessárias a partir da Tarefa 5)

- [x] Conta no [Render](https://render.com) e CLI `render` autenticado
- [x] GitHub conectado ao Render, com o app instalado no repositório (confirmado pelo usuário;
      verificado de fato ao criar o Blueprint)
- [x] Conta no [Honeycomb](https://ui.honeycomb.io), região US
- [x] Na Tarefa 5, quando o Blueprint mostrar os campos no painel: criar a **Ingest API key** do
      Honeycomb e preenchê-la (decisão do usuário: não criar antes)
- [x] Depois do deploy, postar no AVA o link do repositório e o usuário e a senha do ambiente
      publicado

O banco publicado é criado pelo Blueprint na Tarefa 5 (não criar antes: expira em 30 dias).

## Núcleo obrigatório

### [x] F1. Base da arquitetura (R2, R9.3)

Gateway + serviço de inferência + worker de fila + armazenamento vetorial.
Detalhes no `CLAUDE.md` de cada diretório.

- [x] F1.1 `comum/`: ajustar `circuit_breaker.py` e `resiliencia.py` ao uso compartilhado
- [x] F1.2 `vetorial/`: `esquema.sql` (pgvector) e acesso a dados (escrita idempotente, busca)
- [x] F1.3 `inferencia/`: `app.py` com `/predict`, `/processar`, `/buscar`, `/perguntar`, `/saude`;
      embeddings de dimensão fixa; token interno
- [x] F1.4 `worker/`: consumo confiável da fila, dead-letter, chamada à inferência, gravação
      no pgvector, rota `/saude`
- [x] F1.5 `gateway/`: roteamento `/predict`, `/documentos`, `/tarefas/{id}`, `/buscar`,
      `/perguntar`, `/saude`, `/`
- **Aceite:** testes unitários de cada serviço passam sem rede, Docker ou chave de API.

### [x] 1. Autenticacao JWT no gateway (R6) - `gateway/`

Rota de login que emite o token e protecao das demais rotas (401 sem token). (Aula 16)

- [x] `POST /login` emite JWT com expiração; credenciais vindas de variável de ambiente
- [x] Todas as rotas de negócio exigem token; só `/`, `/saude`, `/login` e a documentação são abertas
- [x] Inferência e worker recusam chamadas sem o token interno
- **Aceite:** testes de 401 (sem token, inválido, expirado) e de 200 com token válido.

### [x] 2. Rate limit no gateway - `gateway/`

Limitar requisicoes por cliente por minuto. (Aula 8)

Não consta no edital nem na rubrica. Implementado por decisão do usuário (26/11/2026),
por ser núcleo do kit do professor.

- [x] Limite por cliente por minuto no Redis; 429 com `Retry-After`; IP nunca gravado em claro
- **Aceite:** testes de 429 ao estourar o limite e de liberação na janela seguinte.

### [x] 3. Dockerfile de cada servico (R3)

Um Dockerfile por servico. Use `Dockerfile.exemplo` como ponto de partida. (Aula 13)

- [x] `gateway/Dockerfile`, `inferencia/Dockerfile`, `worker/Dockerfile`, `vetorial/Dockerfile`
- [x] Dependências instaladas com `uv` a partir do `uv.lock`; `.dockerignore`
- [x] Remover `gateway/requirements.txt` e `Dockerfile.exemplo`, substituídos
- **Aceite:** `docker compose build` sem erros; apps rodam com usuário sem privilégios.

### [x] 4. docker-compose completo (R3)

O sistema inteiro deve subir com UM comando. (Aula 14)

- [x] `redis`, `vetorial`, `inferencia`, `worker`, `gateway`, `jaeger`, com healthchecks
- [x] Serviços se acham pelo nome; só `8000` (gateway) e `16686` (Jaeger) expostos
- **Aceite:** `docker compose up --build` num clone limpo, **sem `.env`**; teste e2e passa.

### [x] 5. Deploy em nuvem (free tier) (R4)

Publicar e informar a URL publica no README. (Aula 13)

- [x] `render.yaml` (Blueprint): gateway, inferência, worker e Key Value no Render
- [x] Armazenamento vetorial no Postgres gratuito do Render; traces no Honeycomb
- [x] Segredos só no painel; nada sensível no repositório
- [x] URL pública no README
- **Aceite:** fluxo completo (login → documento → tarefa → busca → pergunta) na URL pública,
  inclusive depois de os serviços terem dormido.
- Verificado em 26/11/2026. Depois de dormirem, os serviços precisam ser despertados por acesso
  externo: a raiz do gateway faz isso pelo navegador (ver o diário).

### [x] 6. Resiliencia (R5)

Tempo-limite, retentativa com espera progressiva e circuit breaker. (Aula 11)

- [x] Tempo-limite em toda chamada de rede (HTTP, Redis, Postgres, LLM)
- [x] Retentativa com backoff e jitter só para falha transitória em operação idempotente
- [x] Circuit breaker nas chamadas gateway→inferência, worker→inferência e inferência→LLM
- [x] Falha transitória não manda mensagem à dead-letter durante o cold start
- **Aceite:** testes automatizados e teste manual `docker compose stop inferencia`
  (503 elegante, disjuntor abre, fila se recupera ao religar).

### [x] 7. Observabilidade (R5)

Rastreamento distribuido cobrindo gateway -> fila -> worker. (Aula 15)

- [x] OpenTelemetry nos três serviços, `service.name` distinto
- [x] Contexto propagado **dentro da mensagem da fila** (`traceparent`)
- [x] `trace_id` nos logs; nenhum dado pessoal em spans ou logs
- **Aceite:** um único trace no Jaeger com gateway → fila → worker → inferência → banco;
  o mesmo no Honeycomb para o ambiente publicado.
- Verificado no Jaeger local e, em 26/11/2026, no Honeycomb com o ambiente publicado.

### [x] 8. HTTPS no servico publicado. (R6) (Aula 16)

- **Aceite:** URL `https://` responde com certificado válido e `http://` redireciona.
- Verificado em 26/11/2026 nos três serviços publicados.

### [x] 9. Secao de conformidade no README (R6)

Quais dados sao tratados, com qual finalidade e por quanto tempo. (LGPD, Aula 16)

- [x] Tabela dado → finalidade → onde fica → prazo, incluindo logs, traces, fila e terceiros
- [x] Todo prazo declarado é de fato aplicado (expurgo e TTL implementados e testados)
- [x] Revisão dos logs: nenhum dado pessoal gravado (roteiro do edital, item 4)

### [x] 10. Relatorio de trade-offs (R7)

CAP, custo e latencia do seu sistema.

- [x] `docs/trade-offs.md`, curto, ligado no README
- [x] Latências **medidas** (local e publicado, com e sem cold start), não estimadas

### [x] F2. README do projeto (R9.2)

- [x] Arquitetura (diagrama), como executar do zero, rotas com exemplos, variáveis de ambiente
- [x] URL pública, LGPD, trade-offs; aviso de que as credenciais do ambiente publicado
      são informadas ao professor no AVA (**sem** colocá-las no repositório)
- [x] Aviso de que, no ambiente publicado, a primeira requisição após inatividade pode levar
      de 1 a 2 minutos
- [x] Créditos ao kit do Prof. Howard Roatti

### [x] F3. Verificação final e entrega (R9)

- [x] Remover `referencia/` e os `README.md` de espera em `inferencia/` e `worker/`
- [x] Clone em OUTRA máquina (ou diretório limpo) e rode o comando unico seguindo só o README
- [x] A URL publica esta no ar?
- [x] Usuário confirmou a postagem do link e das credenciais no AVA
- [x] Toda configuracao esta em variavel de ambiente (nada fixo no codigo)?
- [x] Os logs estao livres de dados pessoais?
- [x] `uv run pytest`, `uv run pytest -m e2e` e `uv run ruff check .` verdes
- [x] Commits enviados ao GitHub
- [x] Lembrar o usuário da entrega no AVA (link do repositório e credenciais)

## Extensoes opcionais (R8) - DISPENSADAS

Não valem nota. Dispensadas por decisão do usuário; não implementar sem pedido.

- Autoescalonamento de workers conforme o tamanho da fila
- Componente serverless ou na borda
- CI/CD publicando automaticamente a cada commit
- Painel de metricas
- Manifests de Kubernetes

Também fora de escopo: interface gRPC do C1.A2 (REST e mensageria já cobrem a comunicação)
e qualquer melhoria do modelo de IA (não pontua).
