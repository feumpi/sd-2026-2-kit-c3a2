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

| Ordem | Tarefa | Por que nesta ordem |
|-------|--------|---------------------|
| 1 | F1 Base da arquitetura | tudo depende dos serviços |
| 2 | 3 Dockerfiles e 4 Compose | comando único funcionando cedo |
| 3 | 5 Deploy e 8 HTTPS | "publique cedo, ainda que incompleto" (edital) |
| 4 | 1 JWT e 2 Rate limit | protege o que já está público |
| 5 | 6 Resiliência | R5 |
| 6 | 7 Observabilidade | R5 |
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
- [ ] GitHub conectado ao Render (só pelo navegador):
      [Account Security](https://dashboard.render.com/u/settings#account-security) →
      *Git Deployment Credentials* → *Add credential* → GitHub; depois
      [dar acesso](https://github.com/apps/render/installations/new) apenas a este repositório
- [x] Conta no [Honeycomb](https://ui.honeycomb.io), região US
- [ ] Criar uma **Ingest API key** (Environments → Manage Environments → API Keys → Ingest);
      ela só aparece uma vez e será colada no painel do Render na Tarefa 5
- [ ] Depois do deploy, enviar usuário e senha do ambiente publicado ao professor por e-mail

O banco publicado é criado pelo Blueprint na Tarefa 5 (não criar antes: expira em 30 dias).

## Núcleo obrigatório

### [ ] F1. Base da arquitetura (R2, R9.3)

Gateway + serviço de inferência + worker de fila + armazenamento vetorial.
Detalhes no `CLAUDE.md` de cada diretório.

- [ ] F1.1 `comum/`: ajustar `circuit_breaker.py` e `resiliencia.py` ao uso compartilhado
- [ ] F1.2 `vetorial/`: `esquema.sql` (pgvector) e acesso a dados (escrita idempotente, busca)
- [ ] F1.3 `inferencia/`: `app.py` com `/predict`, `/processar`, `/buscar`, `/perguntar`, `/saude`;
      embeddings de dimensão fixa; token interno
- [ ] F1.4 `worker/`: consumo confiável da fila, dead-letter, chamada à inferência, gravação
      no pgvector, rota `/saude`
- [ ] F1.5 `gateway/`: roteamento `/predict`, `/documentos`, `/tarefas/{id}`, `/buscar`,
      `/perguntar`, `/saude`, `/`
- **Aceite:** testes unitários de cada serviço passam sem rede, Docker ou chave de API.

### [ ] 1. Autenticacao JWT no gateway (R6) - `gateway/`

Rota de login que emite o token e protecao das demais rotas (401 sem token). (Aula 16)

- [ ] `POST /login` emite JWT com expiração; credenciais vindas de variável de ambiente
- [ ] Todas as rotas de negócio exigem token; só `/`, `/saude`, `/login` e a documentação são abertas
- [ ] Inferência e worker recusam chamadas sem o token interno
- **Aceite:** testes de 401 (sem token, inválido, expirado) e de 200 com token válido.

### [ ] 2. Rate limit no gateway - `gateway/`

Limitar requisicoes por cliente por minuto. (Aula 8)

Não consta no edital nem na rubrica. Implementado por decisão do usuário (26/11/2026),
por ser núcleo do kit do professor.

- [ ] Limite por cliente por minuto no Redis; 429 com `Retry-After`; IP nunca gravado em claro
- **Aceite:** testes de 429 ao estourar o limite e de liberação na janela seguinte.

### [ ] 3. Dockerfile de cada servico (R3)

Um Dockerfile por servico. Use `Dockerfile.exemplo` como ponto de partida. (Aula 13)

- [ ] `gateway/Dockerfile`, `inferencia/Dockerfile`, `worker/Dockerfile`, `vetorial/Dockerfile`
- [ ] Dependências instaladas com `uv` a partir do `uv.lock`; `.dockerignore`
- [ ] Remover `gateway/requirements.txt` e `Dockerfile.exemplo`, substituídos
- **Aceite:** `docker compose build` sem erros; apps rodam com usuário sem privilégios.

### [ ] 4. docker-compose completo (R3)

O sistema inteiro deve subir com UM comando. (Aula 14)

- [ ] `redis`, `vetorial`, `inferencia`, `worker`, `gateway`, `jaeger`, com healthchecks
- [ ] Serviços se acham pelo nome; só `8000` (gateway) e `16686` (Jaeger) expostos
- **Aceite:** `docker compose up --build` num clone limpo, **sem `.env`**; teste e2e passa.

### [ ] 5. Deploy em nuvem (free tier) (R4)

Publicar e informar a URL publica no README. (Aula 13)

- [ ] `render.yaml` (Blueprint): gateway, inferência, worker e Key Value no Render
- [ ] Armazenamento vetorial no Postgres gratuito do Render; traces no Honeycomb
- [ ] Segredos só no painel; nada sensível no repositório
- [ ] URL pública no README
- **Aceite:** fluxo completo (login → documento → tarefa → busca → pergunta) na URL pública,
  inclusive depois de os serviços terem dormido.

### [ ] 6. Resiliencia (R5)

Tempo-limite, retentativa com espera progressiva e circuit breaker. (Aula 11)

- [ ] Tempo-limite em toda chamada de rede (HTTP, Redis, Postgres, LLM)
- [ ] Retentativa com backoff e jitter só para falha transitória em operação idempotente
- [ ] Circuit breaker nas chamadas gateway→inferência, worker→inferência e inferência→LLM
- [ ] Falha transitória não manda mensagem à dead-letter durante o cold start
- **Aceite:** testes automatizados e teste manual `docker compose stop inferencia`
  (503 elegante, disjuntor abre, fila se recupera ao religar).

### [ ] 7. Observabilidade (R5)

Rastreamento distribuido cobrindo gateway -> fila -> worker. (Aula 15)

- [ ] OpenTelemetry nos três serviços, `service.name` distinto
- [ ] Contexto propagado **dentro da mensagem da fila** (`traceparent`)
- [ ] `trace_id` nos logs; nenhum dado pessoal em spans ou logs
- **Aceite:** um único trace no Jaeger com gateway → fila → worker → inferência → banco;
  o mesmo no Honeycomb para o ambiente publicado.

### [ ] 8. HTTPS no servico publicado. (R6) (Aula 16)

- **Aceite:** URL `https://` responde com certificado válido e `http://` redireciona.

### [ ] 9. Secao de conformidade no README (R6)

Quais dados sao tratados, com qual finalidade e por quanto tempo. (LGPD, Aula 16)

- [ ] Tabela dado → finalidade → onde fica → prazo, incluindo logs, traces, fila e terceiros
- [ ] Todo prazo declarado é de fato aplicado (expurgo e TTL implementados e testados)
- [ ] Revisão dos logs: nenhum dado pessoal gravado (roteiro do edital, item 4)

### [ ] 10. Relatorio de trade-offs (R7)

CAP, custo e latencia do seu sistema.

- [ ] `docs/trade-offs.md`, curto, ligado no README
- [ ] Latências **medidas** (local e publicado, com e sem cold start), não estimadas

### [ ] F2. README do projeto (R9.2)

- [ ] Arquitetura (diagrama), como executar do zero, rotas com exemplos, variáveis de ambiente
- [ ] URL pública, LGPD, trade-offs; aviso de que as credenciais do ambiente publicado
      foram enviadas ao professor por e-mail (**sem** colocá-las no repositório)
- [ ] Aviso de que, no ambiente publicado, a primeira requisição após inatividade pode levar
      de 1 a 2 minutos
- [ ] Créditos ao kit do Prof. Howard Roatti

### [ ] F3. Verificação final e entrega (R9)

- [ ] Remover `referencia/` e os `README.md` de espera em `inferencia/` e `worker/`
- [ ] Clone em OUTRA máquina (ou diretório limpo) e rode o comando unico seguindo só o README
- [ ] A URL publica esta no ar?
- [ ] Usuário confirmou o envio das credenciais ao professor por e-mail
- [ ] Toda configuracao esta em variavel de ambiente (nada fixo no codigo)?
- [ ] Os logs estao livres de dados pessoais?
- [ ] `uv run pytest`, `uv run pytest -m e2e` e `uv run ruff check .` verdes
- [ ] Commits enviados ao GitHub
- [ ] Lembrar o usuário de postar **apenas o link do repositório** no AVA

## Extensoes opcionais (R8) - DISPENSADAS

Não valem nota. Dispensadas por decisão do usuário; não implementar sem pedido.

- Autoescalonamento de workers conforme o tamanho da fila
- Componente serverless ou na borda
- CI/CD publicando automaticamente a cada commit
- Painel de metricas
- Manifests de Kubernetes

Também fora de escopo: interface gRPC do C1.A2 (REST e mensageria já cobrem a comunicação)
e qualquer melhoria do modelo de IA (não pontua).
