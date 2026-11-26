# Trade-offs: CAP, custo e latência

## CAP

A plataforma tem estado em dois lugares: a fila (Redis) e o banco vetorial (Postgres). Cada um
é um único nó; a partição possível é entre um serviço e o seu armazenamento. A escolha foi
**aceitar escritas e processá-las depois** na indexação, e **falhar de forma explícita** onde
não há como responder certo.

| Cenário | Comportamento | O que se priorizou |
|---------|---------------|--------------------|
| Operação normal | `POST /documentos` responde 202 antes de gravar; o documento aparece na busca depois | disponibilidade e latência; **consistência eventual** |
| Inferência fora | a escrita é aceita e a tarefa fica `pendente`; `/predict` responde 503 na hora, com o disjuntor aberto | disponibilidade da escrita |
| Worker sem acesso ao banco | a mensagem volta para a fila sem gastar tentativa; após 15 min vai para a dead-letter | não perder dado |
| Banco fora, na leitura | `/buscar` e `/perguntar` respondem 503 `degradado`; `/predict` segue | não responder com dado inexistente |
| Redis fora | `/documentos` e `/tarefas` respondem 503; rotas síncronas seguem | recusar a escrita em vez de perdê-la |
| Redis fora, no limite de requisições | a requisição passa, com aviso no log | disponibilidade acima da proteção |
| LLM fora | 503 com os trechos recuperados | resposta parcial útil |

- **Entrega ao menos uma vez, efeito uma vez.** A mensagem só sai de "processando" junto com o
  resultado; reprocessar é seguro porque o id do documento é o resumo do conteúdo.
- **Fila sem persistência na nuvem.** O Key Value gratuito perde tudo num reinício: tarefas
  pendentes somem e o acompanhamento passa a responder 404. Reenviar é seguro. Localmente o
  Redis grava em disco (`appendonly`).
- **Um único worker.** A recuperação das mensagens interrompidas pressupõe isso; escalar
  exigiria uma lista "processando" por consumidor ou Redis Streams.

## Custo

Hoje o custo é **zero**. O que aperta primeiro:

| Limite gratuito | Efeito |
|-----------------|--------|
| 750 horas de instância por mês, somadas | três serviços acordados o tempo todo acabam com a cota em cerca de 10 dias; dormir é o que a faz render |
| Postgres expira em 30 dias (mais 14 de carência), 1 GB, sem backup | o ambiente publicado tem prazo de validade |
| Um Key Value de 25 MB, 50 conexões, sem persistência | fila pequena e volátil |
| 500 minutos de *build* e 5 GB de banda por mês | builds filtrados por pasta |
| Honeycomb: 20 milhões de eventos por mês | folgado para o volume deste projeto |

Para remover as limitações, pelos preços consultados em 26/11/2026:

| Item | Menor plano pago | US$/mês |
|------|------------------|---------|
| 3 web services (512 MB), sem dormir | 3 × 7 | 21,00 |
| Postgres 256 MB, com 1 GB de armazenamento | 6 + 0,30 | 6,30 |
| Key Value 256 MB | 10 | 10,00 |
| **Total** | | **37,30** |

Fontes: [preços](https://render.com/pricing) e [plano gratuito](https://render.com/docs/free)
do Render; [preços do Honeycomb](https://www.honeycomb.io/pricing).

Memória em repouso no compose: inferência 112 MB, worker 60 MB, vetorial 57 MB, gateway 55 MB,
Jaeger 16 MB, Redis 5 MB. Há folga nos 512 MB por serviço; o que limita é a CPU (0,1).

## Latência

Medida com [deploy/medir_latencia.py](../deploy/medir_latencia.py), sempre através do gateway.

### Local (compose num Apple M3, 4 CPUs e 2 GB para o Docker; 20 amostras)

| Etapa | Mediana | Máximo |
|-------|---------|--------|
| `GET /saude` | 2 ms | 7 ms |
| `POST /predict` (síncrono) | 15 ms | 19 ms |
| `POST /documentos` (202) | 4 ms | 55 ms |
| documento concluído (fila + worker + inferência + banco) | 272 ms | 601 ms |
| `POST /buscar` | 11 ms | 1165 ms |
| `POST /perguntar` (LLM simulado) | 9 ms | 67 ms |

Subir o sistema parado até todos os serviços saudáveis (`docker compose up -d --wait`, imagens
já construídas): 22,5 s nas três medições.

### Publicado

Render (Virgínia), medido de uma máquina no Brasil em 26/11/2026.

**Cold start** (serviço adormecido, acordado por acesso externo):

| Serviço | Tempo até responder |
|---------|---------------------|
| gateway | cerca de 18 s |
| worker | 17,6 s |
| inferência | 27,6 s |

Cada valor é uma única medição; inferência e worker foram acordados em paralelo.

**O que não funcionou:** com os três dormindo, um acesso só ao gateway o acordou, mas as
chamadas dele não acordaram a inferência nem o worker: por mais de 5 minutos o `/predict`
respondeu 503 e nenhum dos dois registrou subida. As chamadas voltavam com erro em cerca de
1 s, em vez de esperar o serviço subir. Um acesso externo os acordou. Por isso a página inicial
publicada faz o navegador de quem visita abrir o `/saude` de cada um.

**Aquecido** (6 amostras):

| Etapa | Mediana | Máximo |
|-------|---------|--------|
| `GET /saude` | 149 ms | 157 ms |
| `POST /predict` (síncrono) | 199 ms | 203 ms |
| `POST /documentos` (202) | 146 ms | 158 ms |
| documento concluído | 294 ms | 308 ms |
| `POST /buscar` | 206 ms | 471 ms |
| `POST /perguntar` (LLM simulado) | 221 ms | 348 ms |

A maior parte dos cerca de 150 ms de `/saude` é a viagem entre o cliente e a região do serviço.

## O que se trocou por quê

- **Síncrono contra assíncrono.** Indexar pela fila devolve a resposta em milissegundos e
  absorve picos e quedas, ao preço de o cliente consultar o estado e de a busca ficar
  momentaneamente desatualizada. O sentimento é síncrono porque é rápido e o cliente precisa
  da resposta.
- **URLs públicas entre serviços.** O plano gratuito não recebe tráfego privado: cada salto
  entre serviços sai pela internet em HTTPS, o que soma latência e exige token interno. Em
  rede privada (plano pago) os dois custos diminuiriam.
- **Cold start contra horas gratuitas.** Não há ping periódico para manter serviços acordados:
  três serviços sempre ligados gastariam a cota do mês em cerca de 10 dias. O preço é o passo
  de despertar pelo navegador depois de uma pausa; um serviço pago, que não dorme, o eliminaria.
- **Tempo-limite longo na nuvem.** 90 s por tentativa (10 s no local) foram pensados para
  esperar um serviço acordando. Como o pedido a um serviço adormecido volta com erro quase
  imediato, o prazo longo só pesa numa falha real de resposta lenta, que demora mais a ser
  percebida até o disjuntor abrir.
- **Limite no login.** Atrás do proxy da hospedagem não há garantia documentada de qual
  cabeçalho traz o IP real sem poder ser forjado; usa-se o endereço da conexão, e na nuvem a
  cota do `/login` pode ser compartilhada entre clientes. Prefere-se isso a um limite que se
  contorna trocando um cabeçalho.
- **Embeddings por *hashing*.** Dimensão fixa e nenhum vocabulário compartilhado, com busca
  menos precisa que a de um modelo semântico: a qualidade da IA não era o objetivo.
