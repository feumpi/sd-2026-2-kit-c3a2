# Diário de implementação — C3.A2: Plataforma de IA como Serviço

Registro das decisões e do raciocínio, para que humanos e agentes entendam como se chegou ao
resultado. Regras de preenchimento em [CLAUDE.md](CLAUDE.md).

## Resumo

| Etapa | Status |
|-------|--------|
| Fase 0 — Ambiente | concluída em 26/11/2026 (falta conectar o GitHub ao Render e criar a chave do Honeycomb) |
| F1 Base da arquitetura | pendente |
| 1 a 10 (kit) | pendentes |
| F2 README e F3 Verificação final | pendentes |

## Fase 0 — Preparação do ambiente (26/11/2026)

Objetivo: deixar o repositório e a máquina prontos para um agente novo implementar, **sem
implementar**. A preparação aconteceu no próprio dia da entrega, o que pesou a favor de
escolhas simples e de reuso.

### O que foi levantado

- Edital, ebook (blocos C2 e C3 na íntegra), arquivos do kit e os trabalhos C1.A2 e C2.A2.
- O repositório é um fork de `howardroatti/sd-2026-2-kit-c3a2` (R11), idêntico ao original
  antes desta preparação.
- Os repositórios anteriores usam um guia para agentes, tarefas em ordem, diário de
  implementação, testes por tarefa e Conventional Commits. O mesmo método foi adotado.

### Decisões do usuário

| Tema | Escolha | Alternativas descartadas |
|------|---------|--------------------------|
| Deploy | Render + Neon | VM no GCP (1 GB de RAM, possível custo de IPv4); Oracle (conta nova, risco de capacidade); Railway (crédito curto) |
| Armazenamento vetorial | pgvector | serviço próprio com o índice JSON do C2 (perde dados em disco efêmero); Qdrant (mais uma conta) |
| Rate limit | implementar | dispensar (não está no edital, mas é núcleo do kit) |
| Traces na nuvem | Honeycomb | Grafana Cloud (configuração mais longa); só Jaeger local |
| RAG com LLM do C2 | incluir, em modo simulado | só busca vetorial |
| Grupo | individual | — |
| Git | versionar `docs/` (inclusive ebook) e fazer push | — |

### Decisões técnicas da preparação

- **Edital × kit:** o edital manda. Opcionais do §8 dispensados; interface gRPC do C1 fora do
  escopo, pois a rubrica aceita "REST / gRPC / mensageria" e REST com fila já atende.
- **Um grupo de dependências por serviço** num único `pyproject.toml`, em vez de um
  `requirements.txt` por pasta ou de um workspace `uv`: um só lock e Dockerfiles que instalam
  apenas o necessário.
- **Versões:** mantidas as fixadas no kit e no C1/C2, com uma exceção: `pyjwt` subiu de
  2.9.0 para 2.15.1, porque a versão do kit tem vários avisos de segurança e é a base da
  autenticação (consulta ao OSV em 26/11/2026). Dependências novas resolvidas na versão atual
  e travadas no `uv.lock`.
- **Pendência de segurança (resolvida na continuação abaixo):** a mesma consulta aponta avisos em `starlette` 0.38.6
  (trazido pelo `fastapi` 0.115.0 do kit; alguns de severidade alta) e em `requests` 2.32.3
  (moderados). Não foram atualizados; decidir com o usuário.
- **Python 3.12**, como a imagem do kit e o C2.
- **Quatro Dockerfiles**, um para cada serviço citado no §2, inclusive o armazenamento
  vetorial. Redis e Jaeger são infraestrutura pronta e usam a imagem oficial.
- **Reuso:** módulos aproveitáveis copiados sem alteração para os serviços, para que as
  adaptações apareçam como diffs; o que serve só de modelo foi para `referencia/`.
- **Rotas, fluxo e responsabilidades** definidos em `CLAUDE.md` (raiz e diretórios), a partir
  das restrições abaixo.

### Restrições descobertas que moldaram a arquitetura

| Constatação | Consequência no plano |
|-------------|-----------------------|
| Render gratuito não tem background worker | worker é web service com consumidor em thread |
| Web service gratuito não recebe tráfego privado | chamadas por URL pública + token interno |
| Serviço dorme após 15 min | pings de despertar; falha transitória não gasta tentativa |
| Key Value gratuito não persiste | limitação a declarar no relatório CAP |
| TF-IDF do C2 muda de dimensão | `HashingVectorizer` com 512 dimensões |
| Cosseno com vetor zero no pgvector dá `NaN` (testado) | tratar texto sem tokens |
| Contexto de trace não atravessa lista Redis | injetar `traceparent` na mensagem |
| Log de acesso do uvicorn grava IP | `--no-access-log` e log próprio |
| Neon usa Postgres 18 por padrão | fixar 17, igual à imagem local |

### Verificações executadas

- `uv run pytest`: 19 passaram (dependências importáveis e modelo funcionando offline). Há um
  aviso inofensivo do scikit-learn 1.5.2 com o SciPy atual (`Unknown solver options: iprint`).
- Instalação por grupo em imagem `python:3.12-slim` arm64: gateway, inferência e worker
  construíram e importaram suas bibliotecas.
- `pgvector/pgvector:pg17` subiu, criou a extensão e calculou distância; Jaeger 2.23.0 subiu.
  Ociosos, cerca de 100 MB e 90 MB: os 2 GB do Docker devem bastar.
- Modelo e embeddings no processo local: cerca de 110 MB, abaixo dos 512 MB do Render.
- CLI do Render 2.39.0 instalado e autenticado pelo usuário durante a preparação.
- `ruff check`: 2 avisos I001 em arquivos importados, que somem na adaptação.
- **Não verificado:** compose completo, Dockerfiles finais e qualquer coisa na nuvem. Os fatos
  sobre o Render vêm da documentação, não de um deploy. Comportamentos descritos nos
  `CLAUDE.md` sobre `X-Forwarded-For`, atributos de IP nos spans e referências do
  `render.yaml` precisam ser confirmados na implementação.

### Revisão do advisor

- **Planejamento:** perguntar as decisões antes de escrever; importar o código sem alterações
  num commit próprio; registrar nos guias que o contexto de trace não atravessa a fila.
- **Revisão final, antes do push:** retirados dos guias nomes de recursos de outros projetos
  (o repositório é público); os commits de documentação, ainda locais, foram refeitos. Também
  entraram os cuidados com minutos de build do Render, tempo-limite durante o cold start da
  inferência, URLs públicas no `render.yaml` e a justificativa correta da versão do `pyjwt`.

## Fase 0 — Continuação (26/11/2026)

### Decisões do usuário

| Tema | Decisão | Motivo |
|------|---------|--------|
| Banco na nuvem | **Postgres gratuito do Render**, no lugar do Neon | a organização disponível no Neon está em plano pago por uso, e o edital exige free tier |
| Credenciais publicadas | e-mail ao professor | no README público permitiriam uso por qualquer um (leitura de textos alheios, estouro de cota); no AVA contrariariam o "APENAS o link" do §9 |
| Honeycomb | região US | — |
| Vulnerabilidades | atualizar | — |

Consequências do novo banco: sem conta extra e com acesso por rede privada; em troca, expira
em 30 dias, não tem backup e há um só por workspace. Por isso é criado apenas no deploy. Onde
a seção anterior menciona o Neon, vale esta decisão.

### O que foi feito

- `fastapi` 0.115.0 → 0.165.0 (leva o `starlette` a 1.10.0) e `requests` 2.32.3 → 2.34.2;
  `pydantic` e `uvicorn` não precisaram mudar. Depois disso: 19 testes passando, builds por
  grupo em Docker ok e consulta ao OSV sem avisos nos 65 pacotes travados.
- Teste rápido da instrumentação com as novas versões: `/saude` excluído dos traces; spans
  trazem `net.peer.ip`, que precisa ser removido (LGPD).
- Pyright instalado com `vp` (ferramenta Node) e apontado para o `.venv`. Os erros que acusa
  estão nos arquivos importados.
- CLI do Render: workspace definido; nenhum serviço criado.
- Blueprint rascunhado em `deploy/render.yaml.rascunho` e aprovado por
  `render blueprints validate` (6 recursos); um plano inválido foi recusado, o que mostra que a
  validação verifica de fato. Comportamento em execução não verificado.
- A conexão do GitHub ao Render exige consentimento no navegador e ficou com o usuário.

<!--
Modelo para as próximas etapas:

## Tarefa N — Título (data)

**O que foi feito:**
**Decisões e justificativas:** (alternativas descartadas; ligação com as aulas)
**Problemas encontrados:**
**Verificação:** (comandos e resultado real)
**Revisão do advisor:** (apontamentos e ajustes)
**Desvios do plano / pendências:**
-->
