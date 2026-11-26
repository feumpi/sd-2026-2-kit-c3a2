# referencia/ — código do C1.A2 e C2.A2, só para consulta

Cópias fiéis dos trabalhos anteriores do usuário. **Não editar, não importar, não testar**
(fora do `ruff`, do pytest e das imagens). **Apagar esta pasta na verificação final.**

Origem: `sd-2026-2-kit-c1a2@e9042d5` e `sd-2026-2-kit-c2a2@d37f0e3` (também em
`github.com/feumpi/`).

| Arquivo | Serve de modelo para |
|---------|----------------------|
| `c1a2/api_rest.py` | rotas assíncronas e log por requisição |
| `c1a2/worker.py`, `c1a2/fila.py` | processamento do sentimento, retentativa, dead-letter |
| `c2a2/ingestao_app.py` | 202 + id, consulta de tarefa, 503 com fila fora |
| `c2a2/ingestao_indice.py` | id por hash e idempotência (o índice JSON vira pgvector) |
| `c2a2/recuperacao_app.py` | validação e ranqueamento da busca |
| `c2a2/geracao_app.py` | disjuntor, retentativa e degradação elegante no RAG |
| `c2a2/Dockerfile`, `docker-compose.yml`, `dockerignore` | containers (trocar `pip` por `uv`) |
| `c2a2/tests/` | testes a adaptar |

Já copiados para o destino (também sem alteração): `inferencia/{modelo,embeddings,llm}.py`,
`worker/{worker,fila}.py`, `comum/{circuit_breaker,resiliencia}.py`.

Cuidado: o C1 guarda o texto no resultado e o C2 devolve `str(erro)` ao cliente. Nenhum dos
dois pode ser repetido aqui (LGPD).
